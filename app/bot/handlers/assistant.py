"""💬 Free text → the agent → result cards with ↩️ Undo / ✏️ Edit.

A text message is handled in this order:
1. instant answers without a model: calculator, "what's the date?"
2. the agent (app/agent): understands the message and acts through tools
3. if no tool-capable model is reachable: the rule-based pipeline (v0.3/v0.4) and plain chat
"""

import asyncio
import html
import re
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.chat_action import ChatActionSender
from loguru import logger

from app import texts
from app.agent.actions import ActionLog
from app.agent.core import Agent, AgentUnavailable
from app.agent.tools import Card, ToolContext
from app.agent.tools.expenses import save_expense_draft
from app.bot.agent_ui import (
    UiDeps,
    render_card,
    render_reminder,
    render_saved_expenses,
    send_notices,
)
from app.bot.keyboards.inline import (
    ActCb,
    agent_scale,
    alert_options,
    saved_expense_categories,
    saved_expense_items,
)
from app.bot.states import AgentForm
from app.bot.streaming import MessageStreamer
from app.config import Calendar, Settings
from app.core.parsers.expense_rules import has_expense_intent, parse_report_request
from app.core.parsers.rules import has_reminder_trigger
from app.llm.client import LanguageModel, LLMError
from app.services.chat import ChatService
from app.services.expenses import ExpenseDraft, ExpenseService
from app.services.reminders import ReminderService, from_utc
from app.services.settings import SettingsService
from app.services.tools import answer_builtin
from app.utils.calendar import now_local
from app.utils.formatting import format_money

router = Router(name="assistant")

# One answer at a time: keeps the transcript in order and a CPU model can't do two anyway.
_generation_lock = asyncio.Lock()

# Typed answers to "thousand or million?"
_SCALE_ANSWERS = {
    "k": re.compile(r"^\s*(?:هزار|هزار تومن|هزار تومان|thousand|k|000)\s*$", re.I),
    "m": re.compile(r"^\s*(?:میلیون|ملیون|میلیون تومن|میلیون تومان|million|m|mil)\s*$", re.I),
}
_HINTS = {"reminder": texts.AGENT_HINT_REMINDER, "expense": texts.AGENT_HINT_EXPENSE}


@dataclass
class Deps:
    """Everything a turn needs (injected by aiogram from middleware data)."""

    message: Message
    state: FSMContext
    config: Settings
    llm: LanguageModel
    agent: Agent
    chat_service: ChatService
    reminder_service: ReminderService
    expense_service: ExpenseService
    settings_service: SettingsService
    action_log: ActionLog
    calendar: Calendar

    def ui(self) -> UiDeps:
        return UiDeps(
            self.config,
            self.calendar,
            self.expense_service,
            self.reminder_service,
            self.settings_service,
        )

    def tool_context(self, user_text: str) -> ToolContext:
        return ToolContext(
            config=self.config,
            calendar=self.calendar,
            now=now_local(self.config.timezone),
            user_text=user_text,
            expenses=self.expense_service,
            reminders=self.reminder_service,
            settings=self.settings_service,
            actions=self.action_log,
        )


async def _deps(message: Message, state: FSMContext, data: dict) -> Deps:
    settings_service: SettingsService = data["settings_service"]
    return Deps(
        message=message,
        state=state,
        config=data["config"],
        llm=data["llm"],
        agent=data["agent"],
        chat_service=data["chat_service"],
        reminder_service=data["reminder_service"],
        expense_service=data["expense_service"],
        settings_service=settings_service,
        action_log=data["action_log"],
        calendar=await settings_service.get_calendar(),
    )


async def _show(target: Message, text: str, markup=None, edit: bool = False) -> None:
    if edit:
        try:
            await target.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest:
            pass
    await target.answer(text, reply_markup=markup)


async def send_cards(message: Message, cards: list[Card], deps: Deps) -> None:
    ui = deps.ui()
    for card in cards:
        rendered = await render_card(card, ui)
        if rendered:
            await message.answer(rendered[0], reply_markup=rendered[1])


