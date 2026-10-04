"""✅ To-dos: today's list (unfinished tasks of earlier days included), tick with a tap, other
days with ◀️ ▶️, and ➕ Add (the next message goes to the agent as tasks).

Adding, ticking or moving tasks by talking («فردا باید نون بخرم», «نون رو خریدم») is done by
the agent (`app/agent/tools/todos.py`).
"""

from datetime import date

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app import texts
from app.bot import views
from app.bot.keyboards.inline import TodoCb, todo_list
from app.bot.states import AgentForm
from app.config import Settings
from app.services.settings import SettingsService
from app.services.todos import TodoService
from app.utils.calendar import format_date, now_local

router = Router(name="todos")


async def render_todos(
    day: date, config: Settings, todo_service: TodoService, settings_service: SettingsService
) -> tuple[str, InlineKeyboardMarkup]:
    calendar = await settings_service.get_calendar()
    today = now_local(config.timezone).date()
    day_list = await todo_service.day_list(day, today)
    items = [(t.id, t.text, t.done) for t in day_list.items]
    return views.todo_list(day_list, calendar), todo_list(day, today, items)


async def _edit(message: Message, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


@router.message(F.text == texts.BTN_TODOS)
async def show_todos(
    message: Message, config: Settings, todo_service: TodoService,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    today = now_local(config.timezone).date()
    text, markup = await render_todos(today, config, todo_service, settings_service)
    await message.answer(text, reply_markup=markup)


@router.callback_query(TodoCb.filter(F.action == "toggle"))
async def toggle(
    query: CallbackQuery, callback_data: TodoCb, config: Settings, todo_service: TodoService,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    todo = await todo_service.toggle(callback_data.tid)
    if todo is None:
        await query.answer(texts.TODO_NOT_FOUND, show_alert=True)
        return
    day = date.fromisoformat(callback_data.day)
    text, markup = await render_todos(day, config, todo_service, settings_service)
    if isinstance(query.message, Message):
        await _edit(query.message, text, markup)
    await query.answer("☑" if todo.done else "☐")


@router.callback_query(TodoCb.filter(F.action == "day"))
async def other_day(
    query: CallbackQuery, callback_data: TodoCb, config: Settings, todo_service: TodoService,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    day = date.fromisoformat(callback_data.day)
    text, markup = await render_todos(day, config, todo_service, settings_service)
    if isinstance(query.message, Message):
        await _edit(query.message, text, markup)
    await query.answer()


@router.callback_query(TodoCb.filter(F.action == "add"))
async def ask_tasks(
    query: CallbackQuery, callback_data: TodoCb, state: FSMContext,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    await state.set_state(AgentForm.hint)
    await state.set_data({"hint": "todo", "day": callback_data.day})
    calendar = await settings_service.get_calendar()
    day = format_date(date.fromisoformat(callback_data.day), calendar)
    if isinstance(query.message, Message):
        await query.message.answer(texts.TODOS_ADD_PROMPT.format(day=day))
    await query.answer()
