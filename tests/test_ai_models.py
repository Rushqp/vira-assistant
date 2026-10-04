"""🤖 AI model menu (/model, ⚙️ Settings), model switch notices, and the saved choice."""

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText
from pydantic import SecretStr

from app import texts
from app.bot.handlers import ai_models
from app.bot.keyboards.inline import AiCb
from app.llm.client import LLMError
from app.llm.models import model_label
from app.llm.providers import ProviderChain
from app.main import apply_saved_model
from app.services.settings import SettingsService
from tests.fakes import FakeLLM, make_env, reply


class ApiModel:
    """One model inside a real ProviderChain: answers with its id, or fails with `error`."""

    def __init__(self, name, model, *, supports_tools=True, error=None):
        self.name, self.model, self.supports_tools = name, model, supports_tools
        self.error = error

    @property
    def id(self):
        return f"{self.name}:{self.model}"

    @property
    def label(self):
        return model_label(self.name, self.model)

    async def respond(self, messages, tools=None, on_text=None, temperature=0.3):
        if self.error:
            raise self.error
        return reply(f"answer from {self.model}")

    async def stream_chat(self, messages):
        if self.error:
            raise self.error
        yield f"chat from {self.model}"

    async def complete_json(self, messages, schema, name="result"):
        raise self.error or LLMError("failed")

    async def list_models(self):
        return ["qwen3:4b", "llama3.2:3b", "nomic-embed-text:latest"]

    async def check(self):
        return self.error is None

    async def close(self):
        pass


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def keyed(config):
    """Gemini and Groq keys, plus the local qwen3:4b of the standard profile."""
    return config.model_copy(
        update={"gemini_api_key": SecretStr("g"), "groq_api_key": SecretStr("q")}
    )


def chain(clock=None, gemini=None, groq=None, local=None) -> ProviderChain:
    """Gemini → Groq → local, each failing with the given error (None = answers)."""
    models = [
        ApiModel("gemini", "gemini-flash-latest", error=gemini),
        ApiModel("groq", "openai/gpt-oss-120b", error=groq),
        ApiModel("local", "qwen3:4b", error=local),
    ]
    return ProviderChain(models, clock=clock or Clock(), factory=lambda p, m: ApiModel(p, m))  # type: ignore[arg-type,list-item]


def buttons(env) -> list[str]:
    return [b.text for row in env.session.markup.inline_keyboard for b in row]


async def saved_choice(sessionmaker, config):
    async with sessionmaker() as session:
        return await SettingsService(session, config.default_calendar).get_ai_model()


# --- The menu ---


async def test_menu_shows_the_order_and_every_model(keyed, sessionmaker):
    env = make_env(keyed, sessionmaker, chain())
    await env.send("/model")
    text = env.session.sent[-1]
    assert texts.AI_TITLE in text and texts.AI_MODE_AUTO in text
    assert "1. ✅ Gemini Flash · Gemini" in text and "3. ✅ qwen3:4b · Local" in text
    assert "MISTRAL_API_KEY, GITHUB_TOKEN, OPENROUTER_API_KEY" in text  # more free models
    labels = buttons(env)
    assert labels[0] == texts.BTN_SELECTED + texts.BTN_AI_AUTO
    assert {"Gemini Flash", "Gemini Flash-Lite", "GPT-OSS 20B", "Llama 3.3 70B"} <= set(labels)
    assert {"qwen3:4b (local)", "llama3.2:3b (local)"} <= set(labels)
    assert not any("embed" in label for label in labels)


async def test_paused_models_show_why_and_until_when(keyed, sessionmaker):
    llm = chain(gemini=LLMError("rate_limited"))
    env = make_env(keyed, sessionmaker, llm)
    await env.send("hello")  # Gemini fails, Groq answers
    await env.send("/model")
    text = env.session.sent[-1]
    assert "1. ⏸ Gemini Flash · Gemini — free quota used up, retry at" in text
    assert texts.AI_ANSWERING.format(model="GPT-OSS 120B · Groq") in text


async def test_choosing_a_model_puts_it_first_and_saves_it(keyed, sessionmaker):
    llm = chain()
    env = make_env(keyed, sessionmaker, llm)
    await env.send("/model")
    await env.press(env.button("GPT-OSS 120B"))
    assert llm.preference == ("groq", "openai/gpt-oss-120b")
    assert env.session.alerts[-1] == texts.AI_CHOSEN.format(model="GPT-OSS 120B · Groq")
    assert texts.AI_MODE_PREFERRED.format(model="GPT-OSS 120B · Groq") in env.session.edits[-1]
    assert texts.BTN_SELECTED + "GPT-OSS 120B" in buttons(env)
    assert await saved_choice(sessionmaker, keyed) == ("groq", "openai/gpt-oss-120b")

    await env.send("hello")
    assert env.session.sent[-1] == "answer from openai/gpt-oss-120b"  # no notice: user's choice

    await env.send("/model")
    await env.press(env.button(texts.BTN_AI_AUTO))
    assert llm.preference is None and env.session.alerts[-1] == texts.AI_AUTO_CHOSEN
    assert await saved_choice(sessionmaker, keyed) is None
    await env.send("hello")
    assert env.session.sent[-1] == "answer from gemini-flash-latest"


