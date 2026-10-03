"""Ordered LLM providers with failover: free APIs first, the local model last.

`ProviderChain` exposes the same methods as `LLMClient` (`respond`, `stream_chat`, `chat`,
`complete_json`, `check`, `close`), so it can be used anywhere a single client was used.

A provider that fails (connection error, timeout, 429, 5xx, empty or invalid answer) is put on
cooldown and the next one is tried. A provider without tool support is skipped for agent turns.
"""

import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.config import Profile, Settings
from app.llm.client import ChatMessage, LLMClient, LLMError, LLMResponse

# Free OpenAI-compatible APIs. Models are defaults; every one can be overridden in .env.
PRESETS: dict[str, dict[str, Any]] = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "reasoning_effort": "low",
    },
    "groq": {"base_url": "https://api.groq.com/openai/v1", "reasoning_effort": "low"},
    "github": {"base_url": "https://models.github.ai/inference"},
}
# Local model families without native tool calling (still fine for plain chat).
NO_TOOL_MODELS = ("gemma3", "gemma2", "gemma:", "phi3", "tinyllama")

COOLDOWN_RATE_LIMIT = 60.0
COOLDOWN_BASE = 30.0
COOLDOWN_MAX = 600.0


def local_supports_tools(model: str, setting: str) -> bool:
    if setting in ("on", "off"):
        return setting == "on"
    return not model.lower().startswith(NO_TOOL_MODELS)


def _suffix_for(model: str) -> str:
    return "/no_think" if "qwen3" in model.lower() else ""


def build_clients(config: Settings) -> list[LLMClient]:
    """Clients in the order of LLM_PROVIDERS; providers without a key / model are skipped."""
    clients: list[LLMClient] = []
    for name in [p.strip().lower() for p in config.llm_providers.split(",") if p.strip()]:
        if name in PRESETS:
            key = config.provider_key(name)
            if not key:
                continue
            model = config.provider_model(name)
            clients.append(
                LLMClient(
                    PRESETS[name]["base_url"],
                    key,
                    model,
                    timeout=min(config.llm_timeout, 60),
                    name=name,
                    reasoning_effort=PRESETS[name].get("reasoning_effort")
                    if "gpt-oss" in model or name == "gemini"
                    else None,
                    system_suffix=_suffix_for(model),
                )
            )
        elif name == "local":
            model = config.effective_llm_model
            if not model:
                continue
            clients.append(
                LLMClient(
                    config.llm_base_url,
                    config.llm_api_key.get_secret_value(),
                    model,
                    timeout=config.llm_timeout,
                    name="local",
                    supports_tools=local_supports_tools(model, config.local_tools),
                    stream_tools=config.profile != Profile.REMOTE,  # Ollama: show progress
                    system_suffix=_suffix_for(model),
                )
            )
        else:
            logger.warning("Unknown LLM provider {!r} in LLM_PROVIDERS (ignored)", name)
    return clients


@dataclass
class _Health:
    failures: int = 0
    until: float = 0.0  # monotonic time when the provider may be tried again


class ProviderChain:
    def __init__(self, clients: list[LLMClient], clock: Callable[[], float] = time.monotonic):
        self.clients = clients
        self._clock = clock
        self._health = {c.name: _Health() for c in clients}

    @classmethod
    def from_settings(cls, config: Settings) -> "ProviderChain":
        return cls(build_clients(config))

    # --- Health ---

    @property
    def model(self) -> str:
        return " → ".join(f"{c.name}:{c.model}" for c in self.clients) or "none"

    def available(self, need_tools: bool = False) -> list[LLMClient]:
        now = self._clock()
        ready = [c for c in self.clients if self._health[c.name].until <= now]
        if need_tools:
            ready = [c for c in ready if c.supports_tools]
        return ready

    def has_tool_provider(self) -> bool:
        return any(c.supports_tools for c in self.clients)

    def _succeeded(self, client: LLMClient) -> None:
        self._health[client.name] = _Health()

    def _failed(self, client: LLMClient, error: LLMError) -> None:
        health = self._health[client.name]
        health.failures += 1
        if error.kind == "rate_limited":
            pause = error.retry_after or COOLDOWN_RATE_LIMIT
        elif error.kind == "model_missing":
            pause = COOLDOWN_MAX
        else:
            pause = min(COOLDOWN_BASE * 2 ** (health.failures - 1), COOLDOWN_MAX)
        health.until = self._clock() + pause
        logger.warning("LLM {} failed ({}); paused for {:.0f}s", client.name, error, pause)

    def _candidates(self, need_tools: bool) -> list[LLMClient]:
        candidates = self.available(need_tools)
        if not candidates:
            raise LLMError("unreachable", "no LLM provider available")
        return candidates

    # --- LLMClient interface ---

    async def respond(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        on_text: Callable[[str], Any] | None = None,
        temperature: float = 0.3,
    ) -> LLMResponse:
        last: LLMError | None = None
        for client in self._candidates(need_tools=bool(tools)):
            shown: list[str] = []

            async def relay(piece: str, shown=shown) -> None:
                shown.append(piece)
                if on_text:
                    result = on_text(piece)
                    if hasattr(result, "__await__"):
                        await result

            try:
                response = await client.respond(messages, tools, relay, temperature)
            except LLMError as exc:
                self._failed(client, exc)
                last = exc
                if shown:  # part of an answer is already on screen: don't mix two answers
                    raise
                continue
            self._succeeded(client)
            return response
        raise last or LLMError("unreachable")

    async def stream_chat(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        last: LLMError | None = None
        for client in self._candidates(need_tools=False):
            started = False
            try:
                async for piece in client.stream_chat(messages):
                    started = True
                    yield piece
            except LLMError as exc:
                self._failed(client, exc)
                last = exc
                if started:
                    raise
                continue
            self._succeeded(client)
            return
        raise last or LLMError("unreachable")

    async def chat(self, messages: list[ChatMessage]) -> str:
        return "".join([piece async for piece in self.stream_chat(messages)])

    async def complete_json(
        self, messages: list[ChatMessage], schema: dict, name: str = "result"
    ) -> dict:
        last: LLMError | None = None
        for client in self._candidates(need_tools=False):
            try:
                result = await client.complete_json(messages, schema, name)
            except LLMError as exc:
                self._failed(client, exc)
                last = exc
                continue
            self._succeeded(client)
            return result
        raise last or LLMError("unreachable")

    async def check(self) -> bool:
        if not self.clients:
            logger.warning("No LLM provider configured: rule-based mode only")
            return False
        results = [await client.check() for client in self.clients]
        if not any(c.supports_tools for c in self.clients):
            logger.warning("No tool-capable model configured: the agent runs in rule-based mode")
        return any(results)

    async def close(self) -> None:
        for client in self.clients:
            await client.close()


def describe_providers(config: Settings) -> str:
    """Chain shown in Settings, e.g. `gemini-flash-latest → qwen3:4b (local)`."""
    parts = []
    for name in [p.strip().lower() for p in config.llm_providers.split(",") if p.strip()]:
        if name in PRESETS and config.provider_key(name):
            parts.append(config.provider_model(name))
        elif name == "local" and config.effective_llm_model:
            parts.append(f"{config.effective_llm_model} (local)")
    return " → ".join(parts) or "none (rule-based only)"
