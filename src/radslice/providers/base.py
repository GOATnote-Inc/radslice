"""Abstract Provider base class with multimodal vision support."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from radslice.image import EncodedImage


@dataclass(frozen=True)
class ProviderResponse:
    """Response from an LLM provider."""

    text: str
    model: str
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class Provider(ABC):
    """Abstract base class for multimodal LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'openai', 'anthropic', 'google')."""
        ...

    @property
    def supports_vision(self) -> bool:
        return True

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str,
        images: list[EncodedImage] | None = None,
        temperature: float = 0.0,
        seed: int = 42,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        """Send a multimodal completion request.

        Args:
            messages: Conversation messages (role/content dicts).
            model: Model identifier.
            images: Optional list of encoded images to include.
            temperature: Sampling temperature (0.0 for deterministic).
            seed: Random seed for reproducibility.
            max_tokens: Maximum completion tokens.

        Returns:
            ProviderResponse with text and metadata.
        """
        ...

    async def health_check(self) -> bool:
        """Check if the provider is available."""
        return True

    async def close(self) -> None:
        """Clean up resources."""
        pass
