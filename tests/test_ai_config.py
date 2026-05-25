"""Tests for app/ai/config.py — settings helpers + cache + seed."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.config import (
    SETTINGS_REGISTRY,
    bust_cache,
    get_all_settings,
    get_setting,
    seed_defaults,
    set_setting,
)
from app.models import AiSetting


@pytest.fixture(autouse=True)
def _reset_cache():
    """Mỗi test chạy với cache sạch — tránh leak giữa tests."""
    bust_cache()
    yield
    bust_cache()


def test_get_setting_returns_default_when_db_empty(session: Session):
    assert get_setting("enabled", db=session) is False
    assert get_setting("base_url", db=session) == "https://openrouter.ai/api/v1"
    assert get_setting("temperature", db=session) == 0.2
    assert get_setting("max_tokens", db=session) == 1024


def test_get_setting_unknown_key_raises(session: Session):
    with pytest.raises(KeyError):
        get_setting("nonexistent_key", db=session)


def test_set_and_get_roundtrip_string(session: Session):
    set_setting("base_url", "https://api.openai.com/v1", "tester", db=session)
    assert get_setting("base_url", db=session) == "https://api.openai.com/v1"


def test_set_and_get_roundtrip_bool(session: Session):
    set_setting("enabled", True, "tester", db=session)
    assert get_setting("enabled", db=session) is True
    set_setting("enabled", False, "tester", db=session)
    assert get_setting("enabled", db=session) is False


def test_set_and_get_roundtrip_int_float(session: Session):
    set_setting("max_tokens", 2048, "tester", db=session)
    set_setting("temperature", 0.7, "tester", db=session)
    assert get_setting("max_tokens", db=session) == 2048
    assert get_setting("temperature", db=session) == 0.7


def test_set_and_get_roundtrip_dict(session: Session):
    headers = {"HTTP-Referer": "https://x.com", "X-Custom": "abc"}
    set_setting("extra_headers", headers, "tester", db=session)
    assert get_setting("extra_headers", db=session) == headers


def test_set_setting_busts_cache(session: Session):
    # Prime cache với default value
    assert get_setting("model_default", db=session) == SETTINGS_REGISTRY["model_default"].default
    # Update qua set_setting
    set_setting("model_default", "openai/gpt-4o", "tester", db=session)
    # Phải thấy giá trị mới ngay (không stale cache)
    assert get_setting("model_default", db=session) == "openai/gpt-4o"


def test_set_setting_unknown_key_raises(session: Session):
    with pytest.raises(KeyError):
        set_setting("bogus_key", "value", "tester", db=session)


def test_get_all_settings_masks_api_key(session: Session):
    set_setting("api_key", "sk-or-v1-abcdefghijklmnop", "tester", db=session)
    all_settings = get_all_settings(db=session)
    api_entry = all_settings["api_key"]
    assert api_entry["is_secret"] is True
    assert api_entry["has_value"] is True
    assert "abcdefghijklmnop" not in api_entry["value"]  # full key không leak
    assert api_entry["value"].startswith("sk-o")  # 4 ký tự đầu
    assert api_entry["value"].endswith("mnop")  # 4 ký tự cuối


def test_get_all_settings_non_secret_returns_raw_value(session: Session):
    set_setting("model_default", "anthropic/claude-sonnet-4", "tester", db=session)
    all_settings = get_all_settings(db=session)
    assert all_settings["model_default"]["value"] == "anthropic/claude-sonnet-4"
    assert all_settings["model_default"]["is_secret"] is False


def test_get_all_settings_empty_secret_has_value_false(session: Session):
    # api_key chưa set
    all_settings = get_all_settings(db=session)
    assert all_settings["api_key"]["has_value"] is False
    assert all_settings["api_key"]["value"] == ""


def test_seed_defaults_populates_empty_db(session: Session):
    assert session.scalar(select(AiSetting).limit(1)) is None
    inserted = seed_defaults(db=session)
    assert inserted == len(SETTINGS_REGISTRY)
    rows = session.scalars(select(AiSetting)).all()
    assert {r.key for r in rows} == set(SETTINGS_REGISTRY.keys())
    assert all(r.updated_by == "seed" for r in rows)


def test_seed_defaults_is_idempotent(session: Session):
    seed_defaults(db=session)
    second_run = seed_defaults(db=session)
    assert second_run == 0
    rows = session.scalars(select(AiSetting)).all()
    assert len(rows) == len(SETTINGS_REGISTRY)


def test_seed_defaults_respects_env_override(session: Session, monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("AI_DAILY_BUDGET_USD", "50.0")
    monkeypatch.setenv("AI_ENABLED", "true")
    inserted = seed_defaults(db=session)
    assert inserted > 0
    assert get_setting("base_url", db=session) == "https://api.openai.com/v1"
    assert get_setting("daily_budget_usd", db=session) == 50.0
    assert get_setting("enabled", db=session) is True


def test_seed_defaults_env_partial_override(session: Session, monkeypatch):
    """Env không set → vẫn dùng registry default."""
    monkeypatch.setenv("AI_MODEL_DEFAULT", "openrouter/auto")
    seed_defaults(db=session)
    assert get_setting("model_default", db=session) == "openrouter/auto"
    # Không set env cho temperature → vẫn dùng default 0.2
    assert get_setting("temperature", db=session) == 0.2


def test_seed_defaults_skips_existing_keys(session: Session):
    # Pre-populate 1 key
    set_setting("base_url", "https://prior.example.com", "previous", db=session)
    inserted = seed_defaults(db=session)
    # Số insert = total - 1 (đã có base_url)
    assert inserted == len(SETTINGS_REGISTRY) - 1
    # Giá trị cũ phải được giữ
    assert get_setting("base_url", db=session) == "https://prior.example.com"


def test_setting_registry_has_all_required_keys():
    """Sanity check — đảm bảo plan keys đầy đủ."""
    required = {
        "enabled", "base_url", "api_key", "extra_headers",
        "model_default", "model_fast", "model_deep",
        "temperature", "max_tokens",
        "daily_budget_usd", "rate_limit_per_hour",
        "history_retention_days", "audit_retention_days",
        "prompt_cache_enabled", "request_timeout_s",
    }
    missing = required - set(SETTINGS_REGISTRY.keys())
    assert not missing, f"Missing settings in registry: {missing}"
