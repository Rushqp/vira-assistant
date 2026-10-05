"""Speech-to-text engines: Groq Whisper and Gemini (free APIs), and faster-whisper on the CPU.

Each engine turns an `Audio` (bytes as Telegram sends them: OGG/Opus voice, MP3, M4A …) into
a `Transcription`, and raises `LLMError` (same kinds as the AI models) when it can't.
"""

import asyncio
import base64
import gc
import os
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import openai
from loguru import logger

from app.llm.client import LLMError, proxied_http_client, strip_think, translate_error
from app.llm.models import PROVIDER_NAMES, model_name

GROQ_URL = "https://api.groq.com/openai/v1"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
API_TIMEOUT = 60  # seconds
GEMINI_MAX_SECONDS = 360  # inline audio must stay under the request size limit (~20 MB)
IDLE_RELEASE = 600  # seconds: an unused local Whisper model leaves RAM
SAMPLE_RATE = 16_000

# Whisper sometimes hears short Persian messages as Arabic or Urdu: those are retried as Persian.
EXPECTED_LANGUAGES = ("fa", "en")
_LANGUAGE_CODES = {"persian": "fa", "farsi": "fa", "english": "en"}

TRANSCRIBE_PROMPT = (
    "Transcribe the speech in this audio exactly as spoken, in its original language (usually "
    "Persian or English; write Persian in Persian script). Reply with the transcript only, "
    "without quotes or comments. If there is no speech, reply with nothing."
)


@dataclass
class Audio:
    data: bytes
    filename: str = "voice.ogg"
    mime: str = "audio/ogg"
    duration: int | None = None  # seconds, when Telegram tells


@dataclass
class Transcription:
    text: str
    language: str | None = None  # "fa", "en", …
    engine: str = ""  # label of the engine that transcribed it


def language_code(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    return _LANGUAGE_CODES.get(lowered, lowered)


def to_wav(data: bytes, rate: int = SAMPLE_RATE) -> bytes:
    """Any audio Telegram sends → mono 16-bit WAV (PyAV, installed with faster-whisper)."""
    import av  # bundled FFmpeg: no system packages needed

    pcm = bytearray()
    try:
        with av.open(BytesIO(data)) as container:
            resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)
            for frame in container.decode(audio=0):
                for chunk in resampler.resample(frame):
                    pcm += bytes(chunk.planes[0])[: chunk.samples * 2]
            for chunk in resampler.resample(None):  # flush
                pcm += bytes(chunk.planes[0])[: chunk.samples * 2]
    except (av.error.FFmpegError, IndexError, ValueError) as exc:
        raise LLMError("failed", f"unreadable audio: {exc}") from exc
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(bytes(pcm))
    return buffer.getvalue()


class _Engine:
    name = ""
    model = ""

    @property
    def id(self) -> str:
        return f"stt-{self.name}:{self.model}"

    @property
    def label(self) -> str:
        return engine_label(self.name, self.model)

    def accepts(self, audio: Audio) -> bool:
        return True

    async def close(self) -> None:
        return None


def engine_label(name: str, model: str) -> str:
    """`Whisper large-v3 · Groq`, `Gemini Flash · Gemini`, `Whisper small · Local`."""
    if name == "gemini":
        shown = model_name(name, model)
    else:
        shown = "Whisper " + model.removeprefix("whisper-")
    return f"{shown} · {PROVIDER_NAMES.get(name, name)}"


# --- Groq: OpenAI-compatible /audio/transcriptions ---


class GroqWhisper(_Engine):
    name = "groq"

    def __init__(
        self,
        api_key: str,
        model: str = "whisper-large-v3",
        client: Any = None,
        proxy: str | None = None,
    ) -> None:
        self.model = model
        self._client = client or openai.AsyncOpenAI(
            base_url=GROQ_URL,
            api_key=api_key,
            timeout=API_TIMEOUT,
            max_retries=0,
            http_client=proxied_http_client(proxy),
        )

    async def transcribe(self, audio: Audio) -> Transcription:
        result = await self._request(audio)
        if result.text and result.language not in EXPECTED_LANGUAGES:
            retry = await self._request(audio, "fa")
            if retry.text:
                return retry
        return result

    async def _request(self, audio: Audio, language: str | None = None) -> Transcription:
        extra = {"language": language} if language else {}
        try:
            response = await self._client.audio.transcriptions.create(
                model=self.model,
                file=(audio.filename, audio.data, audio.mime),
                response_format="verbose_json",
                temperature=0.0,
                **extra,
            )
        except openai.OpenAIError as exc:
            raise translate_error(exc, self.model) from exc
        detected = language_code(getattr(response, "language", None)) or language
        return Transcription((response.text or "").strip(), detected, self.label)

    async def close(self) -> None:
        await self._client.close()


