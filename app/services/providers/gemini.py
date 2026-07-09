"""Google Gemini provider — Vertex AI with gcloud ADC or AI Studio API key.

Uses direct REST calls to Vertex AI when ADC is available (bypasses SDK
OAuth refresh issues), falls back to google-genai SDK for AI Studio API key.
"""

import asyncio
import json
import logging
import ssl
import urllib.request
from typing import Any

from app.core.config import settings
from app.services.providers.base import BaseProvider

logger = logging.getLogger(__name__)

VERTEX_URL = (
    "https://us-central1-aiplatform.googleapis.com/v1"
    "/projects/{project}/locations/us-central1"
    "/publishers/google/models/{model}:generateContent"
)


class GeminiProvider(BaseProvider):
    name = "gemini"

    def is_available(self) -> bool:
        return bool(settings.google_cloud_project or settings.gemini_api_key)

    @staticmethod
    def _get_gcloud_token() -> str | None:
        """Get a fresh access token from gcloud CLI."""
        import os
        import subprocess

        # Try common gcloud paths
        candidates = [
            "gcloud",                                                    # PATH
            r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
            r"C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
            os.path.expanduser(r"~\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"),
        ]

        for gcloud_path in candidates:
            try:
                result = subprocess.run(
                    [gcloud_path, "auth", "print-access-token"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.debug("gcloud at %s failed: %s", gcloud_path, e)
                continue

        logger.warning("Could not find gcloud CLI in any known location")
        return None

    def _generate_via_rest(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """Generate via Vertex AI REST API using gcloud access token."""
        token = self._get_gcloud_token()
        if not token:
            raise RuntimeError("Cannot get gcloud access token — run 'gcloud auth login'")

        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        url = VERTEX_URL.format(
            project=settings.google_cloud_project,
            model="gemini-2.5-flash",
        )

        body = json.dumps({
            "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }).encode("utf-8")

        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        })

        try:
            ctx = ssl.create_default_context()
            resp = urllib.request.urlopen(req, context=ctx, timeout=120)
            result = json.loads(resp.read())
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.error("Vertex AI REST call failed: %s", e)
            if hasattr(e, "read"):
                logger.error("Response body: %s", e.read().decode()[:500])
            raise

    def _generate_via_api_key(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """Generate via Google AI Studio API key."""
        from google import genai
        from google.genai.types import GenerateContentConfig

        client = genai.Client(api_key=settings.gemini_api_key)
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt,
            config=GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )
        return resp.text

    def _generate_sync(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        grounding: bool = False,
        **kwargs: Any,
    ) -> str:
        """Pick the best available backend, with fallback chain."""
        # Prefer Vertex AI via gcloud REST (most reliable in this environment)
        if settings.google_cloud_project:
            logger.info("Gemini: Vertex AI REST mode (project=%s)", settings.google_cloud_project)
            try:
                return self._generate_via_rest(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except Exception as exc:
                logger.warning(
                    "Gemini Vertex AI REST failed: %s. Falling back to API key...", exc
                )
                if not settings.gemini_api_key:
                    raise RuntimeError(
                        "Gemini Vertex AI REST failed and no GEMINI_API_KEY set"
                    ) from exc

        # Fallback: AI Studio API key
        if settings.gemini_api_key:
            logger.info("Gemini: AI Studio API key mode")
            return self._generate_via_api_key(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        raise RuntimeError("Gemini not available: set GOOGLE_CLOUD_PROJECT or GEMINI_API_KEY")

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        grounding: bool = False,
        **kwargs: Any,
    ) -> str:
        """Async wrapper — delegates sync call to a thread pool."""
        try:
            return await asyncio.to_thread(
                self._generate_sync,
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                grounding=grounding,
                **kwargs,
            )
        except Exception as e:
            logger.error("Gemini API error: %s", e)
            raise
