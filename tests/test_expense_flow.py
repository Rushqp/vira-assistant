"""End-to-end expense and report conversations (fake Telegram, fake LLM)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app import texts
from app.config import Calendar
from app.db.models import Category, Expense
from app.utils.calendar import format_date

TZ = ZoneInfo("Asia/Tehran")


async def _expenses(env) -> list[tuple[str, int, str]]:
    async with env.db() as session:
        rows = (await session.scalars(select(Expense).order_by(Expense.id))).unique().all()
        return [(e.description, e.amount, e.category.name) for e in rows]


async def test_roadmap_acceptance_two_records(env):
    """«۳ میلیون خرید خونه دادم، ۱۰ لیتر بنزین هم ۱۰۰ تومن» → two correct records."""
    await env.send("۳ میلیون خرید خونه دادم، ۱۰ لیتر بنزین هم ۱۰۰ تومن")
    assert "<b>بنزین</b>: 100 thousand or 100 million?" in env.session.sent[-1]

    await env.press(env.button("100,000 toman"))
    card = env.session.edits[-1]
    assert "<b>New expenses</b> (2)" in card
    assert "🛒 خرید خونه — <b>3,000,000 toman</b>" in card
    assert "⛽ بنزین (10 L) — <b>100,000 toman</b>" in card
    assert "Total: <b>3,100,000 toman</b>" in card

    await env.press(env.button(texts.BTN_SAVE))
    assert "<b>Saved</b>" in env.session.edits[-1]
    assert await _expenses(env) == [
        ("خرید خونه", 3_000_000, "Groceries"),
        ("بنزین", 100_000, "Fuel"),
    ]


async def test_english_example(env):
    await env.send("Paid 3 million toman for groceries, and 10 liters of fuel cost 100 thousand")
    await env.press(env.button(texts.BTN_SAVE))
    assert await _expenses(env) == [
        ("groceries", 3_000_000, "Groceries"),
        ("fuel", 100_000, "Fuel"),
    ]


async def test_change_category_is_learned(env):
    await env.send("عروسک ۲۰۰ هزار خریدم")  # unknown word, LLM offline → Other
    assert "📦 عروسک" in env.session.sent[-1]

    await env.press(env.button(texts.BTN_CATEGORY))
    await env.press(env.button("🎁 Gifts"))
    assert "🎁 عروسک" in env.session.edits[-1]
    await env.press(env.button(texts.BTN_SAVE))

    await env.send("عروسک ۳۰۰ هزار")  # remembered
    assert "🎁 عروسک" in env.session.sent[-1]


async def test_llm_picks_the_category(env):
    env.llm.json_reply = {"categories": ["Gifts"]}
    await env.send("عروسک ۲۰۰ هزار خریدم")
    assert "🎁 عروسک" in env.session.sent[-1]


async def test_pick_item_then_category_with_several_items(env):
    await env.send("نون ۵۰ هزار و شیر ۳۰ هزار")
    await env.press(env.button(texts.BTN_CATEGORY))
    assert env.session.edits[-1] == texts.EXPENSE_PICK_ITEM
    await env.press(env.button("2. شیر"))
    await env.press(env.button("🛒 Groceries"))
    await env.press(env.button(texts.BTN_SAVE))
    assert await _expenses(env) == [("نون", 50_000, "Food"), ("شیر", 30_000, "Groceries")]


async def test_form_and_missing_amount(env):
    await env.send(texts.BTN_ADD_EXPENSE)
    assert env.session.sent[-1] == texts.EXPENSE_ASK_DESCRIBE
    await env.send("یه کتاب خریدم ولی یادم نیست چقدر")
    assert env.session.sent[-1] == texts.EXPENSE_RETRY  # LLM offline, no amount
    await env.send("کتاب ۱۲۰ هزار")
    assert "📚 کتاب" in env.session.sent[-1]


async def test_undo(env):
    await env.send("بنزین ۱۰۰ هزار تومن")
    await env.press(env.button(texts.BTN_SAVE))
    await env.press(env.button(texts.BTN_UNDO))
    assert env.session.edits[-1] == texts.EXPENSE_UNDONE
    assert await _expenses(env) == []


async def test_cancel(env):
    await env.send("بنزین ۱۰۰ هزار تومن")
    await env.press(env.button(texts.BTN_CANCEL))
    assert env.session.edits[-1] == texts.EXPENSE_CANCELLED
    assert await _expenses(env) == []


async def test_questions_go_to_chat(env):
    await env.send("۳ میلیون تومن چند دلاره؟")
    assert env.llm.calls  # answered by the chat model


async def _save(env, text: str) -> None:
    """Record expenses whose amounts are unambiguous (straight to the confirmation card)."""
    await env.send(text)
    await env.press(env.button(texts.BTN_SAVE))


async def test_today_report_and_delete(env):
    await _save(env, "خرید خونه ۳ میلیون، بنزین ۱۰۰ هزار تومن")
    await env.send(texts.BTN_TODAY_REPORT)
    report = env.session.sent[-1]
    assert "Total: <b>3,100,000 toman</b>" in report
    assert "🛒 Groceries ██████████ 97% · 3,000,000 toman" in report
    assert "⛽ Fuel ░░░░░░░░░░ 3% · 100,000 toman" in report
    assert "⛽ بنزین — 100,000 toman" in report

    await env.press(env.button("🗑 1"))
    assert "Delete" in env.session.edits[-1]
    await env.press(env.button(texts.BTN_YES_DELETE))
    assert env.session.alerts[-1] == texts.REPORT_DELETED
    assert len(await _expenses(env)) == 1


async def test_month_report_and_navigation(env):
    await _save(env, "بنزین ۱۰۰ هزار تومن")
    await env.send(texts.BTN_MONTH_REPORT)
    assert "Daily average" in env.session.sent[-1]
    await env.press(env.button(texts.BTN_PREV))  # previous month
    assert texts.REPORT_EMPTY in env.session.edits[-1]
    await env.press(env.button(texts.BTN_REPORT_WEEK))
    assert "<b>Week</b>" in env.session.edits[-1]


async def test_report_from_text(env):
    await env.send("گزارش این ماه")
    assert texts.REPORT_EMPTY in env.session.sent[-1]
    await env.send("how much did I spend yesterday")
    yesterday = datetime.now(TZ).date() - timedelta(days=1)
    assert env.session.sent[-1].startswith("📊 <b>")
    title = env.session.sent[-1].splitlines()[0]
    assert format_date(yesterday, Calendar.JALALI) in title


async def test_categories_in_settings(env):
    await env.send(texts.BTN_SETTINGS)
    await env.press(env.button(texts.BTN_CATEGORIES))
    assert texts.CATEGORIES_TITLE in env.session.sent[-1]

    await env.press(env.button(texts.BTN_ADD_CATEGORY))
    await env.send("🐶 Pets")
    assert env.session.sent[-2] == texts.CATEGORY_ADDED.format(emoji="🐶", name="Pets")

    await env.press(env.button("🐶 Pets"))
    await env.press(env.button(texts.BTN_YES_DELETE))
    assert env.session.alerts[-1] == texts.CATEGORY_DELETED
    async with env.db() as session:
        names = (await session.scalars(select(Category.name))).all()
    assert "Pets" not in names

    await env.press(env.button("📦 Other"))
    assert env.session.alerts[-1] == texts.CATEGORY_PROTECTED
