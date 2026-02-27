"""Anthropic multimodal provider (Claude Opus/Sonnet 4.6)."""

from __future__ import annotations

import time
from typing import Any

from radslice.image import EncodedImage
from radslice.providers.base import Provider, ProviderResponse


class AnthropicProvider(Provider):
    """Provider for Anthropic Claude multimodal models."""

    def __init__(self, api_key: str | None = None):
        import anthropic

        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        self._client = anthropic.AsyncAnthropic(**kwargs)

    @property
    def name(self) -> str:
        return "anthropic"

    def _build_messages(
        self, messages: list[dict[str, Any]], images: list[EncodedImage] | None
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Build Anthropic-format messages. Returns (system, messages)."""
        system_msg = None
        api_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
                continue
            api_messages.append(msg)

        if images and api_messages:
            # Attach images to last user message
            for i in range(len(api_messages) - 1, -1, -1):
                if api_messages[i].get("role") == "user":
                    content_parts = []
                    # Add images first (Anthropic convention)
                    for img in images:
                        content_parts.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": img.media_type,
                                    "data": img.base64_data,
                                },
                            }
                        )
                    # Then text
                    existing = api_messages[i].get("content", "")
                    if isinstance(existing, str):
                        content_parts.append({"type": "text", "text": existing})
                    elif isinstance(existing, list):
                        content_parts.extend(existing)
                    api_messages[i] = {**api_messages[i], "content": content_parts}
                    break

        return system_msg, api_messages

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str,
        images: list[EncodedImage] | None = None,
        temperature: float = 0.0,
        seed: int = 42,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        system_msg, api_messages = self._build_messages(messages, images)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_msg:
            kwargs["system"] = system_msg

        start = time.monotonic()
        response = await self._client.messages.create(**kwargs)
        latency = (time.monotonic() - start) * 1000

        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        return ProviderResponse(
            text=text,
            model=response.model,
            latency_ms=latency,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
        )

    async def close(self) -> None:
        await self._client.close()
