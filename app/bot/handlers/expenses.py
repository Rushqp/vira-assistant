"""💰 Expenses: record one or several from free text or the form, with confirmation and undo.

The conversation is driven by `ExpenseDraft.next_step()`:
missing amount? → thousand or million? → category (keywords → learned → LLM) → confirm.
The draft is kept in the FSM data under "expense".
"""

import html
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.chat_action import ChatActionSender

from app import texts
from app.bot import views
from app.bot.keyboards.inline import (
    ExpCb,
    category_grid,
    expense_confirm,
    expense_items,
    expense_saved,
    expense_scale,
)
from app.bot.states import ExpenseForm
from app.config import Calendar, Settings
from app.core.normalizer import normalize
from app.core.parsers.amount_parser import find_amounts
from app.core.parsers.expense_rules import has_expense_intent, parse_expenses
from app.llm.client import LLMClient
from app.services import expense_ai
from app.services.expenses import DraftItem, ExpenseDraft, ExpenseService
from app.services.settings import SettingsService
from app.utils.calendar import now_local
from app.utils.formatting import format_money

router = Router(name="expenses")


@dataclass
class Flow:
    config: Settings
    state: FSMContext
    llm: LLMClient
    service: ExpenseService
    calendar: Calendar

    @property
    def currency(self) -> str:
        return self.config.currency.value

    @property
    def label(self) -> str:
        return texts.CURRENCY_LABELS[self.currency]


async def _flow(config, state, llm, expense_service, settings_service: SettingsService) -> Flow:
    return Flow(config, state, llm, expense_service, await settings_service.get_calendar())


async def _load(state: FSMContext) -> ExpenseDraft | None:
    data = await state.get_data()
    return ExpenseDraft.from_dict(data["expense"]) if data.get("expense") else None


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


async def _card(flow: Flow, draft: ExpenseDraft) -> str:
    categories = {c.id: c for c in await flow.service.categories()}
    today = now_local(flow.config.timezone).date()
    return views.expense_card(draft, categories, flow.label, flow.calendar, today)


async def _categorize(target: Message, flow: Flow, draft: ExpenseDraft) -> None:
    """Fill in missing categories: keywords / learned first, then one LLM call, then Other."""
    unknown: list[DraftItem] = []
    for item in draft.items:
        if item.category_id is None:
            found = await flow.service.classify(item.description)
            if found:
                item.category_id = found.id
            else:
                unknown.append(item)
    if not unknown:
        return
    categories = await flow.service.categories()
    by_name = {c.name: c for c in categories}
    async with ChatActionSender.typing(chat_id=target.chat.id, bot=target.bot):
        names = await expense_ai.categorize(
            flow.llm, [i.description for i in unknown], list(by_name)
        )
    other = await flow.service.other()
    for item, name in zip(unknown, names or [None] * len(unknown), strict=True):
        item.category_id = by_name[name].id if name in by_name else other.id


async def advance(target: Message, flow: Flow, draft: ExpenseDraft, edit: bool = False) -> None:
    """Ask the next missing piece, or show the confirmation card."""
    step = draft.next_step()
    if step and step[0] == "category":
        await _categorize(target, flow, draft)
        step = draft.next_step()
    await flow.state.update_data(expense=draft.to_dict())

    if step is None:
        await flow.state.set_state(ExpenseForm.buttons)
        await _show(target, await _card(flow, draft), expense_confirm(), edit)
        return
    kind, index = step
    item = draft.items[index]
    description = html.escape(item.description or texts.EXPENSE_NO_DESCRIPTION)
    await flow.state.update_data(index=index)
    if kind == "amount":
        await flow.state.set_state(ExpenseForm.amount)
        await _show(target, texts.EXPENSE_ASK_AMOUNT.format(description=description), edit=edit)
    else:  # ambiguous
        thousand, million = item.choices(flow.config.currency)  # type: ignore[arg-type]
        await flow.state.set_state(ExpenseForm.buttons)
        raw = f"{item.raw_amount:g}"
        await _show(
            target,
            texts.EXPENSE_ASK_SCALE.format(description=description, raw=raw),
            expense_scale(format_money(thousand, flow.label), format_money(million, flow.label)),
            edit,
        )


