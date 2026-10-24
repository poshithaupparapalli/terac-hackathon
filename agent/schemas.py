"""Pydantic models for the study plan (AGENT_TASK.md section 2).

Field names match AGENT_TASK.md exactly. Don't rename without telling the team.
"""

from typing import Literal

from pydantic import BaseModel, Field


class AgentNote(BaseModel):
    type: Literal["suggestion", "filled_gap"]
    issue: str
    change: str
    why: str
    applied: bool


class ScreenerQuestion(BaseModel):
    q: str
    qualify_if: str


class Segment(BaseModel):
    name: str
    count: int
    why: str
    criteria: list[str]
    screener: list[ScreenerQuestion]


class Question(BaseModel):
    id: str = Field(description='"q1", "q2", ...')
    text: str
    type: Literal["text", "scale_1_5", "choice"]
    options: list[str] = Field(description="Only for type=choice; empty otherwise")
    purpose: str


class WTPQuestion(BaseModel):
    id: str = Field(description='"wtp1" .. "wtp4"')
    text: str
    type: Literal["number_usd"]


class TeracTask(BaseModel):
    task_type: Literal["interview"]
    review_type: Literal["auto_approve"]
    title: str
    description: str
    instructions: str
    task_url: str = Field(description="https://OUR_SITE/study/{study_id}; overwritten by code")


class TeracQuote(BaseModel):
    task_description: str
    panel_description: str
    submission_count: int
    timeline_hours: int
    pay_rate_frequency: Literal["ONE_TIME", "HOURLY", "PER_TASK"]
    loi_minutes: int


DeviceType = Literal[
    "desktop", "mobile_ios", "mobile_android", "tablet_ios", "tablet_android", "other"
]


class TeracStudy(BaseModel):
    title: str
    description: str
    business_type: Literal["b2c", "b2b"]
    num_participants: int
    device_types: list[DeviceType]
    expected_days_to_complete: int = Field(default=5, ge=5, description="Terac minimum is 5")
    audience_note: str = Field(
        description="Plain language; mapped to Terac filters (country filter required)"
    )
    task: TeracTask
    quote: TeracQuote


class Theme(BaseModel):
    theme: str
    count: int = Field(description="Number of distinct testers who raised it")
    summary: str


class Quote(BaseModel):
    text: str = Field(description="Verbatim excerpt from one tester's answer")
    tester_id: str
    segment: str


class Synthesis(BaseModel):
    """What the model writes. price_range is computed in code, not by the model."""

    themes: list[Theme]
    quotes: list[Quote]
    recommendation: str
    limitations: list[str]


class Report(Synthesis):
    price_range: str


class PlanDraft(BaseModel):
    """The part of the plan the model writes. terac_study and max_cost_cents are built in code."""

    summary: str
    agent_notes: list[AgentNote]
    segments: list[Segment]
    diversity_notes: list[str]
    tester_instructions: str
    est_minutes: int
    est_cost_usd: float
    total_testers: int
    questions: list[Question]
    wtp_questions: list[WTPQuestion]
    limitations: list[str]


class Plan(PlanDraft):
    max_cost_cents: int
    terac_study: TeracStudy
