"""⚙️ Settings screen: calendar, ☀️ morning briefing and 🌙 nightly report (on/off and time),
plus read-only system info.

🏷 Categories and 🤖 AI model open their own screens (`categories.py`, `ai_models.py`). The
agent can change the same settings from the chat (`update_settings` tool).
"""

import html
from datetime import time

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app import texts
from app.bot.keyboards.inline import DigestCb, SettingsCb, digest_menu, settings_menu
from app.bot.states import SettingsForm
from app.config import Calendar, Settings
from app.core.parsers.rules import parse_clock
from app.llm.providers import ProviderChain, describe_providers
from app.services.settings import NIGHTLY_EARLIEST, SettingsService
from app.stt.chain import SpeechChain, describe_engines
from app.utils.calendar import format_date, now_local

router = Router(name="settings")


def state_text(enabled: bool, at: time) -> str:
    """`on (22:00)` / `off`."""
    return texts.BRIEFING_ON.format(time=f"{at:%H:%M}") if enabled else texts.BRIEFING_OFF


def render_settings(
    config: Settings,
    calendar: Calendar,
    briefing: bool = True,
    model: str | None = None,
    *,
    briefing_at: time | None = None,
    nightly: bool = True,
    nightly_at: time | None = None,
    voice: str | None = None,
) -> str:
    engines = voice if voice is not None else describe_engines(config)
    if not config.stt_enabled:
        stt = texts.STT_OFF
    else:
        stt = texts.STT_ON.format(model=html.escape(engines or texts.STT_NO_ENGINE))
    return texts.SETTINGS.format(
        calendar=texts.CALENDAR_NAMES[calendar],
        timezone=config.tz,
        today=format_date(now_local(config.timezone).date(), calendar),
        briefing=state_text(briefing, briefing_at or config.morning_briefing_time),
        nightly=state_text(nightly, nightly_at or config.daily_report_time),
        model=html.escape(model or describe_providers(config)),
        profile=config.profile.value,
        stt=stt,
    )


async def digest_state(
    kind: str, config: Settings, settings_service: SettingsService
) -> tuple[bool, time]:
    """(enabled, time) of the morning briefing or the nightly report."""
    if kind == "briefing":
        return (
            await settings_service.briefing_enabled(),
            await settings_service.briefing_time(config.morning_briefing_time),
        )
    return (
        await settings_service.nightly_enabled(),
        await settings_service.nightly_time(config.daily_report_time),
    )


async def _set_digest(
    kind: str, settings_service: SettingsService, *, enabled: bool, at: time | None = None
) -> None:
    if kind == "briefing":
        if at is not None:
            await settings_service.set_briefing_time(at)
        await settings_service.set_briefing(enabled)
    else:
        if at is not None:
            await settings_service.set_nightly_time(at)
        await settings_service.set_nightly(enabled)


async def _screen(
    config: Settings, settings_service: SettingsService, llm: object, stt: object = None
):
    calendar = await settings_service.get_calendar()
    briefing, briefing_at = await digest_state("briefing", config, settings_service)
    nightly, nightly_at = await digest_state("nightly", config, settings_service)
    model = llm.model if isinstance(llm, ProviderChain) and llm.clients else None
    voice = " → ".join(e.label for e in stt.engines) if isinstance(stt, SpeechChain) else None
    text = render_settings(
        config,
        calendar,
        briefing,
        model,
        briefing_at=briefing_at,
        nightly=nightly,
        nightly_at=nightly_at,
        voice=voice,
    )
    return text, settings_menu(calendar)


async def _digest_screen(kind: str, config: Settings, settings_service: SettingsService):
    enabled, at = await digest_state(kind, config, settings_service)
    clock = f"{at:%H:%M}"
    state = (texts.DIGEST_STATE_ON if enabled else texts.DIGEST_STATE_OFF).format(time=clock)
    lines = [texts.DIGEST_TITLES[kind], texts.DIGEST_ABOUT[kind], "", state, "", texts.DIGEST_HELP]
    return "\n".join(lines), digest_menu(kind, enabled, clock)


