from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ContentAction(BaseModel):
    """A content piece in the campaign plan."""
    format: str = ""                    # "zhihu_long_form" | "csdn_article" | ...
    channel: str = ""                   # "知乎" | "CSDN" | ...
    channel_type: Literal["organic", "paid"] = "organic"
    target_persona_id: str = ""
    title_suggestion: str = ""
    llm_prompt: str = ""


class PriorityItem(BaseModel):
    """A prioritized question with content strategy."""
    question_id: str = ""
    question_text: str = ""
    priority: Literal["P0", "P1", "P2"] = "P2"
    strategic_importance: int = 1       # 1-5
    st_current_strength: int = 1        # 1-5 (5 = strong)
    winnability: int = 1                # 1-5
    target_page_url: str = ""
    anchor_point: str = ""
    gap_type: str = ""
    content_plan: list[ContentAction] = Field(default_factory=list)


class CampaignPlan(BaseModel):
    """Full campaign plan generated from diagnosis analysis."""
    campaign_id: str = ""
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    ai_perception_summary: str = ""
    inverted_pyramid: dict = Field(default_factory=dict)
    competitor_landscape: list[dict] = Field(default_factory=list)
    priorities: list[PriorityItem] = Field(default_factory=list)
    timeline_90days: list[dict] = Field(default_factory=list)
    monitoring_metrics: list[dict] = Field(default_factory=list)
