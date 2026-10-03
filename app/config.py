"""Application configuration loaded from environment variables / `.env`."""

from datetime import time
from enum import StrEnum
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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


# Default models per hardware profile: (LLM model, Whisper model).
# Remote uses an external API; its model must be set explicitly via LLM_MODEL.
PROFILE_DEFAULTS: dict[Profile, tuple[str, str]] = {
    Profile.LITE: ("gemma3:1b", "tiny"),
    Profile.STANDARD: ("qwen2.5:3b", "base"),
    Profile.FULL: ("qwen2.5:7b", "small"),
    Profile.REMOTE: ("", "base"),
}


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

    # AI
    profile: Profile = Profile.STANDARD
    llm_base_url: str = "http://ollama:11434/v1"
    llm_model: str | None = None
    llm_api_key: SecretStr = SecretStr("ollama")
    stt_enabled: bool = True
    stt_model: str | None = None

    # Reports
    daily_report_time: time = time(22, 0)

    # Misc
    log_level: str = "INFO"
    database_url: str = Field(default="sqlite+aiosqlite:///data/vira.db")

    @field_validator("telegram_proxy", "llm_model", "stt_model", mode="before")
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

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    @property
    def effective_llm_model(self) -> str:
        return self.llm_model or PROFILE_DEFAULTS[self.profile][0]

    @property
    def effective_stt_model(self) -> str:
        return self.stt_model or PROFILE_DEFAULTS[self.profile][1]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
