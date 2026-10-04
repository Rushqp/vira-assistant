"""Ordered LLM providers with failover: free APIs first, the local model last.

`ProviderChain` exposes the same methods as `LLMClient` (`respond`, `stream_chat`, `chat`,
`complete_json`, `check`, `close`), so it can be used anywhere a single client was used.

- A model that fails (connection error, timeout, 429 / quota, invalid key, 5xx, empty answer) is
  paused with a growing cooldown and the next one answers. Models without tool support are
  skipped for agent turns.
- The user can prefer a model (🤖 AI model menu / `/model`): it is tried first, the configured
  order stays as backup.
- Every change of the answering model is recorded as a `Notice` (switched / restored / down);
  the bot shows them to the user after the turn (`drain_notices`). Health and notices live in
  `failover.py`, shared with the speech engines.
"""

import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from loguru import logger

from app.config import Profile, Settings
from app.llm.client import ChatMessage, LLMClient, LLMError, LLMResponse
from app.llm.failover import (  # noqa: F401  (re-exported for callers and tests)
    COOLDOWN_BASE,
    COOLDOWN_BROKEN,
    COOLDOWN_MAX,
    COOLDOWN_RATE_LIMIT,
    COOLDOWN_RATE_MAX,
    Failover,
    ModelStatus,
    Notice,
)
from app.llm.models import CATALOG, PROVIDER_NAMES

# Free OpenAI-compatible APIs. Models come from the catalog / .env.
PRESETS: dict[str, dict[str, Any]] = {
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/"},
    "groq": {"base_url": "https://api.groq.com/openai/v1"},
    "mistral": {"base_url": "https://api.mistral.ai/v1"},
    "github": {"base_url": "https://models.github.ai/inference"},
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "headers": {
            "HTTP-Referer": "https://github.com/Rushqp/vira-assistant",
            "X-Title": "Vira Assistant",
        },
    },
}
# Local model families without native tool calling (still fine for plain chat).
NO_TOOL_MODELS = ("gemma3", "gemma2", "gemma:", "phi3", "tinyllama")
# Local models offered in the menu (an OpenAI-compatible LLM_BASE_URL may list hundreds).
MAX_LOCAL_OPTIONS = 8


def local_supports_tools(model: str, setting: str) -> bool:
    if setting in ("on", "off"):
        return setting == "on"
    return not model.lower().startswith(NO_TOOL_MODELS)


def _suffix_for(model: str) -> str:
    return "/no_think" if "qwen3" in model.lower() else ""


def _reasoning_for(provider: str, model: str) -> str | None:
    """Keep reasoning short where the API allows it (faster, fewer tokens)."""
    if provider == "gemini" or "gpt-oss" in model:
        return "low"
    return None


def _order(config: Settings) -> list[str]:
    return [p.strip().lower() for p in config.llm_providers.split(",") if p.strip()]


def make_client(config: Settings, provider: str, model: str | None = None) -> LLMClient | None:
    """A client for `provider` (and `model`, default from .env / catalog), or None if unusable."""
    if provider in PRESETS:
        key = config.provider_key(provider)
        if not key:
            return None
        model = model or config.provider_model(provider)
        return LLMClient(
            PRESETS[provider]["base_url"],
            key,
            model,
            timeout=min(config.llm_timeout, 60),
            name=provider,
            reasoning_effort=_reasoning_for(provider, model),
            system_suffix=_suffix_for(model),
            default_headers=PRESETS[provider].get("headers"),
        )
    if provider == "local":
        model = model or config.effective_llm_model
        if not model:
            return None
        return LLMClient(
            config.llm_base_url,
            config.llm_api_key.get_secret_value(),
            model,
            timeout=config.llm_timeout,
            name="local",
            supports_tools=local_supports_tools(model, config.local_tools),
            stream_tools=config.profile != Profile.REMOTE,  # Ollama: show progress
            system_suffix=_suffix_for(model),
        )
    logger.warning("Unknown LLM provider {!r} in LLM_PROVIDERS (ignored)", provider)
    return None


def build_clients(config: Settings) -> list[LLMClient]:
    """Clients in the order of LLM_PROVIDERS; providers without a key / model are skipped."""
    clients = [make_client(config, provider) for provider in _order(config)]
    return [c for c in clients if c is not None]


def model_options(config: Settings, local_models: list[str] | None = None) -> list[tuple[str, str]]:
    """(provider, model) choices for the 🤖 AI model menu: catalog models of providers that have
    a key (plus the model set in .env), and the local models that are pulled."""
    options: list[tuple[str, str]] = []
    for provider in _order(config):
        if provider in PRESETS and config.provider_key(provider):
            models = [m for m, _ in CATALOG.get(provider, [])]
            configured = config.provider_model(provider)
            options += [(provider, m) for m in dict.fromkeys([configured, *models])]
        elif provider == "local" and config.effective_llm_model:
            pulled = [m for m in local_models or [] if "embed" not in m.lower()]
            local: dict[str, str] = {}  # "llama3.2" and "llama3.2:latest" are the same model
            for model in [config.effective_llm_model, *pulled]:
                local.setdefault(model.removesuffix(":latest"), model)
            options += [("local", m) for m in list(local.values())[:MAX_LOCAL_OPTIONS]]
    return list(dict.fromkeys(options))


