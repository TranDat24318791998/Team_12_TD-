"""Kiểm thử cấu hình độc lập với HTTP và API trả phí."""

import json

import pytest
from pydantic import ValidationError

from app.core.paths import PROJECT_ROOT
from app.core.settings import Settings


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def test_empty_example_loads_defaults():
    settings = Settings(_env_file=PROJECT_ROOT / ".env.example")
    assert settings.seed == 42
    assert settings.demo_shop == "D"
    assert settings.max_live_calls_per_session == 64
    assert settings.max_video_jobs_per_session == 3
    assert settings.resolved_mode() == "offline"
    assert settings.fees.model_dump() == {
        "fixed_pct": 8, "transaction_pct": 5, "tax_pct": 1.5, "per_order": 3000
    }


@pytest.mark.parametrize(
    ("mode", "key", "expected"),
    [("auto", "", "offline"), ("auto", "fake-key", "live"),
     ("offline", "fake-key", "offline"), ("live", "", "offline"),
     ("live", "fake-key", "live"), ("replay", "fake-key", "replay"),
     ("replay", "", "replay")],
)
def test_resolved_modes(mode, key, expected):
    assert Settings(_env_file=None, llm_mode=mode, openai_api_key=key).resolved_mode() == expected


def test_env_precedence_and_reflect_default(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("SEED=7\nLLM_MODEL=test-model\nMOCK_API=1\n", encoding="utf-8")
    monkeypatch.setenv("SEED", "12")
    settings = Settings(_env_file=env)
    assert settings.seed == 12
    assert settings.mock_api is True
    assert settings.llm_model_reflect == "test-model"
    assert Settings(_env_file=env, seed=99).seed == 99


def test_describe_hides_secrets():
    key = "test-private-value-1234"
    settings = Settings(_env_file=None, openai_api_key=key, useapi_token="short")
    description = settings.describe()
    assert key not in description
    assert "short" not in description
    assert json.loads(description)["openai_api_key"] == "test…1234"
    assert key not in repr(settings)


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_mode="invalid")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_live_calls_per_session=-1)
