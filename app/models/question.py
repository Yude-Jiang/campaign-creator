from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class QuestionCategory(StrEnum):
    CATEGORY_AWARENESS = "category_awareness"       # 品类认知
    SELECTION = "selection"                          # 选型
    IMPLEMENTATION = "implementation"                # 实施
    COST = "cost"                                    # 成本


class BenchmarkQuestion(BaseModel):
    """A benchmark question for GEO diagnosis with rich metadata."""
    id: str = ""
    text: str = ""                                  # Chinese text
    text_en: str = ""                               # English version (optional)
    category: QuestionCategory = QuestionCategory.CATEGORY_AWARENESS
    target_persona_ids: list[str] = Field(default_factory=list)
    diagnostic_value: Literal["high", "medium", "low"] = "medium"
    assumed_platform: str = ""                      # Assumed platform — not verified (grounding unavailable)
    assumed_heat: str = ""                          # Assumed discussion heat — not verified
    search_intent: str = ""                         # informational | comparison | transactional
    difficulty_level: str = ""                      # beginner | intermediate | advanced
    search_volume_estimate: str = ""                # High | Medium | Low
    seasonality: str = ""                           # evergreen | trending | seasonal
    related_questions: list[str] = Field(default_factory=list)
    funnel_stage: str = ""                          # why | what | how — maps to decision chain stage
    added_after_baseline: bool = False              # True if added after questions_frozen_at was set