async def _edit(message: Message, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:  # the same button pressed twice
        if "message is not modified" not in str(exc):
            raise


@router.message(F.text == texts.BTN_SETTINGS)
async def show_settings(
    message: Message,
    config: Settings,
    settings_service: SettingsService,
    llm: object,
    stt: object = None,
) -> None:
    text, markup = await _screen(config, settings_service, llm, stt)
    await message.answer(text, reply_markup=markup)


# "toggle_briefing": a button of settings messages sent before v0.5
@router.callback_query(SettingsCb.filter(F.action.in_({"show", "toggle_briefing"})))
async def back_to_settings(
    query: CallbackQuery,
    state: FSMContext,
    config: Settings,
    settings_service: SettingsService,
    llm: object,
    stt: object = None,
) -> None:
    if await state.get_state() == SettingsForm.digest_time.state:
        await state.clear()
    text, markup = await _screen(config, settings_service, llm, stt)
    if isinstance(query.message, Message):
        await _edit(query.message, text, markup)
    await query.answer()


@router.callback_query(SettingsCb.filter(F.action == "toggle_calendar"))
async def toggle_calendar(
    query: CallbackQuery,
    config: Settings,
    settings_service: SettingsService,
    llm: object,
    stt: object = None,
) -> None:
    calendar = await settings_service.toggle_calendar()
    text, markup = await _screen(config, settings_service, llm, stt)
    if isinstance(query.message, Message):
        await _edit(query.message, text, markup)
    await query.answer(texts.CALENDAR_CHANGED.format(calendar=texts.CALENDAR_NAMES[calendar]))


# --- ☀️ Morning briefing / 🌙 Nightly report ---


@router.callback_query(DigestCb.filter(F.action == "open"))
async def open_digest(
    query: CallbackQuery, callback_data: DigestCb, config: Settings,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    text, markup = await _digest_screen(callback_data.kind, config, settings_service)
    if isinstance(query.message, Message):
        await _edit(query.message, text, markup)
    await query.answer()


@router.callback_query(DigestCb.filter(F.action.in_({"on", "off", "time"})))
async def change_digest(
    query: CallbackQuery, callback_data: DigestCb, config: Settings,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    kind = callback_data.kind
    at = None
    if callback_data.action == "time":
        value = callback_data.value
        at = time(int(value[:2]), int(value[2:]))
    await _set_digest(kind, settings_service, enabled=callback_data.action != "off", at=at)
    text, markup = await _digest_screen(kind, config, settings_service)
    if isinstance(query.message, Message):
        await _edit(query.message, text, markup)
    enabled, current = await digest_state(kind, config, settings_service)
    await query.answer(
        texts.DIGEST_CHANGED.format(
            name=texts.DIGEST_NAMES[kind], state=state_text(enabled, current)
        )
    )


@router.callback_query(DigestCb.filter(F.action == "other"))
async def ask_time(query: CallbackQuery, callback_data: DigestCb, state: FSMContext) -> None:
    await state.set_state(SettingsForm.digest_time)
    await state.update_data(digest=callback_data.kind)
    if isinstance(query.message, Message):
        await query.message.answer(texts.DIGEST_ASK_TIME)
    await query.answer()


@router.message(SettingsForm.digest_time, F.text)
async def got_time(
    message: Message, state: FSMContext, config: Settings, settings_service: SettingsService
) -> None:
    kind = (await state.get_data()).get("digest", "nightly")
    today = now_local(config.timezone).date()
    at = parse_clock(message.text or "", today, config.day_times, evening=kind == "nightly")
    if at is None:
        await message.answer(texts.DIGEST_TIME_RETRY)
        return
    if kind == "nightly" and at < NIGHTLY_EARLIEST:
        await message.answer(texts.DIGEST_NIGHTLY_RANGE)
        return
    await state.clear()
    await _set_digest(kind, settings_service, enabled=True, at=at)
    text, markup = await _digest_screen(kind, config, settings_service)
    await message.answer(text, reply_markup=markup)