# --- Gemini: audio in a chat completion ---


class GeminiAudio(_Engine):
    name = "gemini"

    def __init__(
        self, api_key: str, model: str, client: Any = None, proxy: str | None = None
    ) -> None:
        self.model = model
        self._client = client or openai.AsyncOpenAI(
            base_url=GEMINI_URL,
            api_key=api_key,
            timeout=API_TIMEOUT,
            max_retries=0,
            http_client=proxied_http_client(proxy),
        )

    def accepts(self, audio: Audio) -> bool:
        return audio.duration is None or audio.duration <= GEMINI_MAX_SECONDS

    async def transcribe(self, audio: Audio) -> Transcription:
        wav = await asyncio.to_thread(to_wav, audio.data)
        if len(wav) > GEMINI_MAX_SECONDS * SAMPLE_RATE * 2:
            raise LLMError("failed", "too long for inline audio")
        content = [
            {"type": "text", "text": TRANSCRIBE_PROMPT},
            {
                "type": "input_audio",
                "input_audio": {"data": base64.b64encode(wav).decode(), "format": "wav"},
            },
        ]
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": content}],
                temperature=0.0,
                reasoning_effort="low",
            )
        except openai.OpenAIError as exc:
            raise translate_error(exc, self.model) from exc
        text = strip_think(response.choices[0].message.content or "").strip()
        return Transcription(text.strip("\"'«»“” \n"), None, self.label)

    async def close(self) -> None:
        await self._client.close()


# --- faster-whisper on the CPU ---


def load_faster_whisper(model: str, download_root: str, proxy: str | None = None) -> Any:
    """Imported only when needed: heavy, with native libraries (the model downloads once).

    The download (Hugging Face, over HTTPS) honours HTTPS_PROXY, set here from API_PROXY. Only
    HTTPS: the local Ollama (plain HTTP) must never go through the proxy, also for a client
    created later (another local model chosen in 🤖 AI model)."""
    from faster_whisper import WhisperModel

    if proxy:
        os.environ.setdefault("HTTPS_PROXY", proxy)
    return WhisperModel(model, device="cpu", compute_type="int8", download_root=download_root)


class LocalWhisper(_Engine):
    """Loaded on first use; released from RAM after `IDLE_RELEASE` seconds without use."""

    name = "local"

    def __init__(
        self,
        model: str,
        download_root: str,
        loader=load_faster_whisper,
        clock: Callable[[], float] = time.monotonic,
        proxy: str | None = None,
    ) -> None:
        self.model = model
        self._proxy = proxy
        self._download_root = download_root
        self._loader = loader
        self._clock = clock
        self._whisper: Any = None
        self._lock = asyncio.Lock()
        self._busy = 0
        self._last_used = 0.0

    @property
    def loaded(self) -> bool:
        return self._whisper is not None

    async def transcribe(self, audio: Audio) -> Transcription:
        self._busy += 1
        try:
            whisper = await self._get()
            text, language = await asyncio.to_thread(self._run, whisper, audio.data)
        except LLMError:
            raise
        except Exception as exc:  # decoding or inference failed
            raise LLMError("failed", f"local Whisper: {exc}") from exc
        finally:
            self._busy -= 1
            self._last_used = self._clock()
        return Transcription(text, language, self.label)

    def release_if_idle(self, idle: float = IDLE_RELEASE) -> bool:
        """Free the model's RAM (0.5–1.6 GB) when it hasn't been used for `idle` seconds."""
        if self._whisper is None or self._busy or self._clock() - self._last_used < idle:
            return False
        self._whisper = None
        gc.collect()
        logger.info("Local Whisper {} released from memory (unused)", self.model)
        return True

    async def _get(self) -> Any:
        async with self._lock:
            if self._whisper is None:
                try:
                    self._whisper = await asyncio.to_thread(
                        self._loader, self.model, self._download_root, self._proxy
                    )
                except (ImportError, ValueError) as exc:  # not installed / unknown model
                    raise LLMError("model_missing", f"local Whisper: {exc}") from exc
                except Exception as exc:  # download failed, out of memory …
                    raise LLMError("unreachable", f"local Whisper: {exc}") from exc
            return self._whisper

    @staticmethod
    def _run(whisper: Any, data: bytes) -> tuple[str, str | None]:
        def once(language: str | None) -> tuple[str, str | None]:
            segments, info = whisper.transcribe(
                BytesIO(data),
                language=language,
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            return " ".join(s.text.strip() for s in segments).strip(), info.language

        text, language = once(None)
        if text and language not in EXPECTED_LANGUAGES:
            retry, _ = once("fa")
            if retry:
                return retry, "fa"
        return text, language