# --- The agent turn ---


async def run_agent(deps: Deps, text: str, hint: str = "") -> None:
    message = deps.message
    chat = await deps.chat_service.active_session()
    history = [
        {"role": row.role, "content": row.content}
        for row in await deps.chat_service.history(chat.id)
    ]
    streamer = MessageStreamer(message)
    async with _generation_lock, ChatActionSender.typing(chat_id=message.chat.id, bot=message.bot):
        try:
            result = await deps.agent.run(
                deps.tool_context(text), history, text, on_text=streamer.push, hint=hint
            )
        except AgentUnavailable as exc:
            logger.info("Agent unavailable ({}): rule-based fallback", exc)
            # Say why the answer is basic before it comes (e.g. "free quota used up").
            await send_notices(message.bot, message.chat.id, deps.llm, deps.config.timezone)
            await fallback(deps, text, hint)
            return
        except LLMError as exc:  # failed after part of the answer was shown
            await streamer.finish(
                f"\n\n{texts.LLM_ERRORS.get(exc.kind, texts.LLM_ERRORS['failed'])}"
            )
            return

    if not streamer.text.strip() and result.text:  # non-streaming providers: show it now
        await streamer.push(result.text)
    if streamer.text.strip():
        await streamer.finish()
    await send_cards(message, result.cards, deps)
    if result.clarification:
        draft = ExpenseDraft.from_dict(result.clarification.data)
        await ask_scale(message, deps, draft)
    if not (streamer.text.strip() or result.cards or result.clarification):
        await message.answer(texts.LLM_EMPTY)

    transcript = "\n".join(filter(None, [result.text, *result.notes])).strip()
    if transcript:
        await deps.chat_service.remember(chat.id, text, transcript)


# --- Thousand or million? ---


async def ask_scale(target: Message, deps: Deps, draft: ExpenseDraft, edit: bool = False) -> None:
    index = next(i for i, item in enumerate(draft.items) if item.ambiguous)
    item = draft.items[index]
    thousand, million = item.choices(deps.config.currency)  # type: ignore[arg-type]
    await deps.state.set_state(AgentForm.pending)
    await deps.state.update_data(agent_pending=draft.to_dict())
    label = texts.CURRENCY_LABELS[deps.config.currency.value]
    await _show(
        target,
        texts.EXPENSE_ASK_SCALE.format(
            description=html.escape(item.description or texts.EXPENSE_NO_DESCRIPTION),
            raw=f"{item.raw_amount:g}",
        ),
        agent_scale(format_money(thousand, label), format_money(million, label)),
        edit,
    )


async def resolve_scale(deps: Deps, choice: str, target: Message, edit: bool) -> None:
    data = await deps.state.get_data()
    if not data.get("agent_pending"):
        await target.answer(texts.EXPENSE_EXPIRED)
        return
    if choice == "cancel":
        await deps.state.clear()
        await _show(target, texts.EXPENSE_CANCELLED, edit=edit)
        return
    draft = ExpenseDraft.from_dict(data["agent_pending"])
    item = next(i for i in draft.items if i.ambiguous)
    thousand, million = item.choices(deps.config.currency)  # type: ignore[arg-type]
    item.amount = thousand if choice == "k" else million
    item.raw_amount = item.raw_currency = None
    if any(i.ambiguous for i in draft.items):
        await ask_scale(target, deps, draft, edit)
        return
    await deps.state.clear()
    outcome = await save_expense_draft(deps.tool_context(draft.raw), draft)
    rendered = await render_card(outcome.card, deps.ui()) if outcome.card else None
    if rendered:
        await _show(target, rendered[0], rendered[1], edit)
    await deps.chat_service.add_note(outcome.note)


# --- When no model is available ---


