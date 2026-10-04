"""One OpenAI-compatible LLM endpoint (Ollama, Gemini, Groq, GitHub Models, OpenRouter, ...).

`ProviderChain` (providers.py) combines several of these with failover; both expose the same
methods, so callers don't care which one they get.
"""

import json
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import openai
from loguru import logger

from app.llm.models import model_label

# Plain dicts in OpenAI chat format: system / user / assistant (+ tool_calls) / tool.
ChatMessage = dict[str, Any]
ErrorKind = Literal["unreachable", "model_missing", "rate_limited", "auth", "failed"]


class LLMError(Exception):
    """The model could not produce an answer. `kind` tells the UI which message to show."""

    def __init__(self, kind: ErrorKind, detail: str = "", retry_after: float | None = None):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.retry_after = retry_after


class LanguageModel(Protocol):
    """What the app needs from a model: one `LLMClient` or a `ProviderChain`."""

    async def respond(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        on_text: Callable[[str], Any] | None = None,
        temperature: float = 0.3,
    ) -> "LLMResponse": ...

    def stream_chat(self, messages: list[ChatMessage]) -> AsyncIterator[str]: ...

    async def chat(self, messages: list[ChatMessage]) -> str: ...

    async def complete_json(
        self, messages: list[ChatMessage], schema: dict, name: str = "result"
    ) -> dict: ...


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text, validated by the tool registry


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    provider: str = ""


_THINK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


class ThinkFilter:
    """Drops a leading <think>…</think> block (Qwen3) from streamed text."""

    def __init__(self) -> None:
        self.buffer = ""
        self.passing = False

    def feed(self, piece: str) -> str:
        if self.passing:
            return piece
        self.buffer += piece
        stripped = self.buffer.lstrip()
        if not stripped:
            return ""
        if "<think>".startswith(stripped) or stripped.startswith("<think>"):
            if "</think>" not in stripped:
                return ""  # still inside (or maybe starting) a think block
            self.passing = True
            return _THINK.sub("", stripped, count=1).lstrip()
        self.passing = True
        return self.buffer


def strip_think(text: str) -> str:
    return _THINK.sub("", text).strip() if "<think>" in text else text


def _retry_after(exc: openai.APIStatusError) -> float | None:
    try:
        value = exc.response.headers.get("retry-after")
        return float(value) if value else None
    except (AttributeError, ValueError):
        return None