async def test_any_model_of_a_provider_can_be_chosen(keyed, sessionmaker):
    llm = chain()
    env = make_env(keyed, sessionmaker, llm)
    await env.send("/model")
    await env.press(env.button("llama3.2:3b"))
    assert [c.id for c in llm.clients][:2] == ["local:llama3.2:3b", "gemini:gemini-flash-latest"]
    await env.send("hello")
    assert env.session.sent[-1] == "answer from llama3.2:3b"


async def test_out_of_date_menu_is_refreshed(keyed, sessionmaker):
    env = make_env(keyed, sessionmaker, chain())
    await env.press(AiCb(action="pick", index=3).pack())  # e.g. a menu from before a restart
    assert env.session.alerts[-1] == texts.AI_MENU_EXPIRED
    assert texts.AI_TITLE in env.session.edits[-1]


@pytest.mark.parametrize("llm", [ProviderChain([]), FakeLLM()], ids=["no-models", "plain-client"])
async def test_without_models_the_menu_explains_basic_mode(config, sessionmaker, llm):
    env = make_env(config, sessionmaker, llm)
    await env.send("/model")
    assert env.session.sent[-1] == texts.AI_NONE


async def test_settings_show_the_live_order_and_open_the_menu(keyed, sessionmaker):
    llm = chain()
    llm.prefer("groq", "openai/gpt-oss-120b")
    env = make_env(keyed, sessionmaker, llm)
    await env.send(texts.BTN_SETTINGS)
    assert "GPT-OSS 120B · Groq → Gemini Flash · Gemini → qwen3:4b · Local" in env.session.sent[-1]
    await env.press(env.button(texts.BTN_AI_MODEL))
    assert texts.AI_TITLE in env.session.sent[-1]


async def test_pressing_the_same_choice_again_is_harmless():
    class Shown:  # Telegram refuses an edit that changes nothing
        async def edit_text(self, text, reply_markup=None):
            method = EditMessageText(text=text)
            raise TelegramBadRequest(method, "Bad Request: message is not modified")

    await ai_models._edit(Shown(), "same text", None)  # type: ignore[arg-type]


# --- Notices ---


async def test_switch_notice_follows_the_answer(keyed, sessionmaker):
    env = make_env(keyed, sessionmaker, chain(gemini=LLMError("rate_limited")))
    await env.send("hello")
    answer, notice = env.session.sent[-2:]
    assert answer == "answer from openai/gpt-oss-120b"
    assert notice.startswith(
        texts.AI_SWITCHED.format(
            previous="Gemini Flash · Gemini",
            reason="free quota used up",
            model="GPT-OSS 120B · Groq",
        )
    )
    assert "I'll try it again at" in notice

    await env.send("hello again")  # Groq again: nothing new to say
    assert env.session.sent[-1] == "answer from openai/gpt-oss-120b"


async def test_outage_is_reported_once_before_basic_mode_then_recovery(keyed, sessionmaker):
    clock = Clock()
    down = LLMError("unreachable")
    llm = chain(clock, gemini=down, groq=down, local=down)
    env = make_env(keyed, sessionmaker, llm)
    await env.send("hello")
    assert env.session.sent[0].startswith("⚠️ No AI model can handle requests right now")
    assert "Gemini Flash · Gemini: not reachable" in env.session.sent[0]
    assert len(env.session.sent) == 2  # the notice, then basic mode's answer (an error here)

    await env.send("hello")  # still down: no repeated notice
    assert sum(t.startswith("⚠️ No AI model") for t in env.session.sent) == 1

    for model in llm.base:
        model.error = None
    clock.now += 3600
    await env.send("hello")
    assert env.session.sent[-2:] == [
        "answer from gemini-flash-latest",
        texts.AI_RESTORED.format(model="Gemini Flash · Gemini"),
    ]


# --- Saved choice ---


async def test_saved_choice_is_used_after_a_restart(keyed, sessionmaker):
    async with sessionmaker() as session:
        await SettingsService(session, keyed.default_calendar).set_ai_model(
            "groq", "openai/gpt-oss-20b"
        )
    llm = chain()
    await apply_saved_model(llm, sessionmaker, keyed)
    assert llm.preference == ("groq", "openai/gpt-oss-20b")


async def test_unusable_saved_choice_falls_back_to_auto(config, sessionmaker):
    async with sessionmaker() as session:
        await SettingsService(session, config.default_calendar).set_ai_model(
            "mistral", "mistral-small-latest"
        )
    llm = ProviderChain.from_settings(config)  # no MISTRAL_API_KEY
    await apply_saved_model(llm, sessionmaker, config)
    assert llm.preference is None
    await llm.close()
