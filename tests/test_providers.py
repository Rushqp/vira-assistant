"""ProviderChain: order, failover, cooldowns, tool support, and building from settings."""

import pytest

from app.config import Settings
from app.llm.client import LLMError, LLMResponse
from app.llm.providers import (
    COOLDOWN_BROKEN,
    COOLDOWN_RATE_LIMIT,
    Notice,
    ProviderChain,
    build_clients,
    describe_providers,
    local_supports_tools,
    missing_providers,
    model_options,
)


class StubClient:
    def __init__(self, name, errors=None, supports_tools=True, answer="ok", model=None):
        self.name = name
        self.model = model or f"{name}-model"
        self.supports_tools = supports_tools
        self.errors = list(errors or [])
        self.answer = answer
        self.calls = 0

    @property
    def id(self):
        return f"{self.name}:{self.model}"

    @property
    def label(self):
        return self.name.upper()

    def _maybe_fail(self):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)

    async def respond(self, messages, tools=None, on_text=None, temperature=0.3):
        self._maybe_fail()
        if on_text:
            await on_text(self.answer)
        return LLMResponse(content=self.answer, provider=self.name)

    async def stream_chat(self, messages):
        self._maybe_fail()
        yield self.answer

    async def complete_json(self, messages, schema, name="result"):
        self._maybe_fail()
        return {"from": self.name}

    async def check(self):
        return True

    async def close(self):
        pass


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


async def test_first_healthy_provider_answers():
    a, b = StubClient("a"), StubClient("b")
    chain = ProviderChain([a, b])  # type: ignore[list-item]
    response = await chain.respond([], tools=[{}])
    assert response.provider == "a" and b.calls == 0


async def test_failover_and_cooldown():
    clock = Clock()
    a = StubClient("a", errors=[LLMError("rate_limited", retry_after=None)])
    b = StubClient("b")
    chain = ProviderChain([a, b], clock=clock)  # type: ignore[list-item]

    assert (await chain.respond([], tools=[{}])).provider == "b"
    assert (await chain.respond([], tools=[{}])).provider == "b"  # a is cooling down
    assert a.calls == 1

    clock.now += COOLDOWN_RATE_LIMIT + 1
    assert (await chain.respond([], tools=[{}])).provider == "a"  # a is back


async def test_retry_after_is_honoured():
    clock = Clock()
    a = StubClient("a", errors=[LLMError("rate_limited", retry_after=5)])
    chain = ProviderChain([a, StubClient("b")], clock=clock)  # type: ignore[list-item]
    await chain.respond([], tools=[{}])
    clock.now += 6
    assert (await chain.respond([], tools=[{}])).provider == "a"


async def test_repeated_failures_back_off_longer():
    clock = Clock()
    a = StubClient("a", errors=[LLMError("unreachable"), LLMError("unreachable")])
    chain = ProviderChain([a, StubClient("b")], clock=clock)  # type: ignore[list-item]
    await chain.respond([], tools=[{}])
    clock.now += 31
    await chain.respond([], tools=[{}])  # a fails again → 60 s
    clock.now += 31
    assert (await chain.respond([], tools=[{}])).provider == "b"


async def test_agent_turns_skip_models_without_tools():
    chat_only = StubClient("local", supports_tools=False)
    chain = ProviderChain([chat_only])  # type: ignore[list-item]
    with pytest.raises(LLMError):
        await chain.respond([], tools=[{}])
    assert (await chain.respond([], tools=None)).provider == "local"  # plain chat is fine
    assert not chain.has_tool_provider()


async def test_all_failing_raises_the_last_error():
    chain = ProviderChain(  # type: ignore[list-item]
        [
            StubClient("a", errors=[LLMError("unreachable")]),
            StubClient("b", errors=[LLMError("failed")]),
        ]
    )
    with pytest.raises(LLMError) as exc:
        await chain.respond([], tools=[{}])
    assert exc.value.kind == "failed"


async def test_no_providers():
    with pytest.raises(LLMError):
        await ProviderChain([]).respond([], tools=[{}])


async def test_stream_and_json_fail_over():
    chain = ProviderChain(  # type: ignore[list-item]
        [
            StubClient("a", errors=[LLMError("unreachable"), LLMError("unreachable")]),
            StubClient("b"),
        ]
    )
    assert [p async for p in chain.stream_chat([])] == ["ok"]
    chain2 = ProviderChain(  # type: ignore[list-item]
        [StubClient("a", errors=[LLMError("rate_limited")]), StubClient("b")]
    )
    assert await chain2.complete_json([], {}) == {"from": "b"}