async def fallback(deps: Deps, text: str, hint: str) -> None:
    """The v0.3/v0.4 rule-based pipeline, then plain chat."""
    # Imported here: these handler modules import nothing from this one, but keep it lazy
    # so the fallback stays an optional dependency of the agent path.
    from app.bot.handlers import expenses as expense_rules
    from app.bot.handlers import reminders as reminder_rules
    from app.bot.handlers import reports

    message, state, data = deps.message, deps.state, deps
    if hint == texts.AGENT_HINT_REMINDER or has_reminder_trigger(text):
        flow = await reminder_rules._flow(data.config, state, data.llm, data.settings_service)
        await reminder_rules.start(message, flow, text)
        return
    if not hint and (period := parse_report_request(text)):
        kind, offset = reports.PERIODS[period]
        report_text, markup = await reports.render_report(
            kind, offset, data.config, data.expense_service, data.settings_service
        )
        await message.answer(report_text, reply_markup=markup)
        return
    if hint == texts.AGENT_HINT_EXPENSE or has_expense_intent(text):
        flow = await expense_rules._flow(
            data.config, state, data.llm, data.expense_service, data.settings_service
        )
        await expense_rules.start(message, flow, text)
        return
    await stream_chat_reply(deps, text)


async def stream_chat_reply(deps: Deps, question: str) -> None:
    """Plain chat (any model, no tools) with short memory."""
    message = deps.message
    streamer = MessageStreamer(message)
    try:
        async for piece in deps.chat_service.stream_answer(question):
            await streamer.push(piece)
    except LLMError as exc:
        logger.warning("LLM error: {}", exc)
        notice = texts.LLM_ERRORS[exc.kind].format(model=deps.config.effective_llm_model)
        if streamer.started:
            await streamer.finish(f"\n\n{notice}")
        else:
            await message.answer(notice)
        return
    if streamer.text.strip():
        await streamer.finish()
    else:
        await message.answer(texts.LLM_EMPTY)


# --- Messages ---


@router.message(AgentForm.pending, F.text)
async def pending_answer(message: Message, state: FSMContext, **data) -> None:
    deps = await _deps(message, state, data)
    text = message.text or ""
    for choice, pattern in _SCALE_ANSWERS.items():
        if pattern.match(text):
            await resolve_scale(deps, choice, message, edit=False)
            return
    await state.clear()  # something else: drop the pending question
    await free_text(message, state, **data)


@router.message(F.text & ~F.text.startswith("/"))
async def free_text(message: Message, state: FSMContext, **data) -> None:
    deps = await _deps(message, state, data)
    text = (message.text or "").strip()
    hint = ""
    form = await state.get_state()
    stored = await state.get_data()
    if form == AgentForm.hint.state:
        hint = _HINTS.get(stored.get("hint", ""), "")
    elif form == AgentForm.edit.state and (aid := stored.get("edit_action")):
        action = await deps.action_log.get(aid)
        if action is not None:
            hint = texts.AGENT_EDIT_HINT.format(summary=action.summary)
    if form:
        await state.clear()

    if not hint:
        builtin = answer_builtin(text, now_local(deps.config.timezone), deps.calendar)
        if builtin is not None:
            await message.answer(builtin)
            return
    await run_agent(deps, text, hint)


# --- Buttons on result cards ---


@router.callback_query(ActCb.filter(F.action == "undo"))
async def undo(query: CallbackQuery, callback_data: ActCb, action_log: ActionLog) -> None:
    action = await action_log.undo(callback_data.aid)
    if action is None:
        await query.answer(texts.AGENT_ALREADY_UNDONE, show_alert=True)
        return
    if isinstance(query.message, Message):
        await query.message.edit_text((query.message.html_text or "") + texts.AGENT_UNDONE_LINE)
    await query.answer("↩️")


@router.callback_query(ActCb.filter(F.action == "edit"))
async def edit(query: CallbackQuery, callback_data: ActCb, state: FSMContext) -> None:
    await state.set_state(AgentForm.edit)
    await state.set_data({"edit_action": callback_data.aid})
    if isinstance(query.message, Message):
        await query.message.answer(texts.AGENT_EDIT_PROMPT)
    await query.answer()


