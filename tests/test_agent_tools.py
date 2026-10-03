"""Agent tools, called directly (no model): validation, deterministic checks, undo.

"Now" is fixed to Sunday 4 Oct 2026 10:00 Tehran (= 12 Mehr 1405).
"""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.agent.actions import ActionLog
from app.agent.tools import ToolContext, build_registry
from app.config import Calendar
from app.db.models import Expense, Reminder
from app.services.expenses import ExpenseService
from app.services.reminders import ReminderService, from_utc
from app.services.settings import SettingsService

TZ = ZoneInfo("Asia/Tehran")
NOW = datetime(2026, 10, 4, 10, 0, tzinfo=TZ)
REGISTRY = build_registry()


@pytest.fixture
async def ctx(config, sessionmaker):
    async with sessionmaker() as session:
        settings = SettingsService(session, Calendar.JALALI)
        expenses = ExpenseService(session, TZ, "toman")
        reminders = ReminderService(session, TZ, config.day_times)
        reminders.now = lambda: NOW  # type: ignore[method-assign]
        yield ToolContext(
            config=config,
            calendar=Calendar.JALALI,
            now=NOW,
            user_text="(test)",
            expenses=expenses,
            reminders=reminders,
            settings=settings,
            actions=ActionLog(session, expenses, reminders, settings),
        )


async def call(ctx, name: str, **args):
    return await REGISTRY.execute(name, json.dumps(args, ensure_ascii=False), ctx)


async def all_expenses(ctx) -> list[tuple[str, int, str]]:
    rows = (await ctx.expenses.session.scalars(select(Expense).order_by(Expense.id))).unique()
    return [(e.description, e.amount, e.category.name) for e in rows]


# --- Registry ---


def test_schemas_are_plain():
    text = json.dumps(REGISTRY.schemas())
    assert "$ref" not in text and "anyOf" not in text
    names = {s["function"]["name"] for s in REGISTRY.schemas()}
    assert {"add_expenses", "create_reminder", "cancel_reminders", "get_report"} <= names


async def test_unknown_tool_and_bad_arguments(ctx):
    assert "unknown tool" in (await REGISTRY.execute("fly", "{}", ctx)).result["error"]
    assert (
        "invalid arguments"
        in (await REGISTRY.execute("add_expenses", "{oops", ctx)).result["error"]
    )
    bad = await call(ctx, "add_expenses", items=[])
    assert "invalid arguments" in bad.result["error"]


# --- Expenses ---


async def test_screenshot_purchases(ctx):
    """«امروز ۳ خرید کردم: سیگار ۱۵۰ هزار تومن، ماست ۲۰۰ هزار، آب ۵۰ هزار»"""
    outcome = await call(
        ctx,
        "add_expenses",
        items=[
            {"description": "سیگار", "amount_text": "۱۵۰ هزار تومن", "category": "Leisure"},
            {"description": "ماست", "amount_text": "۲۰۰ هزار تومن"},
            {"description": "آب", "amount_text": "۵۰ هزار تومن", "category": "Groceries"},
        ],
    )
    assert outcome.clarification is None
    assert outcome.card and outcome.card.kind == "expenses_saved"
    assert outcome.result["total"] == 400_000
    assert await all_expenses(ctx) == [
        ("سیگار", 150_000, "Leisure"),  # the model's category
        ("ماست", 200_000, "Food"),  # built-in keyword
        ("آب", 50_000, "Groceries"),
    ]
    assert "[done: expenses added" in outcome.note


async def test_ambiguous_amount_asks(ctx):
    outcome = await call(
        ctx, "add_expenses", items=[{"description": "بنزین", "amount_text": "۱۰۰ تومن"}]
    )
    assert outcome.clarification is not None and outcome.result["status"] == "waiting_for_user"
    assert await all_expenses(ctx) == []


async def test_amount_must_be_copied(ctx):
    outcome = await call(
        ctx, "add_expenses", items=[{"description": "نون", "amount_text": "یه کم"}]
    )
    assert "no amount" in outcome.result["error"] and "hint" in outcome.result


async def test_learned_category_beats_the_model(ctx):
    gifts = await ctx.expenses.category_by_name("Gifts")
    await ctx.expenses.learn("عروسک", gifts.id)
    await call(
        ctx,
        "add_expenses",
        items=[{"description": "عروسک", "amount_text": "۲۰۰ هزار", "category": "Leisure"}],
    )
    assert (await all_expenses(ctx))[0][2] == "Gifts"