async def test_partial_answer_is_not_retried_elsewhere():
    class Breaks(StubClient):
        async def respond(self, messages, tools=None, on_text=None, temperature=0.3):
            await on_text("half an answer")
            raise LLMError("unreachable")

    shown = []

    async def on_text(piece):
        shown.append(piece)

    chain = ProviderChain([Breaks("a"), StubClient("b")])  # type: ignore[list-item]
    with pytest.raises(LLMError):
        await chain.respond([], tools=[{}], on_text=on_text)
    assert shown == ["half an answer"]


# --- Building from settings ---


def settings(**values) -> Settings:
    return Settings(_env_file=None, bot_token="1:x", owner_id=1, **values)


def test_build_clients_order_and_keys():
    clients = build_clients(settings(gemini_api_key="g", github_token="t"))
    assert [c.name for c in clients] == ["gemini", "github", "local"]
    gemini = clients[0]
    assert gemini.model == "gemini-flash-latest" and gemini.reasoning_effort == "low"
    assert clients[1].reasoning_effort is None
    local = clients[2]
    assert local.model == "qwen3:4b" and local.supports_tools and local.system_suffix == "/no_think"
    assert local.stream_tools


def test_groq_reasoning_only_for_gpt_oss():
    groq = build_clients(settings(groq_api_key="q", llm_providers="groq"))[0]
    assert groq.reasoning_effort == "low"
    llama = build_clients(
        settings(groq_api_key="q", groq_model="llama-3.3-70b", llm_providers="groq")
    )[0]
    assert llama.reasoning_effort is None


def test_lite_local_model_is_chat_only():
    local = build_clients(settings(profile="lite"))[-1]
    assert local.model == "gemma3:1b" and not local.supports_tools
    assert build_clients(settings(profile="lite", local_tools="on"))[-1].supports_tools


def test_remote_without_custom_model_has_no_local_provider():
    clients = build_clients(settings(profile="remote", gemini_api_key="g"))
    assert [c.name for c in clients] == ["gemini"]


@pytest.mark.parametrize(
    ("model", "expected"),
    [("qwen3:4b", True), ("gemma3:1b", False), ("gemma4:e4b", True), ("llama3.1:8b", True)],
)
def test_local_tool_support(model, expected):
    assert local_supports_tools(model, "auto") is expected


def test_describe_providers():
    assert describe_providers(settings(gemini_api_key="g")) == (
        "Gemini Flash · Gemini → qwen3:4b · Local"
    )
    assert describe_providers(settings(profile="remote", gemini_api_key="g")) == (
        "Gemini Flash · Gemini"
    )


# --- More providers ---


def test_mistral_and_openrouter_presets():
    clients = build_clients(
        settings(mistral_api_key="m", openrouter_api_key="o", llm_providers="mistral,openrouter")
    )
    assert [(c.name, c.model) for c in clients] == [
        ("mistral", "mistral-small-latest"),
        ("openrouter", "openrouter/free"),
    ]
    assert clients[1]._client.default_headers["X-Title"] == "Vira Assistant"
    assert [c.label for c in clients] == ["Mistral Small · Mistral", "OpenRouter Free · OpenRouter"]


def test_model_options_and_missing_keys():
    config = settings(groq_api_key="q", groq_model="custom-model")
    options = model_options(config, local_models=["qwen3:4b", "llama3.2:3b", "nomic-embed-text"])
    assert options[0] == ("groq", "custom-model")  # the .env model comes first
    assert ("groq", "openai/gpt-oss-20b") in options
    assert ("local", "llama3.2:3b") in options and ("local", "nomic-embed-text") not in options
    assert not any(p == "gemini" for p, _ in options)
    assert missing_providers(config) == ["gemini", "mistral", "github", "openrouter"]


# --- Preference ---


def test_preferred_model_goes_first_and_auto_restores_the_order():
    a, b = StubClient("a"), StubClient("b")
    created = []

    def factory(provider, model):
        client = StubClient(provider, model=model)
        created.append(client)
        return client

    chain = ProviderChain([a, b], factory=factory)  # type: ignore[list-item]
    chain.prefer("b", "b-model")
    assert [c.name for c in chain.clients] == ["b", "a"]  # the existing client moves first
    chain.prefer("a", "other-model")
    assert [c.id for c in chain.clients] == ["a:other-model", "a:a-model", "b:b-model"]
    assert chain.preference == ("a", "other-model") and created
    chain.prefer(None)
    assert [c.name for c in chain.clients] == ["a", "b"] and chain.preference is None


