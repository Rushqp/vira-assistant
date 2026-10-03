"""End-to-end agent conversations through the real dispatcher (fake Telegram, scripted model).

These check the plumbing around the model: tool execution, cards, undo / edit, follow-ups,
clarifications and the fallback. How well a real model understands Persian is measured with
`scripts/eval_agent.py` instead.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app import texts
from app.db.models import Expense, Reminder
from tests.fakes import calls, reply, tool

TZ = ZoneInfo("Asia/Tehran")


def tomorrow() -> str:
    return (datetime.now(TZ) + timedelta(days=1)).date().isoformat()


async def expenses(env) -> list[tuple[str, int, str]]:
    async with env.db() as session:
        rows = (await session.scalars(select(Expense).order_by(Expense.id))).unique().all()
        return [(e.description, e.amount, e.category.name) for e in rows]


async def reminders(env) -> list[tuple[str, str]]:
    async with env.db() as session:
        rows = (await session.scalars(select(Reminder).order_by(Reminder.id))).all()
        return [(r.text, r.status) for r in rows]


async def test_screenshot_three_purchases(env):
    """Reported: «۳ خرید کردم» was taken as "3 toman"; the agent understands it's a count."""
    env.llm.script = [
        calls(
            tool(
                "add_expenses",
                items=[
                    {"description": "سیگار", "amount_text": "۱۵۰ هزار تومن"},
                    {"description": "ماست", "amount_text": "۲۰۰ هزار تومن"},
                    {"description": "آب", "amount_text": "۵۰ هزار تومن"},
                ],
            )
        ),
        reply(""),
    ]
    await env.send(
        "امروز من ۳ خرید کرد کردم\nسیگار ۱۵۰ هزار تومن\nماست ۲۰۰ هزار تومن\nو اب ۵۰ هزار تومن"
    )
    card = env.session.sent[-1]
    assert card.startswith(texts.AGENT_EXPENSES_SAVED)
    assert "thousand or" not in "".join(env.session.sent)
    assert "Total: <b>400,000 toman</b>" in card
    assert [(d, a) for d, a, _ in await expenses(env)] == [
        ("سیگار", 150_000),
        ("ماست", 200_000),
        ("آب", 50_000),
    ]


async def test_screenshot_reminder_in_five_minutes(env):
    """Reported: «یک یاد اوری تنظیم کن برای ۵ دقیقه دیگه …» went to the chat."""
    env.llm.script = [
        calls(tool("create_reminder", subject="کتاب بخونم", when_text="۵ دقیقه دیگه")),
        reply(""),
    ]
    await env.send("یک یاد اوری تنظیم کن برای ۵ دقیقه دیگه میخوام کتاب بخونم")
    assert env.session.sent[-1].startswith("⏰ <b>Reminder saved</b>")
    assert await reminders(env) == [("کتاب بخونم", "active")]


async def test_cancel_follow_up_and_undo(env):
    """«برای فردا تایم دکتر دارم» → «تایم دکتر رو کنسل کن» → cancelled, using the transcript."""
    env.llm.script = [
        calls(tool("create_reminder", subject="دکتر", start=tomorrow(), important=True)),
        reply("ثبت شد"),
    ]
    await env.send("برای فردا تایم دکتر دارم")
    assert env.session.sent[-2] == "ثبت شد"

    def cancel_using_history(messages):
        notes = [m["content"] for m in messages if m["role"] == "assistant"]
        assert any("[done: reminder created" in n and "دکتر" in n for n in notes)
        return calls(tool("cancel_reminders", query="دکتر"))

    env.llm.script = [cancel_using_history, reply("کنسل شد")]
    await env.send("تایم دکتر رو کنسل کن")
    assert env.session.sent[-2] == "کنسل شد"
    assert env.session.sent[-1].startswith(texts.AGENT_REMINDERS_CANCELLED)
    assert await reminders(env) == [("دکتر", "cancelled")]

    await env.press(env.button(texts.BTN_UNDO))
    assert env.session.edits[-1].endswith("<i>Undone</i>")
    assert await reminders(env) == [("دکتر", "active")]


async def test_amount_question_with_buttons(env):
    env.llm.script = [
        calls(tool("add_expenses", items=[{"description": "بنزین", "amount_text": "۳ تومن"}])),
    ]
    await env.send("۳ تومن بنزین زدم")
    assert "<b>بنزین</b>: 3 thousand or 3 million?" in env.session.sent[-1]
    await env.press(env.button("3,000,000 toman"))
    assert env.session.edits[-1].startswith(texts.AGENT_EXPENSES_SAVED)
    assert await expenses(env) == [("بنزین", 3_000_000, "Fuel")]


async def test_amount_question_answered_by_typing(env):
    env.llm.script = [
        calls(tool("add_expenses", items=[{"description": "نون", "amount_text": "۵۰"}])),
    ]
    await env.send("نون ۵۰")
    await env.send("هزار")
    assert env.session.sent[-1].startswith(texts.AGENT_EXPENSES_SAVED)
    assert await expenses(env) == [("نون", 50_000, "Food")]