@router.callback_query(ActCb.filter(F.action == "alert"))
async def toggle_alert(
    query: CallbackQuery, callback_data: ActCb, state: FSMContext, **data
) -> None:
    if not isinstance(query.message, Message):
        return
    deps = await _deps(query.message, state, data)
    action = await deps.action_log.get(callback_data.aid)
    reminder_id = deps.action_log.payload(action).get("id") if action else None
    reminder = await deps.reminder_service.get(reminder_id) if reminder_id else None
    if reminder is None:
        await query.answer(texts.REMINDER_NOT_FOUND, show_alert=True)
        return
    event = from_utc(reminder.event_at, deps.config.timezone)
    clock = None if reminder.all_day else f"{event:%H:%M}"
    options = alert_options(reminder.all_day, clock, deps.config.day_times)
    index = int(callback_data.value or 0)
    if index < len(options):
        spec = options[index][0]
        specs = [s for s in reminder.alert_specs.split(",") if s] or ["at"]
        specs = [s for s in specs if s != spec] if spec in specs else [*specs, spec]
        await deps.reminder_service.set_alert_specs(reminder.id, specs or ["at"])
    rendered = await render_reminder(
        callback_data.aid, reminder.id, deps.ui(), saved=True, ask_alerts=True
    )
    if rendered:
        await query.message.edit_text(rendered[0], reply_markup=rendered[1])
    await query.answer()


@router.callback_query(ActCb.filter(F.action == "cat"))
async def pick_category(
    query: CallbackQuery, callback_data: ActCb, state: FSMContext, **data
) -> None:
    if not isinstance(query.message, Message):
        return
    deps = await _deps(query.message, state, data)
    action = await deps.action_log.get(callback_data.aid)
    payload = deps.action_log.payload(action) if action else {}
    ids = payload.get("ids") or ([payload["previous"]["id"]] if "previous" in payload else [])
    expenses = await deps.expense_service.by_ids(ids)
    if not expenses:
        await query.answer(texts.REPORT_NOT_FOUND, show_alert=True)
        return
    chosen = int(callback_data.value) if callback_data.value else None
    if chosen is None and len(expenses) > 1:
        items = [(e.id, f"{e.category.emoji} {e.description}") for e in expenses]
        await query.message.edit_reply_markup(
            reply_markup=saved_expense_items(callback_data.aid, items)
        )
        await query.answer()
        return
    target = chosen or expenses[0].id
    categories = [(c.id, f"{c.emoji} {c.name}") for c in await deps.expense_service.categories()]
    await query.message.edit_reply_markup(
        reply_markup=saved_expense_categories(callback_data.aid, target, categories)
    )
    await query.answer()


@router.callback_query(ActCb.filter(F.action == "setcat"))
async def set_category(
    query: CallbackQuery, callback_data: ActCb, state: FSMContext, **data
) -> None:
    if not isinstance(query.message, Message):
        return
    deps = await _deps(query.message, state, data)
    expense_id, category_id = (int(part) for part in callback_data.value.split("."))
    changed = await deps.expense_service.update(expense_id, category_id=category_id)
    if changed is None:
        await query.answer(texts.REPORT_NOT_FOUND, show_alert=True)
        return
    expense, _ = changed
    await deps.expense_service.learn(expense.description, category_id)  # remembered next time
    action = await deps.action_log.get(callback_data.aid)
    payload = deps.action_log.payload(action) if action else {}
    ids = payload.get("ids") or [expense.id]
    rendered = await render_saved_expenses(callback_data.aid, ids, deps.ui())
    if rendered:
        await query.message.edit_text(rendered[0], reply_markup=rendered[1])
    await query.answer()


@router.callback_query(ActCb.filter(F.action == "scale"))
async def pick_scale(query: CallbackQuery, callback_data: ActCb, state: FSMContext, **data) -> None:
    if not isinstance(query.message, Message):
        return
    deps = await _deps(query.message, state, data)
    await resolve_scale(deps, callback_data.value, query.message, edit=True)
    await query.answer()
