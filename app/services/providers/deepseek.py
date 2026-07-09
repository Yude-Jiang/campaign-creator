"""DeepSeek provider (OpenAI-compatible API)."""

import logging
from typing import Any

from app.core.config import settings
from app.services.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class DeepSeekProvider(BaseProvider):
    name = "deepseek"

    def is_available(self) -> bool:
        return bool(settings.deepseek_api_key)

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
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            resp = await client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            logger.error("DeepSeek API error: %s", e)
            raise
