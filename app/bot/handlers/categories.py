"""⚙️ Settings → 🏷 Categories: list, add and delete expense categories."""

import html
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app import texts
from app.bot.keyboards.inline import CatCb, categories_list, category_delete_confirm
from app.bot.states import CategoryForm
from app.services.expenses import OTHER, ExpenseService

router = Router(name="categories")

# Optional leading emoji (anything that is not a letter or digit), then the name.
_NEW_CATEGORY = re.compile(r"^\s*(?P<emoji>[^\w\s]{1,8})?\s*(?P<name>\w[\w\s&'-]{0,31})\s*$")


async def _list(expense_service: ExpenseService):
    items = [(c.id, f"{c.emoji} {c.name}") for c in await expense_service.categories()]
    return texts.CATEGORIES_TITLE, categories_list(items)


@router.callback_query(CatCb.filter(F.action == "list"))
async def show_categories(
    query: CallbackQuery, state: FSMContext, expense_service: ExpenseService
) -> None:
    await state.clear()
    text, markup = await _list(expense_service)
    if isinstance(query.message, Message):
        await query.message.answer(text, reply_markup=markup)
    await query.answer()


@router.callback_query(CatCb.filter(F.action == "add"))
async def ask_new_category(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CategoryForm.name)
    if isinstance(query.message, Message):
        await query.message.edit_text(texts.CATEGORY_ASK_NEW)
    await query.answer()


@router.message(CategoryForm.name, F.text)
async def add_category(
    message: Message, state: FSMContext, expense_service: ExpenseService
) -> None:
    match = _NEW_CATEGORY.match(message.text or "")
    if not match:
        await message.answer(texts.CATEGORY_INVALID)
        return
    emoji = match["emoji"] or "📦"
    name = " ".join(match["name"].split())
    await state.clear()
    created = await expense_service.add_category(name, emoji)
    if created is None:
        await message.answer(texts.CATEGORY_EXISTS.format(name=html.escape(name)))
    else:
        await message.answer(
            texts.CATEGORY_ADDED.format(emoji=created.emoji, name=html.escape(created.name))
        )
    text, markup = await _list(expense_service)
    await message.answer(text, reply_markup=markup)


@router.callback_query(CatCb.filter(F.action == "delete"))
async def ask_delete(
    query: CallbackQuery, callback_data: CatCb, expense_service: ExpenseService
) -> None:
    category = await expense_service.category(callback_data.cid)
    if category is None or not isinstance(query.message, Message):
        await query.answer()
        return
    if category.name == OTHER:
        await query.answer(texts.CATEGORY_PROTECTED, show_alert=True)
        return
    await query.message.edit_text(
        texts.CATEGORY_DELETE_CONFIRM.format(emoji=category.emoji, name=html.escape(category.name)),
        reply_markup=category_delete_confirm(category.id),
    )
    await query.answer()


@router.callback_query(CatCb.filter(F.action == "confirm_delete"))
async def delete_category(
    query: CallbackQuery, callback_data: CatCb, expense_service: ExpenseService
) -> None:
    await expense_service.delete_category(callback_data.cid)
    text, markup = await _list(expense_service)
    if isinstance(query.message, Message):
        await query.message.edit_text(text, reply_markup=markup)
    await query.answer(texts.CATEGORY_DELETED)
