"""ProviderChain: order, failover, cooldowns, tool support, and building from settings."""

import pytest

from app.config import Settings
from app.llm.client import LLMError, LLMResponse
from app.llm.providers import (
    COOLDOWN_RATE_LIMIT,
    ProviderChain,
    build_clients,
    describe_providers,
    local_supports_tools,
)


class StubClient:
    def __init__(self, name, errors=None, supports_tools=True, answer="ok"):
        self.name = name
        self.model = f"{name}-model"
        self.supports_tools = supports_tools
        self.errors = list(errors or [])
        self.answer = answer
        self.calls = 0

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
    assert (
        describe_providers(settings(gemini_api_key="g")) == "gemini-flash-latest → qwen3:4b (local)"
    )
    assert (
        describe_providers(settings(profile="remote", gemini_api_key="g")) == "gemini-flash-latest"
    )