async def test_expense_dates(ctx):
    jalali = await call(
        ctx, "add_expenses", date="1405-07-11", items=[{"description": "نون", "amount_text": "50k"}]
    )
    assert jalali.result["saved"][0]["date"] == "2026-10-03"
    future = await call(
        ctx, "add_expenses", date="2026-12-01", items=[{"description": "x", "amount_text": "50k"}]
    )
    assert "future" in future.result["error"]


async def test_list_update_delete_expenses_and_undo(ctx):
    saved = await call(
        ctx,
        "add_expenses",
        items=[
            {"description": "ماست", "amount_text": "۲۰۰ هزار"},
            {"description": "نون", "amount_text": "۵۰ هزار"},
        ],
    )
    yogurt_id = saved.result["saved"][0]["id"]

    listed = await call(ctx, "list_expenses", period="today", query="ماست")
    assert [e["id"] for e in listed.result["expenses"]] == [yogurt_id]

    ambiguous = await call(ctx, "update_expense", id=yogurt_id, amount_text="۲۵۰")
    assert "ambiguous" in ambiguous.result["error"]
    updated = await call(
        ctx, "update_expense", id=yogurt_id, amount_text="۲۵۰ هزار", category="Groceries"
    )
    assert updated.result["updated"]["amount"] == 250_000
    assert (await ctx.expenses.learned_category("ماست")).name == "Groceries"  # learned

    await ctx.actions.undo(updated.card.action_id)
    assert (await ctx.expenses.get(yogurt_id)).amount == 200_000

    deleted = await call(ctx, "delete_expenses", query="نون")
    assert [i["description"] for i in deleted.result["deleted"]] == ["نون"]
    assert [d for d, *_ in await all_expenses(ctx)] == ["ماست"]
    await ctx.actions.undo(deleted.card.action_id)
    assert [d for d, *_ in await all_expenses(ctx)] == ["ماست", "نون"]

    assert await ctx.actions.undo(deleted.card.action_id) is None  # already undone
    await ctx.actions.undo(saved.card.action_id)
    assert await all_expenses(ctx) == []


# --- Reminders ---


async def created(ctx, **args) -> Reminder:
    outcome = await call(ctx, "create_reminder", **args)
    assert "error" not in outcome.result, outcome.result
    return await ctx.reminders.get(outcome.result["created"]["id"])


def local(reminder: Reminder) -> datetime:
    return from_utc(reminder.event_at, TZ).replace(tzinfo=None)


async def test_doctor_tomorrow_at_two_remind_in_the_morning(ctx):
    reminder = await created(
        ctx,
        subject="دکتر",
        when_text="فردا ساعت ۲",
        start="2026-10-05T14:00",
        alerts=["2026-10-05T09:00"],
        important=True,
    )
    assert local(reminder) == datetime(2026, 10, 5, 14, 0)
    assert reminder.alert_specs == "same_day:09:00" and reminder.important


async def test_parser_wins_for_jalali_dates(ctx):
    # The model got the Gregorian date of «۱۵ مهر» wrong; the deterministic parser fixes it.
    reminder = await created(ctx, subject="تولد", when_text="۱۵ مهر", start="2026-10-08")
    assert local(reminder).date().isoformat() == "2026-10-07"
    assert reminder.all_day


async def test_ambiguous_time_needs_the_model_or_the_user(ctx):
    outcome = await call(ctx, "create_reminder", subject="جلسه", when_text="فردا ساعت ۸")
    assert "AM or PM" in outcome.result["error"]
    ok = await created(ctx, subject="جلسه", when_text="فردا ساعت ۸", start="2026-10-05T20:00")
    assert local(ok).hour == 20


async def test_relative_time_and_default_alert(ctx):
    outcome = await call(
        ctx,
        "create_reminder",
        subject="کتاب بخونم",
        when_text="۵ دقیقه دیگه",
        start="2026-10-04T10:05",
    )
    reminder = await ctx.reminders.get(outcome.result["created"]["id"])
    assert local(reminder) == datetime(2026, 10, 4, 10, 5)
    assert outcome.card.data["ask_alerts"] is True and reminder.alert_specs == "at"


@pytest.mark.parametrize(
    ("alerts", "specs"),
    [
        (["-30m"], "before:30"),
        (["-1h", "at"], "before:60,at"),
        (["-1d"], "before:1440"),
        (["صبح"], "same_day:09:00"),
        (["شب قبلش"], "day_before:22:00"),
        (["2026-10-04T21:00"], "day_before:21:00"),
    ],
)
async def test_alert_mapping(ctx, alerts, specs):
    reminder = await created(ctx, subject="x", start="2026-10-05T14:00", alerts=alerts)
    assert reminder.alert_specs == specs


