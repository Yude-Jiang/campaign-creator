from typing import Literal

from pydantic import BaseModel, Field


class Persona(BaseModel):
    """Target audience persona with value proposition."""
    id: str = ""
    name: str = ""                          # e.g. "Tier-1 System Architect"
    layer: Literal["decision_maker", "practitioner", "influencer"] = "practitioner"
    tech_depth: Literal["deep", "moderate", "shallow"] = "moderate"
    decision_weight: Literal["high", "medium", "low"] = "medium"
    pain_points: list[str] = Field(default_factory=list)
    info_channels: list[str] = Field(default_factory=list)
    value_proposition: str = ""             # Differentiated VP for this persona
