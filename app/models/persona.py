from typing import Literal

from pydantic import BaseModel, Field


class Persona(BaseModel):
    """Target audience persona with deep research dimensions."""
    id: str = ""
    name: str = ""                          # e.g. "Tier-1 System Architect"
    layer: Literal["decision_maker", "practitioner", "influencer"] = "practitioner"
    tech_depth: Literal["deep", "moderate", "shallow"] = "moderate"
    decision_weight: Literal["high", "medium", "low"] = "medium"
    daily_tasks: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    info_channels: list[str] = Field(default_factory=list)
    trusted_sources: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    decision_criteria: list[str] = Field(default_factory=list)
    value_proposition: str = ""             # Differentiated VP for this persona
    vp_headline: str = ""                   # One-line VP headline
    vp_argument: str = ""                   # Expanded VP argument
    vp_proof_points: list[str] = Field(default_factory=list)
    vp_competitor_comparison: dict[str, str] = Field(default_factory=dict)
    anchor: str = ""                        # Master persona code (e.g. "m01") — internal only
    basis: Literal["research", "generated"] = "generated"
    decision_role: str = ""                 # gatekeeper | decision_maker | implementer
    funnel_stage: str = ""                  # why | what | how
    preferred_channels: list[str] = Field(default_factory=list)
    avoid_channels: list[str] = Field(default_factory=list)
