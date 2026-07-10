from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CampaignBrief(BaseModel):
    """Campaign Brief — user input from Tab 0."""
    name: str = ""
    topic: str = ""
    target_page_url: str = ""
    products: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    competitors_known: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    goal: str = ""                          # Business objective, e.g. "新品launch造势", "防守NXP design-in"
    notes: str = ""
    industry: str = ""                      # Industry context, e.g. "半导体", "工业自动化", "生物医药"
    language: Literal["zh", "en"] = "zh"


class Campaign(BaseModel):
    """Full campaign state — persisted to JSON file."""
    campaign_id: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    language: Literal["zh", "en"] = "zh"

    brief: CampaignBrief = Field(default_factory=CampaignBrief)
    personas: list = Field(default_factory=list)
    questions: list = Field(default_factory=list)
    diagnoses: list = Field(default_factory=list)
    data_assets: list[dict] = Field(default_factory=list)
    # Each: {"claim": "Stellar P3E integrates 6x Cortex-R52", "source": "P3E datasheet DS14xxx rev3 p.12", "verified_by": "jania", "added_at": iso}
    plan: dict | None = None

    current_tab: int = 0  # 0=Brief, 1=Persona, 2=Diagnosis, 3=Plan, 4=Content Studio
