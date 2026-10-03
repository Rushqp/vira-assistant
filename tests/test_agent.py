"""The agent loop with a scripted model: tool rounds, corrections, failures, context."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.agent.actions import ActionLog
from app.agent.context import build_context, date_line
from app.agent.core import CORRECTION, Agent, AgentUnavailable
from app.agent.tools import ToolContext, build_registry
from app.config import Calendar
from app.llm.client import LLMError
from app.services.expenses import ExpenseService
from app.services.reminders import ReminderService
from app.services.settings import SettingsService
from tests.fakes import FakeLLM, calls, reply, tool

TZ = ZoneInfo("Asia/Tehran")
NOW = datetime(2026, 10, 4, 10, 0, tzinfo=TZ)


@pytest.fixture
async def ctx(config, sessionmaker):
    async with sessionmaker() as session:
        settings = SettingsService(session, Calendar.JALALI)
        expenses = ExpenseService(session, TZ, "toman")
        reminders = ReminderService(session, TZ, config.day_times)
        yield ToolContext(
            config=config,
            calendar=Calendar.JALALI,
            now=NOW,
            user_text="msg",
            expenses=expenses,
            reminders=reminders,
            settings=settings,
            actions=ActionLog(session, expenses, reminders, settings),
        )


def agent(llm: FakeLLM) -> Agent:
    return Agent(llm, build_registry())


async def test_plain_answer(ctx):
    llm = FakeLLM()
    llm.script = [reply("سلام! چطور کمکت کنم؟")]
    result = await agent(llm).run(ctx, [], "سلام")
    assert result.text == "سلام! چطور کمکت کنم؟" and result.cards == []


async def test_tool_round_trip(ctx):
    llm = FakeLLM()
    llm.script = [
        calls(tool("add_expenses", items=[{"description": "نون", "amount_text": "۵۰ هزار"}])),
        reply("ثبت شد 👍"),
    ]
    result = await agent(llm).run(ctx, [], "نون ۵۰ تومن هزار")
    assert [c.kind for c in result.cards] == ["expenses_saved"]
    assert result.text == "ثبت شد 👍"
    assert result.notes and result.notes[0].startswith("[done: expenses added")
    # The second call saw the tool result.
    tool_message = llm.respond_calls[1][-1]
    assert tool_message["role"] == "tool"
    assert json.loads(tool_message["content"])["saved"][0]["amount"] == 50_000


async def test_tool_errors_go_back_to_the_model(ctx):
    llm = FakeLLM()
    llm.script = [
        calls(tool("add_expenses", items=[{"description": "نون", "amount_text": "یه کم"}])),
        calls(tool("add_expenses", items=[{"description": "نون", "amount_text": "۵۰ هزار"}])),
        reply(""),
    ]
    result = await agent(llm).run(ctx, [], "نون ۵۰ هزار")
    assert "error" in json.loads(llm.respond_calls[1][-1]["content"])
    assert [c.kind for c in result.cards] == ["expenses_saved"]


async def test_claim_without_tool_is_corrected(ctx):
    llm = FakeLLM()
    llm.script = [
        reply("یادآوری ثبت شد ✅"),  # claims success without calling a tool
        calls(tool("create_reminder", subject="دکتر", start="2026-10-05T14:00")),
        reply(""),
    ]
    result = await agent(llm).run(ctx, [], "فردا ساعت ۲ دکتر دارم")
    assert llm.respond_calls[1][-1] == {"role": "user", "content": CORRECTION}
    assert [c.kind for c in result.cards] == ["reminder_saved"]


async def test_unavailable_before_any_tool(ctx):
    llm = FakeLLM()  # empty script → LLMError
    with pytest.raises(AgentUnavailable):
        await agent(llm).run(ctx, [], "hi")


async def test_failure_after_tools_keeps_the_results(ctx):
    llm = FakeLLM()

    def boom(messages):
        raise LLMError("unreachable")

    llm.script = [
        calls(tool("add_expenses", items=[{"description": "نون", "amount_text": "۵۰ هزار"}])),
        boom,
    ]
    result = await agent(llm).run(ctx, [], "نون ۵۰ هزار")
    assert [c.kind for c in result.cards] == ["expenses_saved"] and result.text == ""


async def test_clarification_stops_the_turn(ctx):
    llm = FakeLLM()
    llm.script = [
        calls(tool("add_expenses", items=[{"description": "بنزین", "amount_text": "۱۰۰ تومن"}])),
        reply("should not be asked for"),
    ]
    result = await agent(llm).run(ctx, [], "بنزین ۱۰۰ تومن")
    assert result.clarification is not None and len(llm.respond_calls) == 1


async def test_several_tools_in_one_turn(ctx):
    llm = FakeLLM()
    llm.script = [
        calls(
            tool("add_expenses", items=[{"description": "قبض برق", "amount_text": "۴۵۰ هزار"}]),
            tool(
                "create_reminder",
                subject="پرداخت اجاره",
                start="2026-10-06",
                alerts=["2026-10-06T09:00"],
            ),
        ),
        reply(""),
    ]
    result = await agent(llm).run(ctx, [], "قبض برق ۴۵۰ هزار دادم و یادم بنداز سه‌شنبه اجاره بدم")
    assert [c.kind for c in result.cards] == ["expenses_saved", "reminder_saved"]


async def test_prompt_and_context(ctx):
    llm = FakeLLM()
    llm.script = [reply("ok")]
    history = [{"role": "user", "content": "قبلی"}, {"role": "assistant", "content": "[done: x]"}]
    await agent(llm).run(ctx, history, "سلام", hint="[hint]")
    messages = llm.respond_calls[0]
    assert messages[0]["role"] == "system" and "Groceries" in messages[0]["content"]
    assert messages[1:3] == history
    user = messages[-1]["content"]
    assert user.startswith("[context]") and "[hint]" in user and user.endswith("سلام")
    assert "2026-10-05 Monday = 1405-07-13" in user and "tomorrow" in user


def test_date_line_and_context():
    assert (
        date_line(datetime(2026, 10, 3).date())
        == "2026-10-03 Saturday = 1405-07-11 (11 مهر 1405) شنبه"
    )
    context = build_context(NOW, Calendar.JALALI, "toman")
    assert "user's calendar: jalali · currency: toman" in context
    assert context.count("\n  ") == 11  # yesterday-1 … +8


async def test_streamed_claim_is_not_retried(ctx):
    """Text already on screen can't be taken back, so no corrective retry then."""
    llm = FakeLLM()
    llm.streams = True
    llm.script = [reply("یادآوری ثبت شد ✅")]
    shown = []

    async def on_text(piece):
        shown.append(piece)

    result = await agent(llm).run(ctx, [], "یادم بنداز", on_text=on_text)
    assert shown == ["یادآوری ثبت شد ✅"] and len(llm.respond_calls) == 1
    assert result.text == "یادآوری ثبت شد ✅"


async def test_failure_after_streamed_text_is_reported(ctx):
    """Not AgentUnavailable: the rule-based fallback must not answer over half an answer."""

    class Breaks:
        async def respond(self, messages, tools=None, on_text=None, temperature=0.3):
            await on_text("half an answer")
            raise LLMError("unreachable")

    with pytest.raises(LLMError):
        await Agent(Breaks(), build_registry()).run(ctx, [], "x", on_text=lambda p: None)
