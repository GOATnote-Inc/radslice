"""Disk-cache wrapper for any Provider."""

from __future__ import annotations

from typing import Any

from radslice.cache import ResponseCache
from radslice.image import EncodedImage
from radslice.providers.base import Provider, ProviderResponse


class CachedProvider(Provider):
    """Wraps a Provider with disk-based response caching."""

    def __init__(self, inner: Provider, cache: ResponseCache):
        self._inner = inner
        self._cache = cache

    @property
    def name(self) -> str:
        return f"cached-{self._inner.name}"

    @property
    def supports_vision(self) -> bool:
        return self._inner.supports_vision

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str,
        images: list[EncodedImage] | None = None,
        temperature: float = 0.0,
        seed: int = 42,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        # Build cache key (include image refs for uniqueness)
        cache_messages = list(messages)
        if images:
            # Include image hashes in the cache key
            image_refs = [img.original_path for img in images]
            cache_messages = [*messages, {"role": "system", "content": f"images:{image_refs}"}]

        key = ResponseCache.cache_key(model, cache_messages, temperature, seed)

        cached = self._cache.get(key)
        if cached is not None:
            return ProviderResponse(
                text=cached,
                model=model,
                latency_ms=0.0,
                cached=True,
            )

        response = await self._inner.complete(
            messages=messages,
            model=model,
            images=images,
            temperature=temperature,
            seed=seed,
            max_tokens=max_tokens,
        )

        self._cache.put(key, response.text, model)
        return response

    @property
    def cache_stats(self) -> dict:
        return self._cache.stats

    async def health_check(self) -> bool:
        return await self._inner.health_check()

    async def close(self) -> None:
        await self._inner.close()
