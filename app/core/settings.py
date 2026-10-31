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
    muse_api_base_url: str = "https://muse-api.butterflyro.space"
    muse_api_key: str = Field(default="", repr=False)
    muse_video_model: str = "muse-video"
    media_mode: Literal["live", "replay", "offline"] = "offline"
    media_api_base_url: str = "http://127.0.0.1:8010"
    media_api_token: str = Field(default="", repr=False)
    media_poll_seconds: float = Field(default=2, gt=0)
    media_draft_timeout_seconds: int = Field(default=1200, gt=0)
    max_image_jobs_per_session: int = Field(default=9, ge=0)
    demo_product_image_path: str = ""
    demo_logo_image_path: str = ""
    langfuse_public_key: str = Field(default="", repr=False)
    langfuse_secret_key: str = Field(default="", repr=False)
    langfuse_host: str = ""
    seed: int = 42
    demo_shop: str = "D"
    max_live_calls_per_session: int = Field(default=64, ge=0)
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
        if self.llm_mode == "replay":
            return "replay"
        if not self.openai_api_key or self.llm_mode == "offline":
            return "offline"
        return "live" if self.llm_mode == "auto" else self.llm_mode

    def describe(self) -> str:
        data = self.model_dump()
        for field in (
            "openai_api_key", "useapi_token", "muse_api_key", "media_api_token", "langfuse_public_key", "langfuse_secret_key"
        ):
            value = data[field]
            data[field] = (
                "[đã ẩn]" if field == "media_api_token" and value else
                f"{value[:4]}…{value[-4:]}" if len(value) > 8 else "[đã ẩn]" if value else ""
            )
        data["resolved_mode"] = self.resolved_mode()
        return json.dumps(data, ensure_ascii=False, indent=2)
