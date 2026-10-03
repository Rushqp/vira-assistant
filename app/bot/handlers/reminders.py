"""⏰ Reminders: create (free text or form), list, edit, delete, and the notification buttons.

Creating a reminder is a small conversation driven by `ReminderDraft.next_step()`:
subject? → when? → am/pm? → clock time? → when to notify? → confirm (⭐ decided by the LLM).
The draft is kept in the FSM data between questions.
"""

import html
import re
from dataclasses import dataclass
from datetime import time

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.chat_action import ChatActionSender

from app import texts
from app.bot import views
from app.bot.keyboards.inline import (
    RemCb,
    alert_options,
    reminder_alerts,
    reminder_ampm,
    reminder_confirm,
    reminder_delete_confirm,
    reminder_detail,
    reminder_times,
    reminders_list,
)
from app.bot.states import ReminderForm
from app.config import Calendar, Settings
from app.core.parsers.datetime_parser import Moment
from app.core.parsers.rules import ReminderParse, has_reminder_trigger, parse_reminder
from app.llm.client import LLMClient
from app.services.reminder_ai import classify_importance, extract_reminder
from app.services.reminders import ReminderDraft, ReminderService
from app.services.settings import SettingsService
from app.utils.calendar import now_local

router = Router(name="reminders")

_BARE_TIME = re.compile(r"^\s*([0-9۰-۹]{1,2})(?:[:٫.]([0-9۰-۹]{2}))?\s*$")


@dataclass
class Flow:
    """What every step of the conversation needs."""

    config: Settings
    state: FSMContext
    llm: LLMClient
    calendar: Calendar

    @property
    def now(self):
        return now_local(self.config.timezone)


async def _flow(config, state, llm, settings_service: SettingsService) -> Flow:
    return Flow(config, state, llm, await settings_service.get_calendar())


async def _load(state: FSMContext) -> ReminderDraft | None:
    data = await state.get_data()
    return ReminderDraft.from_dict(data["draft"]) if data.get("draft") else None


async def _show(
    target: Message, text: str, markup: InlineKeyboardMarkup | None = None, edit: bool = False
) -> None:
    if edit:
        try:
            await target.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest:
            pass
    await target.answer(text, reply_markup=markup)


def _as_time_phrase(text: str) -> str:
    """A bare `8` or `8:30` typed as an answer means a clock time."""
    return f"ساعت {text.strip()}" if _BARE_TIME.match(text) else text


# --- The conversation ---


async def advance(target: Message, flow: Flow, draft: ReminderDraft, edit: bool = False) -> None:
    """Ask the next missing piece, or show the confirmation card when everything is known."""
    day_times = flow.config.day_times
    step = draft.next_step(flow.now, day_times)
    subject = html.escape(draft.subject)

    if step == "past":
        draft.date = draft.time = None
        draft.ambiguous = draft.flexible_week = False
    if step == "alerts_past":
        draft.alerts, draft.extra_alerts = None, []
    await flow.state.update_data(draft=draft.to_dict())

    if step == "subject":
        await flow.state.set_state(ReminderForm.subject)
        await _show(target, texts.REMINDER_ASK_SUBJECT, edit=edit)
    elif step in ("when", "past"):
        await flow.state.set_state(ReminderForm.when)
        message = texts.REMINDER_PAST if step == "past" else texts.REMINDER_ASK_WHEN
        await _show(target, message, edit=edit)
    elif step == "ambiguous":
        am = time.fromisoformat(draft.time or "00:00")
        pm = time((am.hour + 12) % 24, am.minute)
        await flow.state.set_state(ReminderForm.buttons)
        await _show(
            target,
            texts.REMINDER_ASK_AMPM.format(subject=subject, am=f"{am:%H:%M}", pm=f"{pm:%H:%M}"),
            reminder_ampm(f"{am:%H:%M}", f"{pm:%H:%M}"),
            edit,
        )
    elif step == "time":
        await flow.state.set_state(ReminderForm.time)
        await _show(target, texts.REMINDER_ASK_TIME, reminder_times(day_times), edit)
    elif step in ("alerts", "alerts_past"):
        await flow.state.set_state(ReminderForm.buttons)
        await flow.state.update_data(alert_pick=[])
        event, all_day = draft.event_datetime(flow.now)
        text = texts.REMINDER_ASK_ALERTS.format(
            subject=subject, when=views.format_when(event, all_day, flow.calendar)
        )
        if step == "alerts_past":
            text = texts.REMINDER_ALERTS_PAST + text
        options = alert_options(all_day, draft.time, day_times)
        await _show(target, text, reminder_alerts(options, []), edit)
    else:
        if draft.important is None:
            async with ChatActionSender.typing(chat_id=target.chat.id, bot=target.bot):
                draft.important = await classify_importance(flow.llm, draft.subject)
            await flow.state.update_data(draft=draft.to_dict())
        await flow.state.set_state(ReminderForm.buttons)
        await _show(target, _confirm_text(flow, draft), reminder_confirm(draft.important), edit)