async def test_edit_button_sends_a_correction(env):
    env.llm.script = [
        calls(tool("add_expenses", items=[{"description": "ماست", "amount_text": "۲۰۰ هزار"}])),
        reply(""),
    ]
    await env.send("ماست ۲۰۰ هزار")
    await env.press(env.button(texts.BTN_EDIT))
    assert env.session.sent[-1] == texts.AGENT_EDIT_PROMPT

    expense_id = 1

    def correct(messages):
        assert (
            "[The user is correcting this earlier action: added expenses" in messages[-1]["content"]
        )
        return calls(tool("update_expense", id=expense_id, amount_text="۲۵۰ هزار"))

    env.llm.script = [correct, reply("")]
    await env.send("۲۵۰ هزار بود")
    assert env.session.sent[-1].startswith(texts.AGENT_EXPENSE_UPDATED)
    assert await expenses(env) == [("ماست", 250_000, "Food")]


async def test_undo_saved_expenses(env):
    env.llm.script = [
        calls(tool("add_expenses", items=[{"description": "نون", "amount_text": "۵۰ هزار"}])),
        reply(""),
    ]
    await env.send("نون ۵۰ هزار")
    await env.press(env.button(texts.BTN_UNDO))
    assert await expenses(env) == []
    await env.press(f"act:undo:{1}:")  # second press on the same action
    assert env.session.alerts[-1] == texts.AGENT_ALREADY_UNDONE


async def test_alert_buttons_on_a_reminder_without_alerts(env):
    env.llm.script = [
        calls(tool("create_reminder", subject="جلسه", start=f"{tomorrow()}T16:00")),
        reply(""),
    ]
    await env.send("فردا ساعت ۴ عصر جلسه دارم")
    assert texts.AGENT_ASK_ALERTS.strip() in env.session.sent[-1]
    await env.press(env.button("1 hour before"))
    async with env.db() as session:
        reminder = await session.scalar(select(Reminder))
        assert reminder is not None and reminder.alert_specs == "at,before:60"
    assert env.button(texts.BTN_SELECTED + "1 hour before")


async def test_change_category_of_a_saved_expense(env):
    env.llm.script = [
        calls(tool("add_expenses", items=[{"description": "عروسک", "amount_text": "۲۰۰ هزار"}])),
        reply(""),
    ]
    await env.send("عروسک ۲۰۰ هزار خریدم")
    await env.press(env.button(texts.BTN_CATEGORY))
    await env.press(env.button("🎁 Gifts"))
    assert "🎁 عروسک" in env.session.edits[-1]
    assert await expenses(env) == [("عروسک", 200_000, "Gifts")]


async def test_report_through_the_agent(env):
    env.llm.script = [calls(tool("get_report", period="this_month")), reply("")]
    await env.send("این ماه چقدر خرج کردم؟")
    assert env.session.sent[-1].startswith("📅 <b>")


async def test_menu_button_gives_the_agent_a_hint(env):
    await env.send(texts.BTN_NEW_REMINDER)

    def check_hint(messages):
        assert texts.AGENT_HINT_REMINDER in messages[-1]["content"]
        return calls(tool("create_reminder", subject="جلسه", start=f"{tomorrow()}T10:00"))

    env.llm.script = [check_hint, reply("")]
    await env.send("فردا ساعت ۱۰ صبح جلسه")
    assert await reminders(env) == [("جلسه", "active")]


async def test_plain_chat_through_the_agent(env):
    env.llm.script = [reply("پایتخت فرانسه پاریس است.")]
    await env.send("پایتخت فرانسه کجاست؟")
    assert env.session.sent[-1] == "پایتخت فرانسه پاریس است."
    assert env.llm.calls == []  # no separate chat call


async def test_calculator_needs_no_model(env):
    await env.send("12*350000")
    assert "4,200,000" in env.session.sent[-1]
    assert env.llm.respond_calls == []


async def test_transcript_notes_hidden_in_chat_recap(env):
    env.llm.script = [
        calls(tool("add_expenses", items=[{"description": "نون", "amount_text": "۵۰ هزار"}])),
        reply("ثبت شد"),
    ]
    await env.send("نون ۵۰ هزار")
    await env.send(texts.BTN_CHATS)
    await env.press(env.button("نون ۵۰ هزار"))
    recap = env.session.edits[-1]
    assert "🤖 ثبت شد" in recap and "[done:" not in recap


async def test_fallback_without_a_model_uses_the_rules(env):
    await env.send(texts.BTN_ADD_EXPENSE)
    await env.send("بنزین ۱۰۰ هزار تومن")  # no script: the agent is unavailable
    assert "<b>New expense</b>" in env.session.sent[-1]
