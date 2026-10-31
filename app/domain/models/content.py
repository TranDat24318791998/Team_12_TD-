from typing import Literal
from pydantic import Field
from app.domain.models.shops import StrictModel


class ContentText(StrictModel):
    title: str
    description: str
    checks: list[str]


class CoverImage(StrictModel):
    option: Literal["A", "B", "C"]
    status: Literal["running", "done", "failed", "cached"]
    path: str | None = None
    prompt: str = ""


class VideoJob(StrictModel):
    status: Literal["pending", "running", "done", "failed", "cached"]
    path: str | None = None
    job_id: str | None = None
    prompt: str = ""
    error: str | None = None


class ContentDraft(StrictModel):
    shop_id: str
    version: int = Field(ge=1, le=3)
    title: str
    description: str
    images: list[CoverImage]
    video: VideoJob
    feedback_history: list[str] = Field(default_factory=list)
    style_notes: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    card_id: str
    brief_version: int
