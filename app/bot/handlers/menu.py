"""Menu buttons and commands whose features land in later versions, plus the free-text fallback.

Entries are removed from `PLANNED` as each feature is implemented.
"""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app import texts
from app.bot.keyboards.reply import main_menu

router = Router(name="menu")

# button label -> (feature name, target version)
PLANNED: dict[str, tuple[str, str]] = {
    texts.BTN_NEW_CHAT: ("Chat", "v0.2"),
    texts.BTN_NEW_REMINDER: ("Reminders", "v0.3"),
    texts.BTN_REMINDERS: ("Reminders", "v0.3"),
    texts.BTN_ADD_EXPENSE: ("Expenses", "v0.4"),
    texts.BTN_TODAY_REPORT: ("Reports", "v0.4"),
    texts.BTN_MONTH_REPORT: ("Reports", "v0.4"),
    texts.BTN_EXPORT: ("Excel export", "v0.5"),
    texts.BTN_TODOS: ("To-dos", "v0.7"),
    texts.BTN_NOTES: ("Notes", "v0.7"),
}

PLANNED_COMMANDS: dict[str, tuple[str, str]] = {
    "new": ("Chat", "v0.2"),
    "backup": ("Backup", "v0.7"),
}


@router.message(F.text.in_(PLANNED))
async def planned_button(message: Message) -> None:
    feature, version = PLANNED[message.text or ""]
    await message.answer(texts.COMING_SOON.format(feature=feature, version=version))


@router.message(Command(*PLANNED_COMMANDS))
async def planned_command(message: Message) -> None:
    command = (message.text or "").split()[0].lstrip("/").split("@")[0]
    feature, version = PLANNED_COMMANDS[command]
    await message.answer(texts.COMING_SOON.format(feature=feature, version=version))


@router.message()
async def fallback(message: Message) -> None:
    await message.answer(texts.FREE_TEXT_NOT_READY, reply_markup=main_menu())