async def test_past_and_missing_times(ctx):
    past = await call(ctx, "create_reminder", subject="x", start="2026-10-04T08:00")
    assert "passed" in past.result["error"]
    missing = await call(ctx, "create_reminder", subject="x")
    assert "ask the user when" in missing.result["hint"]


async def test_weekly_repeat(ctx):
    reminder = await created(
        ctx, subject="باشگاه", when_text="هر شنبه ساعت ۸ صبح", start="2026-10-10T08:00"
    )
    assert reminder.repeat_rule == "weekly:5"
    assert local(reminder) == datetime(2026, 10, 10, 8, 0)


async def test_cancel_by_query_and_undo(ctx):
    """«برای فردا تایم دکتر دارم» … «تایم دکتر رو کنسل کن»"""
    doctor = await created(ctx, subject="دکتر", start="2026-10-05T14:00")
    await created(ctx, subject="جلسه با علی", start="2026-10-05T16:00")

    outcome = await call(ctx, "cancel_reminders", query="تایم دکتر")
    assert [i["subject"] for i in outcome.result["cancelled"]] == ["دکتر"]
    assert (await ctx.reminders.get(doctor.id)).status == "cancelled"
    assert [r.text for r in await ctx.reminders.upcoming()] == ["جلسه با علی"]

    await ctx.actions.undo(outcome.card.action_id)
    assert (await ctx.reminders.get(doctor.id)).status == "active"


async def test_ambiguous_reference_returns_candidates(ctx):
    await created(ctx, subject="دکتر دندون", start="2026-10-05T14:00")
    await created(ctx, subject="دکتر قلب", start="2026-10-06T10:00")
    outcome = await call(ctx, "cancel_reminders", query="دکتر")
    assert outcome.result["status"] == "several_match"
    assert len(outcome.result["candidates"]) == 2
    nothing = await call(ctx, "cancel_reminders", query="پرواز")
    assert "no upcoming reminder" in nothing.result["error"]


async def test_update_reminder_and_undo(ctx):
    reminder = await created(ctx, subject="دکتر", start="2026-10-05T14:00", alerts=["-1h"])
    outcome = await call(
        ctx, "update_reminder", query="دکتر", when_text="فردا ساعت ۵ عصر", start="2026-10-05T17:00"
    )
    moved = await ctx.reminders.get(reminder.id)
    assert local(moved) == datetime(2026, 10, 5, 17, 0) and moved.alert_specs == "before:60"
    await ctx.actions.undo(outcome.card.action_id)
    assert local(await ctx.reminders.get(reminder.id)) == datetime(2026, 10, 5, 14, 0)


async def test_list_reminders(ctx):
    await created(ctx, subject="دکتر", start="2026-10-05T14:00")
    listed = await call(ctx, "list_reminders")
    assert listed.result["reminders"][0]["start_jalali"] == "1405-07-13"


async def test_undo_created_reminder(ctx):
    outcome = await call(ctx, "create_reminder", subject="x", start="2026-10-05T14:00")
    await ctx.actions.undo(outcome.card.action_id)
    assert await ctx.reminders.get(outcome.result["created"]["id"]) is None


# --- General ---


async def test_report_tool(ctx):
    await call(ctx, "add_expenses", items=[{"description": "بنزین", "amount_text": "100k"}])
    outcome = await call(ctx, "get_report", period="today")
    assert outcome.result["total"] == 100_000 and outcome.card.kind == "report"
    assert "unknown period" in (await call(ctx, "get_report", period="decade")).result["error"]


async def test_convert_date_and_calculate(ctx):
    converted = await call(ctx, "convert_date", date_text="۱۵ آبان ۱۴۰۵")
    assert converted.result["date"].startswith("2026-11-06 Friday = 1405-08-15")
    assert (await call(ctx, "calculate", expression="0.15 * 2400000")).result["result"] == "360,000"
    assert "cannot calculate" in (await call(ctx, "calculate", expression="1/0")).result["error"]


async def test_settings_and_undo(ctx):
    outcome = await call(ctx, "update_settings", calendar="gregorian", morning_briefing=False)
    assert await ctx.settings.get_calendar() == Calendar.GREGORIAN
    assert not await ctx.settings.briefing_enabled()
    await ctx.actions.undo(outcome.card.action_id)
    assert await ctx.settings.get_calendar() == Calendar.JALALI
    assert await ctx.settings.briefing_enabled()
