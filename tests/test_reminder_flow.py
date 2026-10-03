"""End-to-end reminder conversations through the real dispatcher (fake Telegram, fake LLM)."""

from datetime import date, datetime, timedelta

from app import texts
from app.config import Calendar
from app.core.parsers.datetime_parser import DayTimes
from app.core.parsers.rules import parse_reminder
from app.services.reminders import ReminderDraft, ReminderService


async def _reminders(env):
    async with env.db() as session:
        return await ReminderService(session, _tz(), DayTimes()).upcoming()


def _tz():
    from zoneinfo import ZoneInfo

    return ZoneInfo("Asia/Tehran")


async def test_free_text_with_am_pm_question(env):
    await env.send("Doctor tomorrow at 2, remind me in the morning")
    assert "did you mean <b>02:00</b> or <b>14:00</b>" in env.session.sent[-1]

    await env.press(env.button("14:00"))
    card = env.session.edits[-1]
    assert "<b>New reminder</b>" in card
    assert "📝 Doctor" in card and "14:00" in card
    assert "🔔 09:00" in card
    assert "⭐ Important" in card  # LLM offline → keywords ("doctor")

    await env.press(env.button(texts.BTN_SAVE))
    assert "<b>Reminder saved</b>" in env.session.edits[-1]
    saved = await _reminders(env)
    assert [r.text for r in saved] == ["Doctor"]
    assert saved[0].important


async def test_form_with_alert_picker(env):
    env.llm.json_reply = {"important": False}
    await env.send(texts.BTN_NEW_REMINDER)
    assert env.session.sent[-1] == texts.REMINDER_ASK_DESCRIBE

    await env.send("call the bank tomorrow at 16:00")
    assert "When should I remind you?" in env.session.sent[-1]

    await env.press(env.button(texts.ALERT_LABELS["at"]))
    await env.press(env.button(texts.ALERT_LABELS["before:15"]))
    assert env.button(texts.BTN_SELECTED + texts.ALERT_LABELS["at"])  # shown as selected

    await env.press(env.button(texts.BTN_ALERTS_DONE))
    card = env.session.edits[-1]
    assert "🔔 15:45 · 16:00" in card
    assert "⭐" not in card.split("🔔")[1]

    await env.press(env.button(texts.BTN_IMPORTANT_OFF))  # toggle on
    assert "⭐ Important" in env.session.edits[-1]
    await env.press(env.button(texts.BTN_SAVE))
    saved = await _reminders(env)
    assert saved[0].text == "call the bank" and saved[0].important
    assert saved[0].alert_specs == "at,before:15"


async def test_picker_requires_a_choice(env):
    await env.send("call the bank tomorrow at 16:00, remind me")
    await env.press(env.button(texts.BTN_ALERTS_DONE))
    assert env.session.alerts[-1] == texts.REMINDER_ALERTS_NONE


async def test_custom_alert_time(env):
    await env.send("call the bank tomorrow at 16:00, remind me")
    await env.press(env.button(texts.BTN_OTHER_TIME))
    assert env.session.edits[-1] == texts.REMINDER_ASK_ALERT_TIME
    await env.send("2 ساعت قبلش")
    assert "🔔 14:00" in env.session.sent[-1]


async def test_missing_time_is_asked_then_llm_offline(env):
    await env.send("remind me to water the plants")
    assert env.session.sent[-1] == texts.REMINDER_ASK_WHEN
    await env.send("I don't know")
    assert env.session.sent[-1] == texts.REMINDER_WHEN_RETRY
    await env.send("tomorrow evening")
    assert "When should I remind you?" in env.session.sent[-1]


async def test_llm_extracts_when_rules_fail(env):
    tomorrow = (datetime.now(_tz()) + timedelta(days=1)).date().isoformat()
    env.llm.json_reply = {
        "subject": "dentist",
        "date": tomorrow,
        "time": "10:30",
        "important": True,
    }
    await env.send("remind me about the dentist sometime tomorrowish around half ten")
    assert env.llm.json_calls  # the LLM was asked
    assert "When should I remind you?" in env.session.sent[-1]


async def test_menu_button_leaves_the_form(env):
    await env.send(texts.BTN_NEW_REMINDER)
    await env.send(texts.BTN_SETTINGS)
    assert "<b>Settings</b>" in env.session.sent[-1]
    await env.send("What is the capital of France?")
    assert env.llm.calls  # went to chat, not to the reminder form


async def test_cancel(env):
    await env.send("Doctor tomorrow at 2, remind me")
    await env.press(env.button(texts.BTN_CANCEL))
    assert env.session.edits[-1] == texts.REMINDER_CANCELLED
    assert await _reminders(env) == []


async def _create(env, text: str) -> int:
    now = datetime.now(_tz())
    draft = ReminderDraft.from_parse(
        parse_reminder(text, now.date(), DayTimes()), text, now, Calendar.JALALI
    )
    async with env.db() as session:
        reminder = await ReminderService(session, _tz(), DayTimes()).create(draft, now)
        return reminder.id


async def test_list_open_edit_delete(env):
    rid = await _create(env, "remind me tomorrow at 09:00 to call mom")
    await env.send(texts.BTN_REMINDERS)
    assert env.session.sent[-1] == texts.REMINDERS_TITLE.format(count=1)

    await env.press(env.button("call mom"))
    assert "<b>Reminder</b>" in env.session.edits[-1]

    await env.press(env.button(texts.BTN_EDIT))
    assert "Send the reminder again" in env.session.edits[-1]
    await env.send("remind me tomorrow at 10am to call mom and dad")
    await env.press(env.button(texts.BTN_SAVE))
    reminders = await _reminders(env)
    assert [r.text for r in reminders] == ["call mom and dad"]
    assert reminders[0].id != rid

    await env.send(texts.BTN_REMINDERS)
    await env.press(env.button("call mom and dad"))
    await env.press(env.button(texts.BTN_DELETE))
    await env.press(env.button(texts.BTN_YES_DELETE))
    assert env.session.alerts[-1] == texts.REMINDER_DELETED
    assert env.session.edits[-1] == texts.REMINDERS_EMPTY


async def test_notification_buttons(env):
    rid = await _create(env, "remind me tomorrow at 09:00 to call mom")
    await env.press(f"rem:snooze:10:{rid}")
    assert env.session.alerts[-1].startswith("⏰ I'll remind you again at")
    await env.press(f"rem:done::{rid}")
    assert env.session.alerts[-1] == texts.MARKED_DONE
    assert await _reminders(env) == []


async def test_reminders_empty(env):
    await env.send(texts.BTN_REMINDERS)
    assert env.session.sent[-1] == texts.REMINDERS_EMPTY


def test_today_is_not_frozen():
    assert date.today().year >= 2026


async def test_reported_sentence_creates_a_reminder(env):
    """Regression: «یاد اوری» (no madda, with a space) used to go to the chat."""
    await env.send("یک یاد اوری تنظیم کن برای ۵ دقیقه دیگه میخوام کتاب بخونم")
    assert env.llm.calls == []  # not answered by the chat model
    assert "<b>New reminder</b>" in env.session.sent[-1]
    assert "میخوام کتاب بخونم" in env.session.sent[-1]