def translate_error(exc: Exception, model: str) -> LLMError:
    if isinstance(exc, openai.APIConnectionError):  # includes timeouts
        return LLMError("unreachable", str(exc))
    if isinstance(exc, openai.NotFoundError):
        return LLMError("model_missing", model)
    if isinstance(exc, openai.RateLimitError):
        return LLMError("rate_limited", str(exc), _retry_after(exc))
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return LLMError("auth", str(exc))
    if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
        return LLMError("unreachable", str(exc))
    return LLMError("failed", str(exc))


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 180,
        temperature: float = 0.6,
        *,
        name: str = "local",
        supports_tools: bool = True,
        stream_tools: bool = False,
        reasoning_effort: str | None = None,
        system_suffix: str = "",
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.temperature = temperature
        self.supports_tools = supports_tools
        self.stream_tools = stream_tools  # stream answers even when tools are offered
        self.reasoning_effort = reasoning_effort
        self.system_suffix = system_suffix  # e.g. "/no_think" for Qwen3
        self._client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=0,
            default_headers=default_headers,
        )

    @property
    def id(self) -> str:
        """Unique per provider + model (health and preference are tracked per id)."""
        return f"{self.name}:{self.model}"

    @property
    def label(self) -> str:
        return model_label(self.name, self.model)

    def _prepare(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        if not self.system_suffix or not messages or messages[0].get("role") != "system":
            return messages
        first = {**messages[0], "content": f"{messages[0]['content']}\n{self.system_suffix}"}
        return [first, *messages[1:]]

    def _extra(self) -> dict[str, Any]:
        return {"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}

    # --- Agent turn: text and/or tool calls ---

    async def respond(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        on_text: Callable[[str], Any] | None = None,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """One model call. `on_text` receives the answer while it streams (streaming calls only)."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._prepare(messages),
            "temperature": temperature,
            **self._extra(),
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        try:
            if self.stream_tools or not tools:
                response = await self._respond_streaming(kwargs, on_text)
            else:
                response = await self._respond_once(kwargs, on_text)
        except LLMError:
            raise
        except openai.OpenAIError as exc:
            raise translate_error(exc, self.model) from exc
        if not response.content.strip() and not response.tool_calls:
            raise LLMError("failed", "empty response")
        response.provider = self.name
        return response

    async def _respond_once(self, kwargs: dict, on_text=None) -> LLMResponse:
        completion = await self._client.chat.completions.create(**kwargs)
        if not completion.choices:
            raise LLMError("failed", "no choices")
        message = completion.choices[0].message
        calls = [
            ToolCall(id=c.id or f"call_{i}", name=c.function.name, arguments=c.function.arguments)
            for i, c in enumerate(message.tool_calls or [])
            if getattr(c, "function", None)
        ]
        # Not passed to `on_text`: the caller shows it after checking it (claims, tools).
        return LLMResponse(content=strip_think(message.content or ""), tool_calls=calls)

    async def _respond_streaming(self, kwargs: dict, on_text) -> LLMResponse:
        stream = await self._client.chat.completions.create(**kwargs, stream=True)
        content: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        thinking = ThinkFilter()
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content and (visible := thinking.feed(delta.content)):
                content.append(visible)
                if on_text:
                    await _maybe_await(on_text(visible))
            for part in delta.tool_calls or []:
                index = part.index if part.index is not None else len(calls) - (0 if part.id else 1)
                existing = calls.get(index)
                if part.id and existing and existing["id"] and existing["id"] != part.id:
                    index = max(calls) + 1  # a new call reusing the index (no index sent)
                slot = calls.setdefault(max(index, 0), {"id": "", "name": "", "arguments": ""})
                if part.id:
                    slot["id"] = part.id
                if part.function and part.function.name:
                    slot["name"] += part.function.name
                if part.function and part.function.arguments:
                    slot["arguments"] += part.function.arguments
        tool_calls = [
            ToolCall(id=slot["id"] or f"call_{i}", name=slot["name"], arguments=slot["arguments"])
            for i, slot in sorted(calls.items())
            if slot["name"]
        ]
        return LLMResponse(content="".join(content), tool_calls=tool_calls)

    # --- Plain chat / structured output (used by fallbacks and helpers) ---

    async def stream_chat(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """Yield the answer piece by piece as the model generates it."""
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=self._prepare(messages),  # type: ignore[arg-type]
                temperature=self.temperature,
                stream=True,
                **self._extra(),
            )
            thinking = ThinkFilter()
            async for chunk in stream:
                piece = chunk.choices[0].delta.content if chunk.choices else None
                if piece and (visible := thinking.feed(piece)):
                    yield visible
        except openai.OpenAIError as exc:
            raise translate_error(exc, self.model) from exc

    async def chat(self, messages: list[ChatMessage]) -> str:
        return "".join([piece async for piece in self.stream_chat(messages)])

    async def complete_json(
        self, messages: list[ChatMessage], schema: dict, name: str = "result"
    ) -> dict:
        """Ask for output matching a JSON schema (Ollama structured outputs / OpenAI json_schema).

        Falls back to extracting the first {...} block if the provider ignores the format.
        """
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=self._prepare(messages),  # type: ignore[arg-type]
                temperature=0,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": name, "schema": schema},
                },  # type: ignore[arg-type]
                **self._extra(),
            )
        except openai.OpenAIError as exc:
            raise translate_error(exc, self.model) from exc
        content = (response.choices[0].message.content or "") if response.choices else ""
        match = re.search(r"\{.*\}", content, re.DOTALL)
        try:
            data = json.loads(match.group() if match else content)
        except json.JSONDecodeError as exc:
            raise LLMError("failed", f"invalid JSON: {content[:200]}") from exc
        if not isinstance(data, dict):
            raise LLMError("failed", "JSON is not an object")
        return data

    async def list_models(self) -> list[str]:
        """Model ids the endpoint offers ([] if it can't be listed)."""
        try:
            return sorted(m.id.removeprefix("models/") async for m in self._client.models.list())
        except openai.OpenAIError as exc:
            logger.info("Could not list models of {}: {}", self.name, exc)
            return []

    async def check(self) -> bool:
        """Log whether the endpoint is reachable and the model is available. Never raises."""
        try:
            models = [m.id async for m in self._client.models.list()]
        except openai.OpenAIError as exc:
            logger.warning("LLM {} not reachable yet: {}", self.name, exc)
            return False
        known = {m.removeprefix("models/") for m in models}
        if models and self.model not in known and f"{self.model}:latest" not in known:
            if self.name == "local":
                logger.warning("LLM local: model {!r} not pulled yet", self.model)
                return False
            logger.info("LLM {}: {!r} not listed (aliases are fine)", self.name, self.model)
        logger.info("LLM {} ready: {}", self.name, self.model)
        return True

    async def close(self) -> None:
        await self._client.close()


async def _maybe_await(value: Any) -> None:
    if hasattr(value, "__await__"):
        await value
