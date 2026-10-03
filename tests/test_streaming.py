"""MessageStreamer with fake Telegram messages (no network)."""

import pytest

from app.bot import streaming
from app.bot.streaming import MessageStreamer


class FakeSent:
    def __init__(self, log: list, text: str) -> None:
        self.log = log
        self.text = text

    async def edit_text(self, text: str) -> None:
        self.text = text
        self.log.append(("edit", text))


class FakeIncoming:
    def __init__(self) -> None:
        self.log: list = []
        self.sent: list[FakeSent] = []

    async def answer(self, text: str) -> FakeSent:
        self.log.append(("send", text))
        message = FakeSent(self.log, text)
        self.sent.append(message)
        return message


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(streaming.time, "monotonic", lambda: now[0])
    return now


async def test_edits_are_throttled(clock):
    incoming = FakeIncoming()
    streamer = MessageStreamer(incoming, interval=1.0)  # type: ignore[arg-type]
    await streamer.push("Hello")  # first push renders immediately
    clock[0] += 0.3
    await streamer.push(" wor")  # too soon: no edit
    clock[0] += 0.3
    await streamer.push("ld")  # still too soon
    assert incoming.log == [("send", "Hello")]

    clock[0] += 1.0
    await streamer.push("!")
    await streamer.finish()
    assert incoming.log == [("send", "Hello"), ("edit", "Hello world!")]
    assert len(incoming.sent) == 1


async def test_finish_renders_markdown_and_suffix(clock):
    incoming = FakeIncoming()
    streamer = MessageStreamer(incoming)  # type: ignore[arg-type]
    await streamer.push("**Done**")
    await streamer.finish("\n\n⚠️ <oops>")
    assert incoming.sent[0].text == "<b>Done</b>\n\n⚠️ &lt;oops&gt;"


async def test_long_answer_continues_in_new_message(clock, monkeypatch):
    monkeypatch.setattr(streaming, "split_point", lambda text: min(len(text), 50))
    incoming = FakeIncoming()
    streamer = MessageStreamer(incoming)  # type: ignore[arg-type]
    for _ in range(12):
        clock[0] += 2
        await streamer.push("x" * 10)
    await streamer.finish()
    texts = [m.text for m in incoming.sent]
    assert len(texts) == 3
    assert all(len(t) <= 50 for t in texts)
    assert "".join(texts) == "x" * 120


async def test_nothing_sent_for_empty_answer(clock):
    incoming = FakeIncoming()
    streamer = MessageStreamer(incoming)  # type: ignore[arg-type]
    await streamer.push("   ")
    await streamer.finish()
    assert incoming.log == []
    assert not streamer.started
