"""OpenAI multimodal provider (GPT-4o, GPT-5.2)."""

from __future__ import annotations

import time
from typing import Any

from radslice.image import EncodedImage
from radslice.providers.base import Provider, ProviderResponse


class OpenAIProvider(Provider):
    """Provider for OpenAI multimodal models."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        import openai

        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.AsyncOpenAI(**kwargs)

    @property
    def name(self) -> str:
        return "openai"

    def _build_messages(
        self, messages: list[dict[str, Any]], images: list[EncodedImage] | None
    ) -> list[dict[str, Any]]:
        """Build OpenAI-format messages with images inlined."""
        if not images:
            return messages

        result = list(messages)
        # Attach images to the last user message
        for i in range(len(result) - 1, -1, -1):
            if result[i].get("role") == "user":
                content_parts = []
                # Add existing text content
                existing = result[i].get("content", "")
                if isinstance(existing, str):
                    content_parts.append({"type": "text", "text": existing})
                elif isinstance(existing, list):
                    content_parts.extend(existing)

                # Add images
                for img in images:
                    content_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{img.media_type};base64,{img.base64_data}"},
                        }
                    )
                result[i] = {**result[i], "content": content_parts}
                break

        return result

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str,
        images: list[EncodedImage] | None = None,
        temperature: float = 0.0,
        seed: int = 42,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        built = self._build_messages(messages, images)

        start = time.monotonic()
        # GPT-5.2 requires max_completion_tokens
        response = await self._client.chat.completions.create(
            model=model,
            messages=built,
            temperature=temperature,
            seed=seed,
            max_completion_tokens=max_tokens,
        )
        latency = (time.monotonic() - start) * 1000

        choice = response.choices[0]
        usage = response.usage

        return ProviderResponse(
            text=choice.message.content or "",
            model=response.model,
            latency_ms=latency,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
        )

    async def close(self) -> None:
        await self._client.close()
