"""Application configuration loaded from environment variables / `.env`."""

from datetime import time
from enum import StrEnum
from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.parsers.datetime_parser import DayTimes
from app.llm.models import DEFAULT_MODELS


class Profile(StrEnum):
    LITE = "lite"
    STANDARD = "standard"
    FULL = "full"
    REMOTE = "remote"


class Calendar(StrEnum):
    JALALI = "jalali"
    GREGORIAN = "gregorian"


class Currency(StrEnum):
    TOMAN = "toman"
    RIAL = "rial"


# Default local models per hardware profile: (LLM model, Whisper model).
# lite: chat only (no tool calling) · standard / full: local agent with tool calling.
# Remote uses external APIs only; a custom endpoint needs LLM_MODEL.
PROFILE_DEFAULTS: dict[Profile, tuple[str, str]] = {
    Profile.LITE: ("gemma3:1b", "tiny"),
    Profile.STANDARD: ("qwen3:4b", "base"),
    Profile.FULL: ("qwen3:8b", "small"),
    Profile.REMOTE: ("", "base"),
}

# Default models of the free API providers (override with GEMINI_MODEL, GROQ_MODEL, …).
API_DEFAULT_MODELS = DEFAULT_MODELS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    bot_token: SecretStr
    owner_id: int
    telegram_proxy: str | None = None

    # Locale
    tz: str = "Asia/Tehran"
    default_calendar: Calendar = Calendar.JALALI
    currency: Currency = Currency.TOMAN

    # AI: providers are tried in this order; those without a key are skipped.
    # "local" = LLM_BASE_URL / LLM_MODEL (Ollama by default, or any OpenAI-compatible API).
    profile: Profile = Profile.STANDARD
    llm_providers: str = "gemini,groq,mistral,github,openrouter,local"
    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None
    groq_api_key: SecretStr | None = None
    groq_model: str | None = None
    mistral_api_key: SecretStr | None = None
    mistral_model: str | None = None
    github_token: SecretStr | None = None
    github_model: str | None = None
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str | None = None
    llm_base_url: str = "http://ollama:11434/v1"
    llm_model: str | None = None
    llm_api_key: SecretStr = SecretStr("ollama")
    local_tools: Literal["auto", "on", "off"] = "auto"  # tool calling with the local model
    llm_timeout: float = Field(default=180, gt=0)  # seconds; CPU inference can be slow
    chat_memory: int = Field(default=10, ge=0, le=50)  # previous messages sent as context
    chat_keep: int = Field(default=20, ge=1, le=200)  # previous chats kept in 🗂 Chats
    stt_enabled: bool = True
    stt_model: str | None = None

    # Reminders: default clock times for words like "morning" / «صبح»
    morning_time: time = time(9, 0)
    noon_time: time = time(12, 0)
    afternoon_time: time = time(16, 0)
    evening_time: time = time(19, 0)
    night_time: time = time(22, 0)
    morning_briefing_time: time = time(8, 0)  # daily list of today's reminders

    # Reports
    daily_report_time: time = time(22, 0)

    # Misc
    log_level: str = "INFO"
    database_url: str = Field(default="sqlite+aiosqlite:///data/vira.db")

    @field_validator(
        "telegram_proxy",
        "llm_model",
        "stt_model",
        "gemini_api_key",
        "gemini_model",
        "groq_api_key",
        "groq_model",
        "github_token",
        "github_model",
        "mistral_api_key",
        "mistral_model",
        "openrouter_api_key",
        "openrouter_model",
        mode="before",
    )
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("tz")
    @classmethod
    def _valid_tz(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone: {value!r}") from exc
        return value

    @model_validator(mode="after")
    def _remote_needs_a_brain(self) -> "Settings":
        if self.profile == Profile.REMOTE and not self.llm_model and not self.api_providers:
            raise ValueError(
                "PROFILE=remote needs an API key (GEMINI_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY, "
                "GITHUB_TOKEN, OPENROUTER_API_KEY) or LLM_MODEL for a custom endpoint"
            )
        return self

    def provider_key(self, name: str) -> str | None:
        secret = {
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
            "mistral": self.mistral_api_key,
            "github": self.github_token,
            "openrouter": self.openrouter_api_key,
        }.get(name)
        return secret.get_secret_value() if secret else None

    def provider_model(self, name: str) -> str:
        chosen = {
            "gemini": self.gemini_model,
            "groq": self.groq_model,
            "mistral": self.mistral_model,
            "github": self.github_model,
            "openrouter": self.openrouter_model,
        }
        return chosen.get(name) or API_DEFAULT_MODELS[name]

    @property
    def api_providers(self) -> list[str]:
        """Free API providers that have a key, in LLM_PROVIDERS order."""
        order = [p.strip().lower() for p in self.llm_providers.split(",")]
        return [p for p in order if p in API_DEFAULT_MODELS and self.provider_key(p)]

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    @property
    def day_times(self) -> DayTimes:
        return DayTimes(
            morning=self.morning_time,
            noon=self.noon_time,
            afternoon=self.afternoon_time,
            evening=self.evening_time,
            night=self.night_time,
        )

    @property
    def effective_llm_model(self) -> str:
        return self.llm_model or PROFILE_DEFAULTS[self.profile][0]

    @property
    def effective_stt_model(self) -> str:
        return self.stt_model or PROFILE_DEFAULTS[self.profile][1]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