# --- Notices ---


async def test_switch_and_restore_notices():
    clock = Clock()
    a = StubClient("a", errors=[LLMError("rate_limited")])
    b = StubClient("b")
    chain = ProviderChain([a, b], clock=clock)  # type: ignore[list-item]

    await chain.respond([], tools=[{}])  # a fails → b answers
    [notice] = chain.drain_notices()
    assert (notice.kind, notice.previous, notice.model, notice.reason) == (
        "switched",
        "A",
        "B",
        "rate_limited",
    )
    assert notice.retry_in == pytest.approx(COOLDOWN_RATE_LIMIT)

    await chain.respond([], tools=[{}])  # still b: nothing new
    assert chain.drain_notices() == []

    clock.now += COOLDOWN_RATE_LIMIT + 1
    await chain.respond([], tools=[{}])  # a is back
    [notice] = chain.drain_notices()
    assert (notice.kind, notice.model) == ("restored", "A")


async def test_down_notice_once_then_restored():
    clock = Clock()
    a = StubClient("a", errors=[LLMError("unreachable"), LLMError("unreachable")])
    chain = ProviderChain([a], clock=clock)  # type: ignore[list-item]
    with pytest.raises(LLMError):
        await chain.respond([], tools=[{}])
    with pytest.raises(LLMError):
        await chain.respond([], tools=[{}])  # paused: still down, no second notice
    [notice] = chain.drain_notices()
    assert notice.kind == "down" and notice.reasons == {"A": "unreachable"}

    clock.now += 1000
    a.errors = []
    await chain.respond([], tools=[{}])
    [notice] = chain.drain_notices()
    assert (notice.kind, notice.model) == ("restored", "A")


async def test_chat_only_setups_do_not_report_outages():
    chain = ProviderChain([StubClient("local", supports_tools=False)])  # type: ignore[list-item]
    with pytest.raises(LLMError):
        await chain.respond([], tools=[{}])
    assert chain.drain_notices() == []


async def test_plain_chat_reports_only_in_chat_only_setups():
    # With a tool-capable model, plain chat only runs during an outage the agent turn already
    # reported: no second notice.
    chain = ProviderChain([StubClient("a", errors=[LLMError("unreachable")]), StubClient("b")])  # type: ignore[list-item]
    assert await chain.chat([]) == "ok"
    assert chain.drain_notices() == []
    # A chat-only setup has no agent turns, so plain chat reports.
    local = StubClient("local", supports_tools=False, errors=[LLMError("unreachable")])
    chain = ProviderChain([local])  # type: ignore[list-item]
    with pytest.raises(LLMError):
        await chain.chat([])
    [notice] = chain.drain_notices()
    assert notice.kind == "down" and notice.reasons == {"LOCAL": "unreachable"}


async def test_preference_change_starts_fresh():
    a, b = StubClient("a"), StubClient("b")
    chain = ProviderChain([a, b])  # type: ignore[list-item]
    await chain.respond([], tools=[{}])
    chain.prefer("b", "b-model")
    await chain.respond([], tools=[{}])
    assert chain.drain_notices() == []  # choosing a model is not an outage


def test_drain_keeps_one_notice_per_kind():
    chain = ProviderChain([])
    chain.notices = [Notice("down"), Notice("down"), Notice("restored", model="X")]
    assert [n.kind for n in chain.drain_notices()] == ["down", "restored"]
    assert chain.drain_notices() == []


# --- Cooldowns ---


async def test_cooldowns_by_error_kind():
    clock = Clock()
    a = StubClient(
        "a", errors=[LLMError("rate_limited"), LLMError("rate_limited"), LLMError("auth")]
    )
    chain = ProviderChain([a, StubClient("b")], clock=clock)  # type: ignore[list-item]
    await chain.respond([], tools=[{}])
    assert chain.status()[0].retry_in == pytest.approx(60)
    clock.now += 61
    await chain.respond([], tools=[{}])
    assert chain.status()[0].retry_in == pytest.approx(120)  # quota again: longer pause
    clock.now += 121
    await chain.respond([], tools=[{}])
    status = chain.status()[0]
    assert status.reason == "auth" and status.retry_in == pytest.approx(COOLDOWN_BROKEN)
    assert chain.status()[1].answering
