"""Anthropic Claude provider."""

import logging
from typing import Any

from app.core.config import settings
from app.services.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class ClaudeProvider(BaseProvider):
    name = "claude"

    def is_available(self) -> bool:
        return bool(settings.anthropic_api_key)

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> str:
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            messages = [{"role": "user", "content": prompt}]
            resp = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=messages,
            )
            return {"text": resp.content[0].text}
        except Exception as e:
            logger.error("Claude API error: %s", e)
            raise
