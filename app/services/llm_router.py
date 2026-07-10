"""Multi-model LLM Router with task-based model selection."""

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from app.services.providers import (
    ClaudeProvider,
    DeepSeekProvider,
    GeminiProvider,
    KimiProvider,
)

logger = logging.getLogger(__name__)

# ── Task → Model Routing ──
# Each task maps to primary/secondary/fallback models and optional grounding.

TASK_ROUTING: dict[str, dict[str, Any]] = {
    # Tab 1: Persona & Questions (with grounding)
    "persona_discovery": {
        "primary": "gemini",
        "grounding": True,
        "secondary": "kimi",
        "fallback": "claude",
    },
    "vp_generation": {
        "primary": "deepseek",
        "grounding": False,
        "secondary": "kimi",
        "fallback": "gemini",
    },
    "question_discovery": {
        "primary": "gemini",
        "grounding": True,
        "secondary": "deepseek",
        "fallback": "kimi",
    },
    # Tab 3: Campaign Plan
    "diagnosis_analysis": {
        "primary": "kimi",
        "grounding": False,
        "secondary": "gemini",
        "fallback": "claude",
    },
    "plan_generation": {
        "primary": "claude",
        "grounding": False,
        "secondary": "gemini",
        "fallback": "deepseek",
    },
    # Tab 4: Content Studio
    "content_organic_chinese": {
        "primary": "deepseek",
        "grounding": False,
        "secondary": "kimi",
        "fallback": "gemini",
    },
    "content_organic_english": {
        "primary": "claude",
        "grounding": False,
        "secondary": "gemini",
        "fallback": "deepseek",
    },
    "content_paid_baidu_sem": {
        "primary": "deepseek",
        "grounding": False,
        "secondary": "kimi",
        "fallback": "gemini",
    },
    "content_paid_baidu_feed": {
        "primary": "deepseek",
        "grounding": False,
        "secondary": "kimi",
        "fallback": "gemini",
    },
    "content_paid_bing": {
        "primary": "claude",
        "grounding": False,
        "secondary": "gemini",
        "fallback": "deepseek",
    },
    # Tab 5: Re-check (future)
    "recheck_comparison": {
        "primary": "kimi",
        "grounding": False,
        "secondary": "claude",
        "fallback": "gemini",
    },
    "recheck_attribution": {
        "primary": "claude",
        "grounding": False,
        "secondary": "gemini",
        "fallback": "deepseek",
    },
}

# ── Provider Registry ──

PROVIDERS: dict[str, Any] = {
    "claude": ClaudeProvider(),
    "gemini": GeminiProvider(),
    "deepseek": DeepSeekProvider(),
    "kimi": KimiProvider(),
}

# ── Prompt Template Engine ──

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))


class LLMRouter:
    """Routes generation requests to the best available model for each task."""

    @staticmethod
    async def route_and_generate(
        task: str,
        prompt_name: str,
        variables: dict[str, Any],
        language: str = "zh",
        model_override: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """Route a task to the appropriate model and generate a response.

        Args:
            task: Task key from TASK_ROUTING (e.g. "persona_discovery")
            prompt_name: Template filename (e.g. "persona_discovery.md")
            variables: Jinja2 template variables
            language: "zh" or "en" — selects the prompt subdirectory
            model_override: Force a specific model (bypasses routing)
            max_tokens: Maximum output tokens (default 4096)
            temperature: Sampling temperature (default 0.7)

        Returns:
            {"text": str, "model": str, "task": str}
        """
        # 1. Resolve which model to use
        routing = TASK_ROUTING.get(task, {})
        model_name = model_override or routing.get("primary", "claude")
        grounding = routing.get("grounding", False)

        # 2. Load and render the prompt template
        template_path = f"{language}/{prompt_name}"
        try:
            template = _jinja_env.get_template(template_path)
        except Exception:
            logger.warning("Template not found: %s, trying fallback", template_path)
            # Try the other language as fallback
            fallback_lang = "en" if language == "zh" else "zh"
            template = _jinja_env.get_template(f"{fallback_lang}/{prompt_name}")

        full_prompt = template.render(**variables)

        # 3. Try primary → secondary → fallback chain, with runtime fallback
        model_chain = [model_name]
        for fallback_key in ("secondary", "fallback"):
            fb = routing.get(fallback_key)
            if fb:
                model_chain.append(fb)

        last_error = None
        # Always append gemini as ultimate fallback if it's not already in the chain
        if "gemini" not in model_chain:
            model_chain.append("gemini")

        for candidate in model_chain:
            provider = PROVIDERS.get(candidate)
            if not provider:
                continue
            if not provider.is_available():
                logger.warning("Model %s not configured, skipping", candidate)
                continue

            # Only the first (primary) model gets grounding
            use_grounding = grounding and (candidate == model_name)

            try:
                logger.info("Routing task '%s' → %s (grounding=%s)", task, candidate, use_grounding)
                result = await provider.generate(
                    prompt=full_prompt,
                    system_prompt="",
                    grounding=use_grounding,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                text = result["text"] if isinstance(result, dict) else result
                grounding_sources = result.get("grounding_sources", []) if isinstance(result, dict) else []
                return {
                    "text": text,
                    "model": candidate,
                    "task": task,
                    "grounding_used": use_grounding,
                    "grounding_sources": grounding_sources,
                }
            except Exception as exc:
                last_error = exc
                logger.warning("Model %s failed for task '%s': %s. Trying next...", candidate, task, exc)

        # All models in the chain failed
        logger.error("All models failed for task '%s'. Last error: %s", task, last_error)
        raise RuntimeError(
            f"All LLM models failed for task '{task}'. "
            f"Models tried: {model_chain}. Last error: {last_error}"
        ) from last_error


# Singleton
llm_router = LLMRouter()
