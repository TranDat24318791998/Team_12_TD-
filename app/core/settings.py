"""Nạp thiết lập môi trường; các quy tắc nghiệp vụ nằm trong domain."""

import json
import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.paths import PROJECT_ROOT
from app.domain.models.shops import FeeConfig


class Settings(BaseModel):
    """Nạp .env, môi trường và tham số trực tiếp theo thứ tự ưu tiên."""

    model_config = ConfigDict(extra="forbid")

    openai_api_key: str = Field(default="", repr=False)
    llm_model: str = ""
    llm_model_reflect: str = ""
    openai_image_model: str = ""
    llm_mode: Literal["auto", "live", "replay", "offline"] = "auto"
    useapi_token: str = Field(default="", repr=False)
    muse_email: str = ""
    langfuse_public_key: str = Field(default="", repr=False)
    langfuse_secret_key: str = Field(default="", repr=False)
    langfuse_host: str = ""
    seed: int = 42
    demo_shop: str = "D"
    max_live_calls_per_session: int = Field(default=40, ge=0)
    max_video_jobs_per_session: int = Field(default=3, ge=0)
    image_provider: Literal["openai", "muse"] = "openai"
    mock_api: bool = False
    fees: FeeConfig = Field(default_factory=FeeConfig)

    def __init__(self, _env_file: str | Path | None = PROJECT_ROOT / ".env", **values):
        source = dict(dotenv_values(_env_file)) if _env_file is not None else {}
        source.update(os.environ)
        env_values = {
            name: source[name.upper()]
            for name in type(self).model_fields
            if name != "fees" and source.get(name.upper()) not in (None, "")
        }
        super().__init__(**(env_values | values))

    @model_validator(mode="after")
    def set_reflect_model(self):
        if not self.llm_model_reflect:
            self.llm_model_reflect = self.llm_model
        return self

    def resolved_mode(self) -> Literal["live", "replay", "offline"]:
        if not self.openai_api_key or self.llm_mode == "offline":
            return "offline"
        return "live" if self.llm_mode == "auto" else self.llm_mode

    def describe(self) -> str:
        data = self.model_dump()
        for field in (
            "openai_api_key", "useapi_token", "langfuse_public_key", "langfuse_secret_key"
        ):
            value = data[field]
            data[field] = (
                f"{value[:4]}…{value[-4:]}" if len(value) > 8 else "[đã ẩn]" if value else ""
            )
        data["resolved_mode"] = self.resolved_mode()
        return json.dumps(data, ensure_ascii=False, indent=2)