def _confirm_text(flow: Flow, draft: ReminderDraft) -> str:
    card = views.draft_card(draft, flow.now, flow.config.day_times, flow.calendar)
    template = texts.REMINDER_CONFIRM_EDIT if draft.replace_id else texts.REMINDER_CONFIRM
    return template.format(card=card)


async def start(message: Message, flow: Flow, text: str, replace_id: int | None = None) -> None:
    now = flow.now
    parse = parse_reminder(text, now.date(), flow.config.day_times)
    draft = ReminderDraft.from_parse(parse, text, now, flow.calendar)
    draft.replace_id = replace_id
    if draft.next_step(now, flow.config.day_times) == "when":
        # The rules found no date/time: ask the LLM before asking the user.
        async with ChatActionSender.typing(chat_id=message.chat.id, bot=message.bot):
            found = await extract_reminder(flow.llm, text, now)
        if found:
            subject, day, clock, important = found
            draft.subject = draft.subject or subject
            draft.date = day.isoformat() if day else None
            draft.time = f"{clock:%H:%M}" if clock else None
            draft.important = important
    await advance(message, flow, draft)


# --- Entry points ---


@router.message(F.text == texts.BTN_NEW_REMINDER)
async def new_reminder(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ReminderForm.describe)
    await message.answer(texts.REMINDER_ASK_DESCRIBE)


