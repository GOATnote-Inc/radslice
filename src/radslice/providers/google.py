"""Google Gemini multimodal provider (Gemini 2.5 Pro)."""

from __future__ import annotations

import time
from typing import Any

from radslice.image import EncodedImage
from radslice.providers.base import Provider, ProviderResponse


class GoogleProvider(Provider):
    """Provider for Google Gemini multimodal models."""

    def __init__(self, api_key: str | None = None):
        from google import genai

        self._client = genai.Client(api_key=api_key) if api_key else genai.Client()

    @property
    def name(self) -> str:
        return "google"

    def _build_contents(
        self, messages: list[dict[str, Any]], images: list[EncodedImage] | None
    ) -> list[dict[str, Any]]:
        """Build Gemini-format contents."""
        from google.genai import types

        contents = []
        for msg in messages:
            role = "user" if msg["role"] in ("user", "system") else "model"
            parts = []
            content = msg.get("content", "")
            if isinstance(content, str):
                parts.append(types.Part.from_text(text=content))
            contents.append(types.Content(role=role, parts=parts))

        # Attach images to the last user content
        if images and contents:
            for i in range(len(contents) - 1, -1, -1):
                if contents[i].role == "user":
                    for img in images:
                        import base64

                        img_bytes = base64.b64decode(img.base64_data)
                        contents[i].parts.append(
                            types.Part.from_bytes(data=img_bytes, mime_type=img.media_type)
                        )
                    break

        return contents

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str,
        images: list[EncodedImage] | None = None,
        temperature: float = 0.0,
        seed: int = 42,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        from google.genai import types

        contents = self._build_contents(messages, images)

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            seed=seed,
        )

        start = time.monotonic()
        response = await self._client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        latency = (time.monotonic() - start) * 1000

        text = response.text or ""
        usage = response.usage_metadata

        return ProviderResponse(
            text=text,
            model=model,
            latency_ms=latency,
            prompt_tokens=usage.prompt_token_count if usage else 0,
            completion_tokens=usage.candidates_token_count if usage else 0,
            total_tokens=usage.total_token_count if usage else 0,
        )
