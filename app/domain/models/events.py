from typing import Any
from pydantic import Field
from app.domain.models.shops import StrictModel


class Event(StrictModel):
    seq: int
    run_id: str
    day: int
    ts: str
    type: str
    actor: str
    shop_id: str | None = None
    text_vi: str
    data: dict[str, Any] = Field(default_factory=dict)
