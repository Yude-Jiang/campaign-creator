from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class QuestionCategory(StrEnum):
    CATEGORY_AWARENESS = "category_awareness"       # 品类认知
    SELECTION = "selection"                          # 选型
    IMPLEMENTATION = "implementation"                # 实施
    COST = "cost"                                    # 成本


class BenchmarkQuestion(BaseModel):
    """A benchmark question for GEO diagnosis."""
    id: str = ""
    text: str = ""                                  # Chinese text
    text_en: str = ""                               # English version (optional)
    category: QuestionCategory = QuestionCategory.CATEGORY_AWARENESS
    target_persona_ids: list[str] = Field(default_factory=list)
    diagnostic_value: Literal["high", "medium", "low"] = "medium"
    source_platform: str = ""                       # Where found (Zhihu, CSDN, etc.)
    source_heat: str = ""                           # Approximate search volume
