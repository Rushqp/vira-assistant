"""⚙️ Settings screen: calendar and morning-briefing toggles, plus read-only system info."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app import texts
from app.bot.keyboards.inline import SettingsCb, settings_menu
from app.config import Calendar, Settings
from app.llm.providers import describe_providers
from app.services.settings import SettingsService
from app.utils.calendar import format_date, now_local

router = Router(name="settings")


def render_settings(config: Settings, calendar: Calendar, briefing: bool = True) -> str:
    stt = (
        texts.STT_ON.format(model=config.effective_stt_model)
        if config.stt_enabled
        else texts.STT_OFF
    )
    briefing_text = (
        texts.BRIEFING_ON.format(time=f"{config.morning_briefing_time:%H:%M}")
        if briefing
        else texts.BRIEFING_OFF
    )
    return texts.SETTINGS.format(
        calendar=texts.CALENDAR_NAMES[calendar],
        timezone=config.tz,
        today=format_date(now_local(config.timezone).date(), calendar),
        briefing=briefing_text,
        model=describe_providers(config),
        profile=config.profile.value,
        stt=stt,
    )


async def _screen(config: Settings, settings_service: SettingsService):
    calendar = await settings_service.get_calendar()
    briefing = await settings_service.briefing_enabled()
    return render_settings(config, calendar, briefing), settings_menu(calendar, briefing)


@router.message(F.text == texts.BTN_SETTINGS)
async def show_settings(
    message: Message, config: Settings, settings_service: SettingsService
) -> None:
    text, markup = await _screen(config, settings_service)
    await message.answer(text, reply_markup=markup)


@router.callback_query(SettingsCb.filter(F.action == "toggle_calendar"))
async def toggle_calendar(
    query: CallbackQuery, config: Settings, settings_service: SettingsService
) -> None:
    calendar = await settings_service.toggle_calendar()
    text, markup = await _screen(config, settings_service)
    if isinstance(query.message, Message):
        await query.message.edit_text(text, reply_markup=markup)
    await query.answer(texts.CALENDAR_CHANGED.format(calendar=texts.CALENDAR_NAMES[calendar]))


@router.callback_query(SettingsCb.filter(F.action == "toggle_briefing"))
async def toggle_briefing(
    query: CallbackQuery, config: Settings, settings_service: SettingsService
) -> None:
    enabled = await settings_service.toggle_briefing()
    text, markup = await _screen(config, settings_service)
    if isinstance(query.message, Message):
        await query.message.edit_text(text, reply_markup=markup)
    state = texts.BRIEFING_ON.format(time=f"{config.morning_briefing_time:%H:%M}")
    await query.answer(
        texts.BRIEFING_CHANGED.format(state=state if enabled else texts.BRIEFING_OFF)
    )
