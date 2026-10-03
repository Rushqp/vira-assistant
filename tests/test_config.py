from datetime import time

import pytest
from pydantic import ValidationError

from app.config import Calendar, Profile, Settings


def make(**overrides) -> Settings:
    return Settings(_env_file=None, bot_token="1:x", owner_id=1, **overrides)


@pytest.mark.parametrize(
    ("profile", "llm", "stt"),
    [
        (Profile.LITE, "gemma3:1b", "tiny"),
        (Profile.STANDARD, "qwen3:4b", "base"),
        (Profile.FULL, "qwen3:8b", "small"),
    ],
)
def test_profile_defaults(profile, llm, stt):
    s = make(profile=profile)
    assert s.effective_llm_model == llm
    assert s.effective_stt_model == stt


def test_explicit_models_override_profile():
    s = make(profile="lite", llm_model="llama3.2:3b", stt_model="medium")
    assert s.effective_llm_model == "llama3.2:3b"
    assert s.effective_stt_model == "medium"


def test_empty_strings_mean_unset():
    s = make(llm_model="", stt_model="  ", telegram_proxy="")
    assert s.llm_model is None
    assert s.stt_model is None
    assert s.telegram_proxy is None
    assert s.effective_llm_model == "qwen3:4b"


def test_defaults():
    s = make()
    assert s.profile == Profile.STANDARD
    assert s.default_calendar == Calendar.JALALI
    assert s.daily_report_time == time(22, 0)
    assert s.timezone.key == "Asia/Tehran"


def test_env_values_are_parsed(monkeypatch):
    monkeypatch.setenv("DEFAULT_CALENDAR", "gregorian")
    monkeypatch.setenv("DAILY_REPORT_TIME", "21:30")
    monkeypatch.setenv("STT_ENABLED", "false")
    s = make()
    assert s.default_calendar == Calendar.GREGORIAN
    assert s.daily_report_time == time(21, 30)
    assert s.stt_enabled is False


def test_invalid_timezone_rejected():
    with pytest.raises(ValidationError):
        make(tz="Mars/Olympus")


def test_invalid_profile_rejected():
    with pytest.raises(ValidationError):
        make(profile="huge")


def test_remote_profile_needs_an_api_key_or_model():
    with pytest.raises(ValidationError, match="PROFILE=remote needs an API key"):
        make(profile="remote")
    s = make(profile="remote", llm_model="gpt-4o-mini", llm_base_url="https://api.example.com/v1")
    assert s.effective_llm_model == "gpt-4o-mini"
    s = make(profile="remote", gemini_api_key="key")
    assert s.api_providers == ["gemini"]


def test_api_providers_and_models():
    s = make(gemini_api_key="g", groq_api_key="q", groq_model="qwen/qwen3-32b")
    assert s.api_providers == ["gemini", "groq"]
    assert s.provider_model("gemini") == "gemini-flash-latest"
    assert s.provider_model("groq") == "qwen/qwen3-32b"
    assert s.provider_key("github") is None
    assert make(gemini_api_key="  ").api_providers == []


def test_chat_memory_bounds():
    assert make(chat_memory=0).chat_memory == 0
    with pytest.raises(ValidationError):
        make(chat_memory=-1)
