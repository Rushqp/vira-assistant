"""Test doubles shared across test modules."""

from collections.abc import AsyncIterator

from app.llm.client import ChatMessage, LLMError


class FakeLLM:
    """Streams a canned answer and records the messages it was called with."""

    def __init__(self, answer: str = "Hello there!", error: LLMError | None = None) -> None:
        self.answer = answer
        self.error = error
        self.calls: list[list[ChatMessage]] = []

    async def stream_chat(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        self.calls.append(messages)
        for word in self.answer.split(" "):
            yield word + " "
        if self.error:
            raise self.error