def missing_providers(config: Settings) -> list[str]:
    """Providers in LLM_PROVIDERS that can't be used because their key is missing."""
    return [p for p in _order(config) if p in PRESETS and not config.provider_key(p)]


class ProviderChain:
    def __init__(
        self,
        clients: list[LLMClient],
        clock: Callable[[], float] = time.monotonic,
        factory: Callable[[str, str], LLMClient | None] | None = None,
    ) -> None:
        self.base = clients
        self.preferred: LLMClient | None = None
        self.factory = factory
        self.failover = Failover(clock)

    @classmethod
    def from_settings(cls, config: Settings) -> "ProviderChain":
        return cls(build_clients(config), factory=lambda p, m: make_client(config, p, m))

    @property
    def notices(self) -> list[Notice]:
        return self.failover.notices

    @notices.setter
    def notices(self, value: list[Notice]) -> None:
        self.failover.notices = value

    # --- Order and preference ---

    @property
    def clients(self) -> list[LLMClient]:
        if self.preferred is None:
            return self.base
        return [self.preferred, *(c for c in self.base if c.id != self.preferred.id)]

    @property
    def model(self) -> str:
        return " → ".join(c.label for c in self.clients) or "none"

    @property
    def preference(self) -> tuple[str, str] | None:
        return (self.preferred.name, self.preferred.model) if self.preferred else None

    def prefer(self, provider: str | None, model: str | None = None) -> LLMClient | None:
        """Use this model first (None = back to the configured order). Returns the client."""
        if not provider:
            self.preferred = None
        else:
            match = next((c for c in self.base if c.name == provider and c.model == model), None)
            if match is None and self.factory and model:
                match = self.factory(provider, model)
            self.preferred = match
        self.failover.reset()  # fresh start: no stale notices
        return self.preferred

    def answering(self, need_tools: bool = True) -> LLMClient | None:
        last = self.failover.last(_mode(need_tools))
        return next((c for c in self.clients if c.id == last), None)

    # --- Health ---

    def available(self, need_tools: bool = False) -> list[LLMClient]:
        ready = self.failover.ready(self.clients)
        return [c for c in ready if c.supports_tools] if need_tools else ready

    def has_tool_provider(self) -> bool:
        return any(c.supports_tools for c in self.clients)

    def status(self) -> list[ModelStatus]:
        answering = self.answering(True) or self.answering(False)
        return self.failover.status(self.clients, answering.id if answering else None)

    # --- Notices ---

    def _order_for(self, need_tools: bool) -> list[LLMClient]:
        return [c for c in self.clients if c.supports_tools] if need_tools else self.clients

    def _reports(self, need_tools: bool) -> bool:
        """Agent turns report model changes. Plain-chat calls only run during an outage the
        agent turn already reported, unless no model can use tools (a chat-only setup)."""
        return self.has_tool_provider() if need_tools else not self.has_tool_provider()

    def _failed(self, client: LLMClient, error: LLMError) -> None:
        self.failover.failed(client, error)

    def _answered(self, client: LLMClient, need_tools: bool) -> None:
        self.failover.answered(
            client, self._order_for(need_tools), _mode(need_tools), self._reports(need_tools)
        )

    def _nothing_answered(self, need_tools: bool) -> None:
        self.failover.nothing_answered(
            self._order_for(need_tools), _mode(need_tools), self._reports(need_tools)
        )

    def drain_notices(self) -> list[Notice]:
        """Notices since the last call, at most one per kind (the first)."""
        return self.failover.drain()

    def _candidates(self, need_tools: bool) -> list[LLMClient]:
        candidates = self.available(need_tools)
        if not candidates:
            self._nothing_answered(need_tools)
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
        need_tools = bool(tools)
        last: LLMError | None = None
        for client in self._candidates(need_tools):
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
            self._answered(client, need_tools)
            return response
        self._nothing_answered(need_tools)
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
            self._answered(client, need_tools=False)
            return
        self._nothing_answered(need_tools=False)
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
            self._answered(client, need_tools=False)
            return result
        self._nothing_answered(need_tools=False)
        raise last or LLMError("unreachable")

    async def check(self) -> bool:
        if not self.clients:
            logger.warning("No LLM provider configured: rule-based mode only")
            return False
        results = [await client.check() for client in self.clients]
        if not self.has_tool_provider():
            logger.warning("No tool-capable model configured: the agent runs in rule-based mode")
        return any(results)

    async def local_models(self) -> list[str]:
        """Models pulled in the local Ollama (for the menu); [] when there is no local provider."""
        local = next((c for c in self.base if c.name == "local"), None)
        return await local.list_models() if local else []

    async def close(self) -> None:
        clients = {c.id: c for c in [*self.base, *([self.preferred] if self.preferred else [])]}
        for client in clients.values():
            await client.close()


def _mode(need_tools: bool) -> str:
    return "tools" if need_tools else "chat"


def describe_providers(config: Settings) -> str:
    """Configured chain, e.g. `Gemini Flash · Gemini → qwen3:4b · Local`."""
    clients = build_clients(config)
    return " → ".join(c.label for c in clients) or "none (rule-based only)"


def provider_name(provider: str) -> str:
    return PROVIDER_NAMES.get(provider, provider)
