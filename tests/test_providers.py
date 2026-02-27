"""Tests for providers — base, cached, message building."""

from __future__ import annotations

import pytest

from radslice.cache import ResponseCache
from radslice.image import EncodedImage
from radslice.providers.base import Provider, ProviderResponse
from radslice.providers.cached import CachedProvider


class MockProvider(Provider):
    """A mock provider for testing."""

    def __init__(self, responses: list[str] | None = None):
        self._responses = responses or ["mock response"]
        self._call_count = 0

    @property
    def name(self) -> str:
        return "mock"

    async def complete(
        self, messages, model, images=None, temperature=0.0, seed=42, max_tokens=4096
    ):
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return ProviderResponse(
            text=self._responses[idx],
            model=model,
            latency_ms=100.0,
            prompt_tokens=50,
            completion_tokens=100,
            total_tokens=150,
        )


class TestProviderResponse:
    def test_frozen(self):
        resp = ProviderResponse(text="test", model="m", latency_ms=100.0)
        with pytest.raises(AttributeError):
            resp.text = "changed"

    def test_defaults(self):
        resp = ProviderResponse(text="test", model="m", latency_ms=0.0)
        assert resp.prompt_tokens == 0
        assert resp.cached is False
        assert resp.metadata == {}

    def test_all_fields(self):
        resp = ProviderResponse(
            text="test",
            model="gpt-5.2",
            latency_ms=250.0,
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            cached=True,
            metadata={"key": "val"},
        )
        assert resp.total_tokens == 300
        assert resp.cached is True


class TestMockProvider:
    @pytest.mark.asyncio
    async def test_basic_completion(self):
        provider = MockProvider(["test response"])
        resp = await provider.complete(
            messages=[{"role": "user", "content": "hello"}],
            model="test-model",
        )
        assert resp.text == "test response"
        assert resp.model == "test-model"

    @pytest.mark.asyncio
    async def test_multiple_responses(self):
        provider = MockProvider(["first", "second", "third"])
        r1 = await provider.complete([], model="m")
        r2 = await provider.complete([], model="m")
        r3 = await provider.complete([], model="m")
        assert r1.text == "first"
        assert r2.text == "second"
        assert r3.text == "third"

    def test_supports_vision(self):
        provider = MockProvider()
        assert provider.supports_vision is True

    @pytest.mark.asyncio
    async def test_health_check(self):
        provider = MockProvider()
        assert await provider.health_check() is True


class TestCachedProvider:
    @pytest.mark.asyncio
    async def test_cache_miss_then_hit(self, tmp_cache_dir):
        inner = MockProvider(["real response"])
        cache = ResponseCache(tmp_cache_dir)
        cached = CachedProvider(inner, cache)

        messages = [{"role": "user", "content": "test"}]

        # First call: cache miss
        r1 = await cached.complete(messages, model="m")
        assert r1.text == "real response"
        assert r1.cached is False

        # Second call: cache hit
        r2 = await cached.complete(messages, model="m")
        assert r2.text == "real response"
        assert r2.cached is True

    @pytest.mark.asyncio
    async def test_different_models_separate(self, tmp_cache_dir):
        inner = MockProvider(["r1", "r2"])
        cache = ResponseCache(tmp_cache_dir)
        cached = CachedProvider(inner, cache)

        messages = [{"role": "user", "content": "test"}]
        r1 = await cached.complete(messages, model="model-a")
        r2 = await cached.complete(messages, model="model-b")
        assert r1.text == "r1"
        assert r2.text == "r2"

    @pytest.mark.asyncio
    async def test_cache_with_images(self, tmp_cache_dir):
        inner = MockProvider(["img response"])
        cache = ResponseCache(tmp_cache_dir)
        cached = CachedProvider(inner, cache)

        images = [
            EncodedImage(
                base64_data="abc",
                media_type="image/png",
                width=100,
                height=100,
                original_path="test.png",
            )
        ]
        messages = [{"role": "user", "content": "describe this image"}]

        r1 = await cached.complete(messages, model="m", images=images)
        r2 = await cached.complete(messages, model="m", images=images)
        assert r1.cached is False
        assert r2.cached is True
        assert r2.text == "img response"

    @pytest.mark.asyncio
    async def test_cache_stats(self, tmp_cache_dir):
        inner = MockProvider(["response"])
        cache = ResponseCache(tmp_cache_dir)
        cached = CachedProvider(inner, cache)

        messages = [{"role": "user", "content": "test"}]
        await cached.complete(messages, model="m")
        await cached.complete(messages, model="m")

        stats = cached.cache_stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_name(self, tmp_cache_dir):
        inner = MockProvider()
        cache = ResponseCache(tmp_cache_dir)
        cached = CachedProvider(inner, cache)
        assert cached.name == "cached-mock"

    def test_supports_vision(self, tmp_cache_dir):
        inner = MockProvider()
        cache = ResponseCache(tmp_cache_dir)
        cached = CachedProvider(inner, cache)
        assert cached.supports_vision is True
