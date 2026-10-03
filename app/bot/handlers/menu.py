"""Menu buttons and commands whose features land in later versions.

Entries are removed from `PLANNED` / `PLANNED_COMMANDS` as each feature is implemented.
"""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app import texts

router = Router(name="menu")

# button label -> (feature name, target version)
PLANNED: dict[str, tuple[str, str]] = {
    texts.BTN_EXPORT: ("Excel export", "v0.5"),
    texts.BTN_TODOS: ("To-dos", "v0.7"),
    texts.BTN_NOTES: ("Notes", "v0.7"),
}

PLANNED_COMMANDS: dict[str, tuple[str, str]] = {
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
