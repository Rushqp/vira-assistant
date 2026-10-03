"""⚙️ Settings screen: calendar toggle and read-only system info."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app import texts
from app.bot.keyboards.inline import SettingsCb, settings_menu
from app.config import Calendar, Settings
from app.services.settings import SettingsService
from app.utils.calendar import format_date, now_local

router = Router(name="settings")


def render_settings(config: Settings, calendar: Calendar) -> str:
    stt = (
        texts.STT_ON.format(model=config.effective_stt_model)
        if config.stt_enabled
        else texts.STT_OFF
    )
    return texts.SETTINGS.format(
        calendar=texts.CALENDAR_NAMES[calendar],
        timezone=config.tz,
        today=format_date(now_local(config.timezone).date(), calendar),
        model=config.effective_llm_model,
        profile=config.profile.value,
        stt=stt,
    )


@router.message(F.text == texts.BTN_SETTINGS)
async def show_settings(
    message: Message, config: Settings, settings_service: SettingsService
) -> None:
    calendar = await settings_service.get_calendar()
    await message.answer(render_settings(config, calendar), reply_markup=settings_menu(calendar))


@router.callback_query(SettingsCb.filter(F.action == "toggle_calendar"))
async def toggle_calendar(
    query: CallbackQuery, config: Settings, settings_service: SettingsService
) -> None:
    calendar = await settings_service.toggle_calendar()
    if isinstance(query.message, Message):
        await query.message.edit_text(
            render_settings(config, calendar), reply_markup=settings_menu(calendar)
        )
    await query.answer(texts.CALENDAR_CHANGED.format(calendar=texts.CALENDAR_NAMES[calendar]))
