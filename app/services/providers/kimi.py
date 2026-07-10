"""Kimi / Moonshot provider (OpenAI-compatible API)."""

import logging
from typing import Any

from app.core.config import settings
from app.services.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class KimiProvider(BaseProvider):
    name = "kimi"

    def is_available(self) -> bool:
        return bool(settings.kimi_api_key)

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> str:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=settings.kimi_api_key,
                base_url=settings.kimi_base_url,
            )
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            resp = await client.chat.completions.create(
                model="moonshot-v1-128k",
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return {"text": resp.choices[0].message.content or ""}
        except Exception as e:
            logger.error("Kimi API error: %s", e)
            raise