@router.message(ReminderForm.describe, F.text)
async def describe(
    message: Message, state: FSMContext, config: Settings, llm: LLMClient,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    replace_id = (await state.get_data()).get("replace_id")
    flow = await _flow(config, state, llm, settings_service)
    await state.set_data({})
    await start(message, flow, message.text or "", replace_id)


@router.message(ReminderForm.subject, F.text)
async def got_subject(
    message: Message, state: FSMContext, config: Settings, llm: LLMClient,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    draft = await _load(state)
    if draft is None:
        await state.clear()
        await message.answer(texts.REMINDER_EXPIRED)
        return
    draft.subject = (message.text or "").strip()
    await advance(message, await _flow(config, state, llm, settings_service), draft)


@router.message(ReminderForm.when, F.text)
async def got_when(
    message: Message, state: FSMContext, config: Settings, llm: LLMClient,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    draft = await _load(state)
    if draft is None:
        await state.clear()
        await message.answer(texts.REMINDER_EXPIRED)
        return
    flow = await _flow(config, state, llm, settings_service)
    parse = parse_reminder(_as_time_phrase(message.text or ""), flow.now.date(), config.day_times)
    if parse.event.empty:
        await message.answer(texts.REMINDER_WHEN_RETRY)
        return
    draft.apply_event(parse, flow.now, flow.calendar)
    if draft.alerts is None:
        draft.apply_notify(parse, flow.now)
    await advance(message, flow, draft)


@router.message(ReminderForm.time, F.text)
async def got_time(
    message: Message, state: FSMContext, config: Settings, llm: LLMClient,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    draft = await _load(state)
    if draft is None:
        await state.clear()
        await message.answer(texts.REMINDER_EXPIRED)
        return
    flow = await _flow(config, state, llm, settings_service)
    parse = parse_reminder(_as_time_phrase(message.text or ""), flow.now.date(), config.day_times)
    if parse.event.time is None:
        await message.answer(
            texts.REMINDER_TIME_RETRY, reply_markup=reminder_times(config.day_times)
        )
        return
    draft.time = f"{parse.event.time:%H:%M}"
    draft.ambiguous = parse.event.ambiguous
    await advance(message, flow, draft)


@router.message(ReminderForm.alert_time, F.text)
async def got_alert_time(
    message: Message, state: FSMContext, config: Settings, llm: LLMClient,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    draft = await _load(state)
    if draft is None:
        await state.clear()
        await message.answer(texts.REMINDER_EXPIRED)
        return
    flow = await _flow(config, state, llm, settings_service)
    parse = parse_reminder(_as_time_phrase(message.text or ""), flow.now.date(), config.day_times)
    moment: Moment = parse.event
    if moment.empty:
        await message.answer(texts.REMINDER_ALERT_TIME_RETRY)
        return
    picked = (await state.get_data()).get("alert_pick", [])
    as_notify = ReminderParse(
        subject="", event=Moment(), notify=moment, notify_at_event=False, has_trigger=True
    )
    draft.apply_notify(as_notify, flow.now)
    draft.alerts = list(dict.fromkeys(picked + (draft.alerts or [])))
    await advance(message, flow, draft)


@router.message(F.text == texts.BTN_REMINDERS)
async def show_reminders(
    message: Message, config: Settings, reminder_service: ReminderService,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    text, markup = await _render_list(config, reminder_service, settings_service)
    await message.answer(text, reply_markup=markup)


@router.message(F.text.func(has_reminder_trigger), ~F.text.startswith("/"))
async def reminder_from_text(
    message: Message, state: FSMContext, config: Settings, llm: LLMClient,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    await state.clear()
    await start(message, await _flow(config, state, llm, settings_service), message.text or "")


# --- Buttons while creating ---


async def _query_flow(
    query: CallbackQuery, state: FSMContext, config, llm, settings_service
) -> tuple[Message, Flow, ReminderDraft] | None:
    draft = await _load(state)
    if draft is None or not isinstance(query.message, Message):
        await query.answer(texts.REMINDER_EXPIRED, show_alert=True)
        return None
    return query.message, await _flow(config, state, llm, settings_service), draft


@router.callback_query(RemCb.filter(F.action.in_({"ampm", "time"})))
async def pick_time(
    query: CallbackQuery, callback_data: RemCb, state: FSMContext, config: Settings,
    llm: LLMClient, settings_service: SettingsService,
) -> None:  # fmt: skip
    loaded = await _query_flow(query, state, config, llm, settings_service)
    if loaded is None:
        return
    message, flow, draft = loaded
    if callback_data.action == "ampm":
        am = time.fromisoformat(draft.time or "00:00")
        chosen = am if callback_data.value == "am" else time((am.hour + 12) % 24, am.minute)
    else:
        chosen = config.day_times.of(callback_data.value)  # type: ignore[arg-type]
    draft.time, draft.ambiguous = f"{chosen:%H:%M}", False
    await query.answer()
    await advance(message, flow, draft, edit=True)


@router.callback_query(RemCb.filter(F.action == "alert"))
async def toggle_alert(
    query: CallbackQuery, callback_data: RemCb, state: FSMContext, config: Settings,
    llm: LLMClient, settings_service: SettingsService,
) -> None:  # fmt: skip
    loaded = await _query_flow(query, state, config, llm, settings_service)
    if loaded is None:
        return
    message, flow, draft = loaded
    _, all_day = draft.event_datetime(flow.now)
    options = alert_options(all_day, draft.time, config.day_times)
    index = int(callback_data.value)
    if index >= len(options):
        await query.answer()
        return
    spec = options[index][0]
    picked: list[str] = (await state.get_data()).get("alert_pick", [])
    picked = [p for p in picked if p != spec] if spec in picked else [*picked, spec]
    await state.update_data(alert_pick=picked)
    await message.edit_reply_markup(reply_markup=reminder_alerts(options, picked))
    await query.answer()


@router.callback_query(RemCb.filter(F.action == "alert_other"))
async def other_alert_time(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ReminderForm.alert_time)
    if isinstance(query.message, Message):
        await query.message.edit_text(texts.REMINDER_ASK_ALERT_TIME)
    await query.answer()


@router.callback_query(RemCb.filter(F.action == "alerts_done"))
async def alerts_done(
    query: CallbackQuery, state: FSMContext, config: Settings, llm: LLMClient,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    loaded = await _query_flow(query, state, config, llm, settings_service)
    if loaded is None:
        return
    message, flow, draft = loaded
    picked = (await state.get_data()).get("alert_pick", [])
    if not picked:
        await query.answer(texts.REMINDER_ALERTS_NONE, show_alert=True)
        return
    draft.alerts = picked
    await query.answer()
    await advance(message, flow, draft, edit=True)


@router.callback_query(RemCb.filter(F.action == "star"))
async def toggle_star(
    query: CallbackQuery, state: FSMContext, config: Settings, llm: LLMClient,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    loaded = await _query_flow(query, state, config, llm, settings_service)
    if loaded is None:
        return
    message, flow, draft = loaded
    draft.important = not draft.important
    await state.update_data(draft=draft.to_dict())
    await message.edit_text(
        _confirm_text(flow, draft), reply_markup=reminder_confirm(draft.important)
    )
    await query.answer()


@router.callback_query(RemCb.filter(F.action == "save"))
async def save(
    query: CallbackQuery, state: FSMContext, config: Settings, llm: LLMClient,
    settings_service: SettingsService, reminder_service: ReminderService,
) -> None:  # fmt: skip
    loaded = await _query_flow(query, state, config, llm, settings_service)
    if loaded is None:
        return
    message, flow, draft = loaded
    reminder = await reminder_service.create(draft, flow.now)
    await state.clear()
    card = views.reminder_card(reminder, config.timezone, flow.calendar)
    await message.edit_text(texts.REMINDER_SAVED.format(card=card))
    await query.answer()


@router.callback_query(RemCb.filter(F.action == "edit"))
async def edit_draft(query: CallbackQuery, state: FSMContext) -> None:
    draft = await _load(state)
    if draft is None or not isinstance(query.message, Message):
        await query.answer(texts.REMINDER_EXPIRED, show_alert=True)
        return
    await state.set_state(ReminderForm.describe)
    await state.set_data({"replace_id": draft.replace_id})
    await query.message.edit_text(texts.REMINDER_EDIT_PROMPT.format(raw=html.escape(draft.raw)))
    await query.answer()


@router.callback_query(RemCb.filter(F.action == "cancel"))
async def cancel(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(query.message, Message):
        await query.message.edit_text(texts.REMINDER_CANCELLED)
    await query.answer()


# --- Notification buttons ---


@router.callback_query(RemCb.filter(F.action == "done"))
async def notification_done(
    query: CallbackQuery, callback_data: RemCb, reminder_service: ReminderService
) -> None:
    reminder = await reminder_service.mark_done(callback_data.rid)
    if reminder is None:
        await query.answer(texts.REMINDER_NOT_FOUND, show_alert=True)
        return
    if isinstance(query.message, Message):
        await query.message.edit_text((query.message.html_text or "") + texts.MARKED_DONE_LINE)
    await query.answer(texts.MARKED_DONE)


@router.callback_query(RemCb.filter(F.action == "snooze"))
async def notification_snooze(
    query: CallbackQuery, callback_data: RemCb, reminder_service: ReminderService
) -> None:
    when = await reminder_service.snooze(callback_data.rid, int(callback_data.value))
    if when is None:
        await query.answer(texts.REMINDER_NOT_FOUND, show_alert=True)
        return
    clock = f"{when:%H:%M}"
    if isinstance(query.message, Message):
        await query.message.edit_text(
            (query.message.html_text or "") + texts.SNOOZED_LINE.format(time=clock)
        )
    await query.answer(texts.SNOOZED.format(time=clock))


# --- List / detail / delete / edit ---


async def _render_list(
    config: Settings, reminder_service: ReminderService, settings_service: SettingsService
) -> tuple[str, InlineKeyboardMarkup | None]:
    reminders = await reminder_service.upcoming()
    if not reminders:
        return texts.REMINDERS_EMPTY, None
    calendar = await settings_service.get_calendar()
    items = [(r.id, views.reminder_list_label(r, config.timezone, calendar)) for r in reminders]
    return texts.REMINDERS_TITLE.format(count=len(reminders)), reminders_list(items)


@router.callback_query(RemCb.filter(F.action == "list"))
async def back_to_list(
    query: CallbackQuery, config: Settings, reminder_service: ReminderService,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    text, markup = await _render_list(config, reminder_service, settings_service)
    if isinstance(query.message, Message):
        await query.message.edit_text(text, reply_markup=markup)
    await query.answer()


@router.callback_query(RemCb.filter(F.action == "open"))
async def open_reminder(
    query: CallbackQuery, callback_data: RemCb, config: Settings,
    reminder_service: ReminderService, settings_service: SettingsService,
) -> None:  # fmt: skip
    reminder = await reminder_service.get(callback_data.rid)
    if reminder is None or not isinstance(query.message, Message):
        await query.answer(texts.REMINDER_NOT_FOUND, show_alert=True)
        return
    calendar = await settings_service.get_calendar()
    card = views.reminder_card(reminder, config.timezone, calendar)
    await query.message.edit_text(
        texts.REMINDER_DETAIL.format(card=card), reply_markup=reminder_detail(reminder.id)
    )
    await query.answer()


@router.callback_query(RemCb.filter(F.action == "delete"))
async def ask_delete_reminder(
    query: CallbackQuery, callback_data: RemCb, reminder_service: ReminderService
) -> None:
    reminder = await reminder_service.get(callback_data.rid)
    if reminder is None or not isinstance(query.message, Message):
        await query.answer(texts.REMINDER_NOT_FOUND, show_alert=True)
        return
    await query.message.edit_text(
        texts.REMINDER_DELETE_CONFIRM.format(subject=html.escape(reminder.text)),
        reply_markup=reminder_delete_confirm(reminder.id),
    )
    await query.answer()


@router.callback_query(RemCb.filter(F.action == "confirm_delete"))
async def delete_reminder(
    query: CallbackQuery, callback_data: RemCb, config: Settings,
    reminder_service: ReminderService, settings_service: SettingsService,
) -> None:  # fmt: skip
    await reminder_service.delete(callback_data.rid)
    text, markup = await _render_list(config, reminder_service, settings_service)
    if isinstance(query.message, Message):
        await query.message.edit_text(text, reply_markup=markup)
    await query.answer(texts.REMINDER_DELETED)


@router.callback_query(RemCb.filter(F.action == "item_edit"))
async def edit_reminder(
    query: CallbackQuery, callback_data: RemCb, state: FSMContext,
    reminder_service: ReminderService,
) -> None:  # fmt: skip
    reminder = await reminder_service.get(callback_data.rid)
    if reminder is None or not isinstance(query.message, Message):
        await query.answer(texts.REMINDER_NOT_FOUND, show_alert=True)
        return
    await state.set_state(ReminderForm.describe)
    await state.set_data({"replace_id": reminder.id})
    await query.message.edit_text(
        texts.REMINDER_EDIT_PROMPT.format(raw=html.escape(reminder.raw_text or reminder.text))
    )
    await query.answer()
