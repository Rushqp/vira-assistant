"""Smoke tests for the bot wiring (no network)."""

from app import texts
from app.bot.handlers.settings import render_settings
from app.bot.keyboards.inline import SettingsCb, settings_menu
from app.bot.keyboards.reply import main_menu
from app.config import Calendar
from app.main import build_dispatcher
from tests.fakes import FakeLLM


def test_main_menu_layout():
    rows = [[b.text for b in row] for row in main_menu().keyboard]
    assert [len(r) for r in rows] == [3, 3, 3, 1]
    assert rows[0] == [texts.BTN_NEW_CHAT, texts.BTN_CHATS, texts.BTN_NEW_REMINDER]
    assert rows[-1] == [texts.BTN_SETTINGS]  # Excel files are asked for in the chat (v0.5)


def test_every_menu_button_is_handled():
    labels = {b.text for row in main_menu().keyboard for b in row}
    implemented = {
        texts.BTN_SETTINGS,
        texts.BTN_NEW_CHAT,
        texts.BTN_CHATS,
        texts.BTN_NEW_REMINDER,
        texts.BTN_REMINDERS,
        texts.BTN_ADD_EXPENSE,
        texts.BTN_TODAY_REPORT,
        texts.BTN_MONTH_REPORT,
        texts.BTN_TODOS,
        texts.BTN_NOTES,
    }
    assert labels == implemented  # every button works since v0.7


def test_settings_keyboard_offers_the_other_calendar():
    button = settings_menu(Calendar.JALALI).inline_keyboard[0][0]
    assert "Gregorian" in button.text
    assert SettingsCb.unpack(button.callback_data).action == "toggle_calendar"
    assert "Jalali" in settings_menu(Calendar.GREGORIAN).inline_keyboard[0][0].text


def test_render_settings(config):
    text = render_settings(config, Calendar.JALALI)
    assert "Jalali (Shamsi)" in text
    assert "qwen3:4b · Local" in text
    assert "Asia/Tehran" in text
    assert "Morning briefing: <b>on (08:00)</b>" in text
    assert "Nightly report: <b>on (22:00)</b>" in text


def test_dispatcher_builds(config, sessionmaker):
    dp = build_dispatcher(config, sessionmaker, FakeLLM())  # type: ignore[arg-type]
    assert {"message", "callback_query"} <= set(dp.resolve_used_update_types())
