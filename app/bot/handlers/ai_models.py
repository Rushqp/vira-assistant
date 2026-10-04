"""🤖 AI model: see which models are ready, and choose the one that answers first.

Opened from ⚙️ Settings or with /model. "Auto" keeps the configured order (LLM_PROVIDERS);
choosing a model puts it first and keeps the others as backups. The choice is saved, so it
survives restarts (applied in `main.py`).
"""

import asyncio
import html
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app import texts
from app.bot.keyboards.inline import AiCb, SettingsCb, ai_models_menu
from app.config import Settings
from app.llm.models import KEY_NAMES, model_label, model_name
from app.llm.providers import ProviderChain, missing_providers, model_options
from app.services.settings import SettingsService

router = Router(name="ai_models")

LOCAL_LIST_TIMEOUT = 3  # seconds to ask Ollama which models are pulled


async def render(
    llm: object, config: Settings, state: FSMContext
) -> tuple[str, InlineKeyboardMarkup | None]:
    if not isinstance(llm, ProviderChain) or not llm.clients:
        return texts.AI_NONE, None
    try:
        local = await asyncio.wait_for(llm.local_models(), LOCAL_LIST_TIMEOUT)
    except TimeoutError:
        local = []
    options = model_options(config, local)
    await state.update_data(ai_options=[list(option) for option in options])

    lines = [texts.AI_TITLE, ""]
    if llm.preferred:
        lines.append(texts.AI_MODE_PREFERRED.format(model=html.escape(llm.preferred.label)))
    else:
        lines.append(texts.AI_MODE_AUTO)
    if (answering := llm.answering() or llm.answering(need_tools=False)) is not None:
        lines.append(texts.AI_ANSWERING.format(model=html.escape(answering.label)))
    lines += ["", texts.AI_ORDER]
    now = datetime.now(config.timezone)
    for n, status in enumerate(llm.status(), 1):
        label = html.escape(status.client.label)
        if status.ready:
            line = texts.AI_STATUS_READY.format(n=n, model=label)
        else:
            at = now + timedelta(seconds=status.retry_in)
            line = texts.AI_STATUS_PAUSED.format(
                n=n,
                model=label,
                reason=texts.AI_REASONS.get(status.reason, status.reason),
                time=f"{at:%H:%M}",
            )
        if not status.client.supports_tools:
            line += texts.AI_STATUS_CHAT_ONLY
        lines.append(line)
    if missing := missing_providers(config):
        lines += ["", texts.AI_NO_KEY.format(keys=", ".join(KEY_NAMES[p] for p in missing))]
    lines += ["", texts.AI_HELP]

    labels = [
        model_name(p, m) if p != "local" else f"{m.removesuffix(':latest')} (local)"
        for p, m in options
    ]
    selected = options.index(llm.preference) if llm.preference in options else None
    return "\n".join(lines), ai_models_menu(labels, selected)


async def _edit(message: Message, text: str, markup: InlineKeyboardMarkup | None) -> None:
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:  # e.g. ✨ Auto pressed again: nothing changed
        if "message is not modified" not in str(exc):
            raise


@router.message(Command("model"))
async def show_menu(message: Message, state: FSMContext, llm: object, config: Settings) -> None:
    text, markup = await render(llm, config, state)
    await message.answer(text, reply_markup=markup)


@router.callback_query(SettingsCb.filter(F.action == "ai"))
async def from_settings(
    query: CallbackQuery, state: FSMContext, llm: object, config: Settings
) -> None:
    text, markup = await render(llm, config, state)
    if isinstance(query.message, Message):
        await query.message.answer(text, reply_markup=markup)
    await query.answer()


@router.callback_query(AiCb.filter())
async def choose(
    query: CallbackQuery,
    callback_data: AiCb,
    state: FSMContext,
    llm: object,
    config: Settings,
    settings_service: SettingsService,
) -> None:
    if not isinstance(llm, ProviderChain) or not isinstance(query.message, Message):
        await query.answer()
        return
    if callback_data.action == "auto":
        llm.prefer(None)
        await settings_service.set_ai_model(None)
        toast = texts.AI_AUTO_CHOSEN
    else:
        options = (await state.get_data()).get("ai_options") or []
        if callback_data.index >= len(options):
            text, markup = await render(llm, config, state)
            await _edit(query.message, text, markup)
            await query.answer(texts.AI_MENU_EXPIRED, show_alert=True)
            return
        provider, model = options[callback_data.index]
        if llm.prefer(provider, model) is None:
            await query.answer(texts.AI_PICK_FAILED, show_alert=True)
            return
        await settings_service.set_ai_model(provider, model)
        toast = texts.AI_CHOSEN.format(model=model_label(provider, model))
    text, markup = await render(llm, config, state)
    await _edit(query.message, text, markup)
    await query.answer(toast)