async def start(message: Message, flow: Flow, text: str) -> None:
    today = now_local(flow.config.timezone).date()
    parse = parse_expenses(text, today)
    draft = ExpenseDraft.from_parse(parse, text, flow.config.currency)  # type: ignore[arg-type]
    if not any(i.amount is not None or i.raw_amount is not None for i in draft.items):
        # The rules found no amount: ask the LLM before asking the user.
        async with ChatActionSender.typing(chat_id=message.chat.id, bot=message.bot):
            found = await expense_ai.extract(flow.llm, text)
        if not found:
            await flow.state.set_state(ExpenseForm.describe)
            await message.answer(texts.EXPENSE_RETRY)
            return
        draft.items = []
        for description, amount in found:
            item = DraftItem(description=description)
            item.set_amount(amount, amount < 1000, None, flow.config.currency)  # type: ignore[arg-type]
            draft.items.append(item)
    await advance(message, flow, draft)


# --- Entry points ---


@router.message(F.text == texts.BTN_ADD_EXPENSE)
async def add_expense(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ExpenseForm.describe)
    await message.answer(texts.EXPENSE_ASK_DESCRIBE)


@router.message(ExpenseForm.describe, F.text)
async def describe(
    message: Message, state: FSMContext, config: Settings, llm: LLMClient,
    expense_service: ExpenseService, settings_service: SettingsService,
) -> None:  # fmt: skip
    await state.set_data({})
    flow = await _flow(config, state, llm, expense_service, settings_service)
    await start(message, flow, message.text or "")


@router.message(ExpenseForm.amount, F.text)
async def got_amount(
    message: Message, state: FSMContext, config: Settings, llm: LLMClient,
    expense_service: ExpenseService, settings_service: SettingsService,
) -> None:  # fmt: skip
    draft = await _load(state)
    if draft is None:
        await state.clear()
        await message.answer(texts.EXPENSE_EXPIRED)
        return
    index = (await state.get_data()).get("index", 0)
    item = draft.items[index]
    amounts = find_amounts(normalize(message.text or "", lowercase=False))
    if not amounts:
        await message.answer(
            texts.EXPENSE_AMOUNT_RETRY.format(description=html.escape(item.description))
        )
        return
    found = amounts[0]
    item.set_amount(found.value, found.ambiguous, found.currency, config.currency)
    flow = await _flow(config, state, llm, expense_service, settings_service)
    await advance(message, flow, draft)


@router.message(F.text.func(has_expense_intent), ~F.text.startswith("/"))
async def expense_from_text(
    message: Message, state: FSMContext, config: Settings, llm: LLMClient,
    expense_service: ExpenseService, settings_service: SettingsService,
) -> None:  # fmt: skip
    await state.clear()
    flow = await _flow(config, state, llm, expense_service, settings_service)
    await start(message, flow, message.text or "")


# --- Buttons ---


async def _query_flow(
    query: CallbackQuery, state, config, llm, expense_service, settings_service
) -> tuple[Message, Flow, ExpenseDraft] | None:
    draft = await _load(state)
    if draft is None or not isinstance(query.message, Message):
        await query.answer(texts.EXPENSE_EXPIRED, show_alert=True)
        return None
    flow = await _flow(config, state, llm, expense_service, settings_service)
    return query.message, flow, draft


@router.callback_query(ExpCb.filter(F.action == "scale"))
async def pick_scale(
    query: CallbackQuery, callback_data: ExpCb, state: FSMContext, config: Settings,
    llm: LLMClient, expense_service: ExpenseService, settings_service: SettingsService,
) -> None:  # fmt: skip
    loaded = await _query_flow(query, state, config, llm, expense_service, settings_service)
    if loaded is None:
        return
    message, flow, draft = loaded
    index = (await state.get_data()).get("index", 0)
    item = draft.items[index]
    if item.ambiguous:
        thousand, million = item.choices(config.currency)  # type: ignore[arg-type]
        item.amount = thousand if callback_data.value == "k" else million
        item.raw_amount = item.raw_currency = None
    await query.answer()
    await advance(message, flow, draft, edit=True)


