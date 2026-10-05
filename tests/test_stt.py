"""Speech to text: the engines (with fake API clients), the chain's failover, and settings."""

import base64
import wave
from io import BytesIO
from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import SecretStr

from app.config import Profile
from app.llm.client import LLMError
from app.stt.chain import SpeechChain, describe_engines, planned_engines
from app.stt.engines import (
    Audio,
    GeminiAudio,
    GroqWhisper,
    LocalWhisper,
    Transcription,
    engine_label,
    to_wav,
)


def wav_bytes(seconds: float = 0.5, rate: int = 8000) -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"\x00\x01" * int(seconds * rate))
    return buffer.getvalue()


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


# --- Groq ---


class FakeTranscriptions:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def groq_with(*responses) -> tuple[GroqWhisper, FakeTranscriptions]:
    transcriptions = FakeTranscriptions(*responses)
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=transcriptions))
    return GroqWhisper("key", client=client), transcriptions


async def test_groq_sends_the_voice_as_it_is():
    groq, calls = groq_with(SimpleNamespace(text=" فردا ساعت ۲ دکتر دارم ", language="persian"))
    result = await groq.transcribe(Audio(b"ogg", "voice.ogg", "audio/ogg", 3))
    assert result == Transcription("فردا ساعت ۲ دکتر دارم", "fa", "Whisper large-v3 · Groq")
    [call] = calls.calls
    assert call["model"] == "whisper-large-v3" and call["file"] == (
        "voice.ogg",
        b"ogg",
        "audio/ogg",
    )
    assert call["response_format"] == "verbose_json" and "language" not in call


async def test_groq_retries_persian_heard_as_another_language():
    groq, calls = groq_with(
        SimpleNamespace(text="فردا", language="arabic"),
        SimpleNamespace(text="فردا ساعت ۲", language="persian"),
    )
    result = await groq.transcribe(Audio(b"ogg"))
    assert result.text == "فردا ساعت ۲" and calls.calls[1]["language"] == "fa"


async def test_groq_errors_become_llm_errors():
    request = httpx.Request("POST", "https://api.groq.com")
    groq, _ = groq_with(openai.APIConnectionError(request=request))
    with pytest.raises(LLMError) as error:
        await groq.transcribe(Audio(b"ogg"))
    assert error.value.kind == "unreachable"


# --- Gemini ---


class FakeCompletions:
    def __init__(self, text: str):
        self.text = text
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.text)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


async def test_gemini_gets_wav_audio_in_the_chat():
    completions = FakeCompletions("«remind me tomorrow»\n")
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    gemini = GeminiAudio("key", "gemini-flash-latest", client=client)
    result = await gemini.transcribe(Audio(wav_bytes(), "voice.wav", "audio/wav", 1))
    assert result.text == "remind me tomorrow" and result.engine == "Gemini Flash · Gemini"
    [content] = completions.calls[0]["messages"]
    audio = content["content"][1]["input_audio"]
    assert audio["format"] == "wav" and base64.b64decode(audio["data"])[:4] == b"RIFF"
    assert not gemini.accepts(Audio(b"x", duration=400))  # too long for inline audio


def test_audio_is_converted_to_16khz_mono_wav():
    with wave.open(BytesIO(to_wav(wav_bytes(seconds=1, rate=8000)))) as out:
        assert (out.getnchannels(), out.getframerate(), out.getsampwidth()) == (1, 16000, 2)
        assert out.getnframes() == pytest.approx(16000, abs=400)
    with pytest.raises(LLMError):
        to_wav(b"not audio at all")


# --- Local Whisper ---


class FakeWhisper:
    def __init__(self, *results):
        self.results = list(results)
        self.languages: list = []

    def transcribe(self, audio, language=None, **kwargs):
        self.languages.append(language)
        text, detected = self.results.pop(0)
        return [SimpleNamespace(text=f" {text} ")], SimpleNamespace(language=detected)


