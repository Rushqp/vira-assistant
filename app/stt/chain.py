"""Speech engines in order (`STT_PROVIDERS`): free APIs first, local Whisper as the backup.

Like the AI models: an engine that fails is paused with a growing cooldown and the next one
transcribes; every change is a notice for the user (`drain_notices`, shown after the turn).
"""

import time
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from app.config import Settings
from app.llm.client import LLMError
from app.llm.failover import Failover, Notice
from app.stt.engines import (
    Audio,
    GeminiAudio,
    GroqWhisper,
    LocalWhisper,
    Transcription,
    engine_label,
)

KNOWN = ("groq", "gemini", "local")
MODELS_DIR = Path("data/models/whisper")  # on the data volume: downloaded once


def planned_engines(config: Settings) -> list[tuple[str, str]]:
    """(engine, model) in order, skipping engines without a key or model."""
    if not config.stt_enabled:
        return []
    planned = []
    for name in (p.strip().lower() for p in config.stt_providers.split(",") if p.strip()):
        if name == "groq" and config.provider_key("groq"):
            planned.append(("groq", config.groq_stt_model))
        elif name == "gemini" and config.provider_key("gemini"):
            planned.append(("gemini", config.provider_model("gemini")))
        elif name == "local" and config.effective_stt_model:
            planned.append(("local", config.effective_stt_model))
        elif name not in KNOWN:
            logger.warning("Unknown speech engine {!r} in STT_PROVIDERS (ignored)", name)
    return planned


def build_engines(config: Settings) -> list:
    engines: list = []
    for name, model in planned_engines(config):
        proxy = config.api_proxy
        if name == "groq":
            engines.append(GroqWhisper(config.provider_key("groq") or "", model, proxy=proxy))
        elif name == "gemini":
            engines.append(GeminiAudio(config.provider_key("gemini") or "", model, proxy=proxy))
        else:
            engines.append(LocalWhisper(model, str(MODELS_DIR), proxy=proxy))
    return engines


def describe_engines(config: Settings) -> str:
    """e.g. `Whisper large-v3 · Groq → Whisper small · Local` (no clients are created)."""
    return " → ".join(engine_label(name, model) for name, model in planned_engines(config))


class SpeechChain:
    def __init__(self, engines: list, clock: Callable[[], float] = time.monotonic) -> None:
        self.engines = engines
        self.failover = Failover(clock, task="voice")

    @classmethod
    def from_settings(cls, config: Settings) -> "SpeechChain":
        return cls(build_engines(config))

    @property
    def model(self) -> str:
        return " → ".join(e.label for e in self.engines) or "none"

    async def transcribe(self, audio: Audio) -> Transcription:
        last: LLMError | None = None
        for engine in self.failover.ready(self.engines):
            if not engine.accepts(audio):  # e.g. too long for inline audio: not a failure
                continue
            try:
                result = await engine.transcribe(audio)
            except LLMError as exc:
                self.failover.failed(engine, exc)
                last = exc
                continue
            self.failover.answered(engine, self.engines)
            return result
        self.failover.nothing_answered(self.engines)
        raise last or LLMError("unreachable", "no speech engine available")

    def drain_notices(self) -> list[Notice]:
        return self.failover.drain()

    async def release_idle(self) -> None:
        """Free the RAM of a local model that hasn't been used for a while (scheduler)."""
        for engine in self.engines:
            if isinstance(engine, LocalWhisper):
                engine.release_if_idle()

    async def close(self) -> None:
        for engine in self.engines:
            await engine.close()