@router.callback_query(ExpCb.filter(F.action.in_({"category", "back"})))
async def open_category_picker(
    query: CallbackQuery, callback_data: ExpCb, state: FSMContext, config: Settings,
    llm: LLMClient, expense_service: ExpenseService, settings_service: SettingsService,
) -> None:  # fmt: skip
    loaded = await _query_flow(query, state, config, llm, expense_service, settings_service)
    if loaded is None:
        return
    message, flow, draft = loaded
    await query.answer()
    if callback_data.action == "back":
        await advance(message, flow, draft, edit=True)
    elif len(draft.items) == 1:
        await _show_categories(message, flow, draft, 0)
    else:
        descriptions = [i.description or texts.EXPENSE_NO_DESCRIPTION for i in draft.items]
        await message.edit_text(texts.EXPENSE_PICK_ITEM, reply_markup=expense_items(descriptions))


async def _show_categories(message: Message, flow: Flow, draft: ExpenseDraft, index: int) -> None:
    choices = [(c.id, f"{c.emoji} {c.name}") for c in await flow.service.categories()]
    description = html.escape(draft.items[index].description or texts.EXPENSE_NO_DESCRIPTION)
    await message.edit_text(
        texts.EXPENSE_PICK_CATEGORY.format(description=description),
        reply_markup=category_grid(choices, index),
    )


@router.callback_query(ExpCb.filter(F.action == "pick"))
async def pick_item(
    query: CallbackQuery, callback_data: ExpCb, state: FSMContext, config: Settings,
    llm: LLMClient, expense_service: ExpenseService, settings_service: SettingsService,
) -> None:  # fmt: skip
    loaded = await _query_flow(query, state, config, llm, expense_service, settings_service)
    if loaded is None:
        return
    message, flow, draft = loaded
    await query.answer()
    if callback_data.index < len(draft.items):
        await _show_categories(message, flow, draft, callback_data.index)


@router.callback_query(ExpCb.filter(F.action == "setcat"))
async def set_category(
    query: CallbackQuery, callback_data: ExpCb, state: FSMContext, config: Settings,
    llm: LLMClient, expense_service: ExpenseService, settings_service: SettingsService,
) -> None:  # fmt: skip
    loaded = await _query_flow(query, state, config, llm, expense_service, settings_service)
    if loaded is None:
        return
    message, flow, draft = loaded
    if callback_data.index < len(draft.items):
        item = draft.items[callback_data.index]
        item.category_id = int(callback_data.value)
        await expense_service.learn(item.description, item.category_id)  # remember for next time
    await query.answer()
    await advance(message, flow, draft, edit=True)


@router.callback_query(ExpCb.filter(F.action == "save"))
async def save(
    query: CallbackQuery, state: FSMContext, config: Settings, llm: LLMClient,
    expense_service: ExpenseService, settings_service: SettingsService,
) -> None:  # fmt: skip
    loaded = await _query_flow(query, state, config, llm, expense_service, settings_service)
    if loaded is None:
        return
    message, flow, draft = loaded
    card = await _card(flow, draft)
    saved = await expense_service.add(draft, now_local(config.timezone))
    await state.clear()
    await state.update_data(last_saved=[e.id for e in saved])  # for ↩️ Undo
    await message.edit_text(texts.EXPENSE_SAVED.format(card=card), reply_markup=expense_saved())
    await query.answer()


@router.callback_query(ExpCb.filter(F.action == "undo"))
async def undo(query: CallbackQuery, state: FSMContext, expense_service: ExpenseService) -> None:
    ids = (await state.get_data()).get("last_saved")
    if not ids:
        await query.answer(texts.EXPENSE_UNDO_EXPIRED, show_alert=True)
        return
    await expense_service.delete(ids)
    await state.update_data(last_saved=None)
    if isinstance(query.message, Message):
        await query.message.edit_text(texts.EXPENSE_UNDONE)
    await query.answer()


@router.callback_query(ExpCb.filter(F.action == "edit"))
async def edit(query: CallbackQuery, state: FSMContext) -> None:
    draft = await _load(state)
    if draft is None or not isinstance(query.message, Message):
        await query.answer(texts.EXPENSE_EXPIRED, show_alert=True)
        return
    await state.set_state(ExpenseForm.describe)
    await state.set_data({})
    await query.message.edit_text(texts.EXPENSE_EDIT_PROMPT.format(raw=html.escape(draft.raw)))
    await query.answer()


@router.callback_query(ExpCb.filter(F.action == "cancel"))
async def cancel(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(query.message, Message):
        await query.message.edit_text(texts.EXPENSE_CANCELLED)
    await query.answer()
