"""OpenAI-compatible LLM client (works with Ollama, OpenRouter, Gemini, ...)."""

from collections.abc import AsyncIterator
from typing import Literal, TypedDict

import openai
from loguru import logger

from app.config import Settings


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMError(Exception):
    """The model could not produce an answer. `kind` tells the UI which message to show."""

    def __init__(self, kind: Literal["unreachable", "model_missing", "failed"], detail: str = ""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 180,
        temperature: float = 0.6,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self._client = openai.AsyncOpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout, max_retries=1
        )

    @classmethod
    def from_settings(cls, config: Settings) -> "LLMClient":
        return cls(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key.get_secret_value(),
            model=config.effective_llm_model,
            timeout=config.llm_timeout,
        )

    async def stream_chat(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """Yield the answer piece by piece as the model generates it."""
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=self.temperature,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and (piece := chunk.choices[0].delta.content):
                    yield piece
        except openai.APIConnectionError as exc:  # includes timeouts
            raise LLMError("unreachable", str(exc)) from exc
        except openai.NotFoundError as exc:
            raise LLMError("model_missing", self.model) from exc
        except openai.APIError as exc:
            raise LLMError("failed", str(exc)) from exc

    async def chat(self, messages: list[ChatMessage]) -> str:
        return "".join([piece async for piece in self.stream_chat(messages)])

    async def check(self) -> bool:
        """Log whether the endpoint is reachable and the model is available. Never raises."""
        try:
            models = [m.id async for m in self._client.models.list()]
        except openai.APIError as exc:
            logger.warning("LLM endpoint not reachable yet: {}", exc)
            return False
        if self.model not in models and f"{self.model}:latest" not in models:
            logger.warning("LLM model {!r} not found. Available: {}", self.model, models)
            return False
        logger.info("LLM ready: {}", self.model)
        return True

    async def close(self) -> None:
        await self._client.close()
