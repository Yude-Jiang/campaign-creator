from typing import Literal

from pydantic import BaseModel, Field


class GEODiagnosisResult(BaseModel):
    """Structured result extracted from a GEO diagnosis file."""
    question_id: str = ""
    models_tested: list[str] = Field(default_factory=list)
    st_recall_position: int | None = None           # None = not mentioned
    st_recall_strength: Literal["strong", "moderate", "weak", "absent"] = "absent"
    st_sentiment: Literal["positive", "neutral", "negative"] = "neutral"
    st_mentioned_products: list[str] = Field(default_factory=list)
    competitors_named: list[dict] = Field(default_factory=list)
    cognition_errors: list[str] = Field(default_factory=list)
    gap_type: Literal["open_gap", "rival_owned", "not_linked", "buried_in_pdf"] = "open_gap"
    recommended_anchor: str = ""
    raw_excerpt: str = ""                            # Key snippet from diagnosis
