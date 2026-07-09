"""Abstract base for LLM providers."""

from abc import ABC, abstractmethod
from typing import Any


class BaseProvider(ABC):
    """Every LLM provider must implement this interface."""

    name: str = "base"

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> str:
        """Send prompt to the LLM and return the response text."""
        ...

    def is_available(self) -> bool:
        """Check if the provider's API credentials are configured."""
        return True
