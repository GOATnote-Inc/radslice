"""Tests for cache.py — SHA-256 disk cache."""

from __future__ import annotations

import json

import pytest

from radslice.cache import ResponseCache


class TestCacheKey:
    def test_deterministic(self):
        key1 = ResponseCache.cache_key("gpt-4", [{"role": "user", "content": "hi"}], 0.0, 42)
        key2 = ResponseCache.cache_key("gpt-4", [{"role": "user", "content": "hi"}], 0.0, 42)
        assert key1 == key2

    def test_different_model(self):
        key1 = ResponseCache.cache_key("gpt-4", [{"role": "user", "content": "hi"}], 0.0, 42)
        key2 = ResponseCache.cache_key("claude", [{"role": "user", "content": "hi"}], 0.0, 42)
        assert key1 != key2

    def test_different_messages(self):
        key1 = ResponseCache.cache_key("gpt-4", [{"role": "user", "content": "hi"}], 0.0, 42)
        key2 = ResponseCache.cache_key("gpt-4", [{"role": "user", "content": "bye"}], 0.0, 42)
        assert key1 != key2

    def test_different_temp(self):
        key1 = ResponseCache.cache_key("gpt-4", [{"role": "user", "content": "hi"}], 0.0, 42)
        key2 = ResponseCache.cache_key("gpt-4", [{"role": "user", "content": "hi"}], 0.5, 42)
        assert key1 != key2

    def test_different_seed(self):
        key1 = ResponseCache.cache_key("gpt-4", [{"role": "user", "content": "hi"}], 0.0, 42)
        key2 = ResponseCache.cache_key("gpt-4", [{"role": "user", "content": "hi"}], 0.0, 99)
        assert key1 != key2

    def test_key_is_hex(self):
        key = ResponseCache.cache_key("model", [], 0.0, 0)
        assert all(c in "0123456789abcdef" for c in key)
        assert len(key) == 64  # SHA-256 hex length


class TestCachePutGet:
    def test_put_and_get(self, tmp_cache_dir):
        cache = ResponseCache(tmp_cache_dir)
        cache.put("testkey", "test response", "model-1")
        result = cache.get("testkey")
        assert result == "test response"

    def test_miss(self, tmp_cache_dir):
        cache = ResponseCache(tmp_cache_dir)
        assert cache.get("nonexistent") is None

    def test_multiple_entries(self, tmp_cache_dir):
        cache = ResponseCache(tmp_cache_dir)
        for i in range(10):
            cache.put(f"key_{i}", f"response_{i}", "model")
        for i in range(10):
            assert cache.get(f"key_{i}") == f"response_{i}"

    def test_overwrite(self, tmp_cache_dir):
        cache = ResponseCache(tmp_cache_dir)
        cache.put("key", "first", "model")
        cache.put("key", "second", "model")
        assert cache.get("key") == "second"

    def test_unicode_content(self, tmp_cache_dir):
        cache = ResponseCache(tmp_cache_dir)
        content = "Radiological findings: pneumothorax 日本語テスト"
        cache.put("unicode_key", content, "model")
        assert cache.get("unicode_key") == content

    def test_empty_response(self, tmp_cache_dir):
        cache = ResponseCache(tmp_cache_dir)
        cache.put("empty_key", "", "model")
        assert cache.get("empty_key") == ""


class TestCacheIntegrity:
    def test_corruption_quarantined(self, tmp_cache_dir):
        cache = ResponseCache(tmp_cache_dir)
        cache.put("corruptkey", "original", "model")

        # Corrupt the cached file
        cache_file = cache._path_for_key("corruptkey")
        data = json.loads(cache_file.read_text())
        data["response"] = "tampered"
        cache_file.write_text(json.dumps(data))

        result = cache.get("corruptkey")
        assert result is None
        assert cache._corruption_events == 1

    def test_invalid_json_quarantined(self, tmp_cache_dir):
        cache = ResponseCache(tmp_cache_dir)
        cache.put("badjson", "test", "model")

        cache_file = cache._path_for_key("badjson")
        cache_file.write_text("not json at all")

        result = cache.get("badjson")
        assert result is None


class TestCacheStats:
    def test_initial_stats(self, tmp_cache_dir):
        cache = ResponseCache(tmp_cache_dir)
        stats = cache.stats
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["total"] == 0
        assert stats["hit_rate"] == 0.0

    def test_hit_miss_tracking(self, tmp_cache_dir):
        cache = ResponseCache(tmp_cache_dir)
        cache.put("k1", "v1", "m")

        cache.get("k1")  # hit
        cache.get("k2")  # miss
        cache.get("k1")  # hit

        stats = cache.stats
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["total"] == 3
        assert stats["hit_rate"] == pytest.approx(2 / 3)

    def test_corruption_tracking(self, tmp_cache_dir):
        cache = ResponseCache(tmp_cache_dir)
        cache.put("ck", "val", "m")
        file = cache._path_for_key("ck")
        file.write_text("corrupt")
        cache.get("ck")
        assert cache.stats["corruption_events"] == 1


class TestCachePathStructure:
    def test_two_level_subdirs(self, tmp_cache_dir):
        cache = ResponseCache(tmp_cache_dir)
        key = "abcdef1234567890" * 4  # 64 chars
        cache.put(key, "test", "model")
        path = cache._path_for_key(key)
        # Should be nested under first 2 chars
        assert path.parent.name == key[:2]
