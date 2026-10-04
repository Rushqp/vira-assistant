"""Voice messages through the real dispatcher: transcribed first, then handled like typed text."""

from datetime import datetime

from aiogram.types import Chat, Message, User, VideoNote

from app import texts
from app.llm.client import LLMError
from app.stt.chain import SpeechChain
from tests.fakes import FakeSTT, calls, make_env, reply, tool, voice_message
from tests.test_stt import StubEngine


def voice_env(config, sessionmaker, text="", **stt_args):
    return make_env(config, sessionmaker, stt=FakeSTT(text, **stt_args))


async def test_voice_is_shown_and_then_acted_on(config, sessionmaker):
    env = voice_env(config, sessionmaker, "نون پنجاه هزار تومن")
    env.llm.script = [
        calls(
            tool("add_expenses", items=[{"description": "نون", "amount_text": "پنجاه هزار تومن"}])
        ),
        reply(""),
    ]
    await env.feed(voice_message())
    assert env.session.downloads == ["voice-1"]
    assert env.session.sent[0] == "🎙 «نون پنجاه هزار تومن»"
    assert "50,000 toman" in env.session.sent[-1]  # the saved-expense card
    user = env.llm.respond_calls[0][-1]["content"]
    assert user.endswith("نون پنجاه هزار تومن") and "Voice message" in user
    audio = env.stt.audio[0]
    assert (audio.filename, audio.mime, audio.duration) == ("voice.ogg", "audio/ogg", 3)


async def test_audio_files_and_captions(config, sessionmaker):
    env = voice_env(config, sessionmaker, "سلام")
    env.llm.script = [reply("سلام!"), reply("سلام!")]
    await env.feed(voice_message(kind="audio"))
    await env.feed(voice_message(kind="document", caption="این رو خلاصه کن"))
    assert [(a.filename, a.mime) for a in env.stt.audio] == [
        ("memo.mp3", "audio/mpeg"),
        ("memo.m4a", "audio/mp4"),
    ]
    assert env.llm.respond_calls[1][-1]["content"].endswith("این رو خلاصه کن\nسلام")


async def test_voice_answers_a_waiting_form(config, sessionmaker):
    # No model can use tools: the rule-based reminder form asks for the time, and a voice
    # message answers it just like typed text would.
    env = voice_env(config, sessionmaker, "فردا ساعت ۹ صبح")
    await env.send("یادم بنداز به مامان زنگ بزنم")
    asked = env.session.sent[-1]
    await env.feed(voice_message())
    assert env.session.sent[-2] == "🎙 «فردا ساعت ۹ صبح»"
    assert env.session.sent[-1] != asked and "مامان" in env.session.sent[-1]


async def test_refused_recordings(config, sessionmaker):
    env = voice_env(config, sessionmaker, "x")
    await env.feed(voice_message(duration=700))
    assert env.session.sent[-1] == texts.VOICE_TOO_LONG.format(minutes=12, limit=10)
    await env.feed(voice_message(size=30 * 1024 * 1024))
    assert env.session.sent[-1] == texts.VOICE_TOO_BIG
    assert env.session.downloads == [] and env.stt.audio == []


async def test_voice_turned_off(config, sessionmaker):
    off = make_env(config.model_copy(update={"stt_enabled": False}), sessionmaker, stt=FakeSTT())
    await off.feed(voice_message())
    assert off.session.sent[-1] == texts.VOICE_OFF


async def test_voice_without_engines(config, sessionmaker):
    env = make_env(config, sessionmaker, stt=SpeechChain([]))
    await env.feed(voice_message())
    assert env.session.sent[-1] == texts.VOICE_NO_ENGINE


async def test_failed_recording(config, sessionmaker):
    failing = voice_env(config, sessionmaker, error=LLMError("unreachable"))
    await failing.feed(voice_message())
    assert failing.session.sent[-1] == texts.VOICE_FAILED


async def test_silent_recording(config, sessionmaker):
    env = voice_env(config, sessionmaker, "")
    await env.feed(voice_message())
    assert env.session.sent[-1] == texts.VOICE_EMPTY
    assert env.llm.respond_calls == []


async def test_engine_switch_is_reported(config, sessionmaker):
    stt = SpeechChain([StubEngine("groq", error=LLMError("rate_limited")), StubEngine("gemini")])
    env = make_env(config, sessionmaker, stt=stt)
    env.llm.script = [reply("👍")]
    await env.feed(voice_message())
    assert env.session.sent[0] == "🎙 «ok»"
    assert env.session.sent[-1].startswith(
        texts.VOICE_SWITCHED.format(previous="GROQ", reason="free quota used up", model="GEMINI")
    )


async def test_settings_show_the_voice_engines(config, sessionmaker):
    env = make_env(config, sessionmaker, stt=SpeechChain([StubEngine("groq"), StubEngine("local")]))
    await env.send(texts.BTN_SETTINGS)
    assert "🎙 Voice: <b>on (GROQ → LOCAL)</b>" in env.session.sent[-1]


async def test_round_videos_are_not_transcribed(config, sessionmaker):
    env = voice_env(config, sessionmaker, "x")
    note = VideoNote(file_id="vn", file_unique_id="vn1", length=240, duration=5)
    await env.feed(
        Message(
            message_id=1,
            date=datetime.now(),
            chat=Chat(id=1001, type="private"),
            from_user=User(id=1001, is_bot=False, first_name="T"),
            video_note=note,
        )
    )
    assert env.session.sent[-1] == texts.UNSUPPORTED_MESSAGE and env.stt.audio == []