async def test_local_whisper_loads_once_and_retries_persian():
    loads = []
    whisper = FakeWhisper(("salam", "ar"), ("سلام", "fa"), ("hello", "en"))

    def loader(model, root, proxy=None):
        loads.append((model, root))
        return whisper

    engine = LocalWhisper("small", "models", loader=loader)
    assert (await engine.transcribe(Audio(b"ogg"))).text == "سلام"
    assert (await engine.transcribe(Audio(b"ogg"))).language == "en"
    assert loads == [("small", "models")] and whisper.languages == [None, "fa", None]


async def test_local_whisper_not_installed():
    def loader(model, root, proxy=None):
        raise ImportError("ctranslate2")

    with pytest.raises(LLMError) as error:
        await LocalWhisper("small", "models", loader=loader).transcribe(Audio(b"ogg"))
    assert error.value.kind == "model_missing"


# --- The chain ---


class StubEngine:
    def __init__(self, name, *, error=None, text="ok", max_seconds=None):
        self.name, self.model = name, f"{name}-model"
        self.error, self.text, self.max_seconds = error, text, max_seconds
        self.calls = 0

    @property
    def id(self):
        return f"stt-{self.name}"

    @property
    def label(self):
        return self.name.upper()

    def accepts(self, audio):
        return self.max_seconds is None or (audio.duration or 0) <= self.max_seconds

    async def transcribe(self, audio):
        self.calls += 1
        if self.error:
            raise self.error
        return Transcription(self.text, "fa", self.label)

    async def close(self):
        pass


async def test_failover_with_notices():
    clock = Clock()
    groq = StubEngine("groq", error=LLMError("rate_limited"))
    chain = SpeechChain([groq, StubEngine("gemini", text="سلام")], clock=clock)
    assert (await chain.transcribe(Audio(b"x"))).text == "سلام"
    [notice] = chain.drain_notices()
    assert (notice.kind, notice.task, notice.previous, notice.model) == (
        "switched", "voice", "GROQ", "GEMINI",
    )  # fmt: skip

    groq.error = None
    clock.now += 61  # the quota pause is over
    await chain.transcribe(Audio(b"x"))
    [notice] = chain.drain_notices()
    assert (notice.kind, notice.model) == ("restored", "GROQ")


async def test_nothing_works():
    chain = SpeechChain([StubEngine("groq", error=LLMError("auth"))])
    with pytest.raises(LLMError):
        await chain.transcribe(Audio(b"x"))
    with pytest.raises(LLMError):  # paused for an hour: not tried again
        await chain.transcribe(Audio(b"x"))
    assert chain.engines[0].calls == 1
    [notice] = chain.drain_notices()
    assert notice.kind == "down" and notice.reasons == {"GROQ": "auth"}


async def test_engines_that_cannot_take_the_audio_are_skipped():
    gemini = StubEngine("gemini", max_seconds=360)
    chain = SpeechChain([gemini, StubEngine("local", text="long")])
    assert (await chain.transcribe(Audio(b"x", duration=500))).text == "long"
    assert gemini.calls == 0 and chain.drain_notices()[0].kind == "switched"


# --- From the settings ---


def test_planned_engines(config):
    keys = {"groq_api_key": SecretStr("q"), "gemini_api_key": SecretStr("g")}
    standard = config.model_copy(update=keys)
    assert planned_engines(standard) == [
        ("groq", "whisper-large-v3"),
        ("gemini", "gemini-flash-latest"),
        ("local", "small"),
    ]
    assert describe_engines(standard) == (
        "Whisper large-v3 · Groq → Gemini Flash · Gemini → Whisper small · Local"
    )
    lite = config.model_copy(update={**keys, "profile": Profile.LITE})
    assert [name for name, _ in planned_engines(lite)] == ["groq", "gemini"]  # no local on 2 GB
    assert planned_engines(config.model_copy(update={"stt_enabled": False})) == []
    custom = config.model_copy(update={"stt_providers": "local,groq", "stt_model": "medium"})
    assert planned_engines(custom) == [("local", "medium")]  # no Groq key


def test_engine_labels():
    assert engine_label("groq", "whisper-large-v3-turbo") == "Whisper large-v3-turbo · Groq"
    assert engine_label("local", "large-v3-turbo") == "Whisper large-v3-turbo · Local"
