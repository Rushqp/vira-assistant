"""📊 Reports: today / week / month (selected calendar), navigation, and deleting expenses.

Free-text requests («گزارش این ماه») are understood by the agent (`get_report` tool) or, when no
model is available, by the rule-based fallback; both render with `render_report`.
"""

import html

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app import texts
from app.bot import views
from app.bot.keyboards.inline import RepCb, report_delete_confirm, report_nav
from app.config import Settings
from app.core.parsers.expense_rules import Period
from app.services.expenses import ExpenseService
from app.services.reports import Kind, ReportService
from app.services.settings import SettingsService
from app.utils.calendar import now_local
from app.utils.formatting import format_money

router = Router(name="reports")

# Text requests («گزارش ماه قبل», "report this week") → (kind, offset)
PERIODS: dict[Period, tuple[Kind, int]] = {
    "today": ("day", 0),
    "yesterday": ("day", 1),
    "week": ("week", 0),
    "last_week": ("week", 1),
    "month": ("month", 0),
    "last_month": ("month", 1),
}


async def render_report(
    kind: Kind,
    offset: int,
    config: Settings,
    expense_service: ExpenseService,
    settings_service: SettingsService,
):
    calendar = await settings_service.get_calendar()
    today = now_local(config.timezone).date()
    report = await ReportService(expense_service).build(kind, today, calendar, offset)
    text = views.report(report, texts.CURRENCY_LABELS[config.currency.value], calendar)
    ids = [e.id for e in report.expenses[: views.REPORT_MAX_ITEMS]] if kind == "day" else []
    return text, report_nav(kind, offset, ids)


@router.message(F.text.in_({texts.BTN_TODAY_REPORT, texts.BTN_MONTH_REPORT}))
async def report_button(
    message: Message, config: Settings, expense_service: ExpenseService,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    kind: Kind = "day" if message.text == texts.BTN_TODAY_REPORT else "month"
    text, markup = await render_report(kind, 0, config, expense_service, settings_service)
    await message.answer(text, reply_markup=markup)


@router.callback_query(RepCb.filter(F.action == "show"))
async def show(
    query: CallbackQuery, callback_data: RepCb, config: Settings,
    expense_service: ExpenseService, settings_service: SettingsService,
) -> None:  # fmt: skip
    text, markup = await render_report(
        callback_data.kind,  # type: ignore[arg-type]
        max(callback_data.offset, 0),
        config,
        expense_service,
        settings_service,
    )
    if isinstance(query.message, Message):
        await query.message.edit_text(text, reply_markup=markup)
    await query.answer()


@router.callback_query(RepCb.filter(F.action == "delete"))
async def ask_delete(
    query: CallbackQuery, callback_data: RepCb, config: Settings, expense_service: ExpenseService
) -> None:
    expense = await expense_service.get(callback_data.eid)
    if expense is None or not isinstance(query.message, Message):
        await query.answer(texts.REPORT_NOT_FOUND, show_alert=True)
        return
    await query.message.edit_text(
        texts.REPORT_DELETE_CONFIRM.format(
            description=html.escape(expense.description or texts.EXPENSE_NO_DESCRIPTION),
            amount=format_money(expense.amount, texts.CURRENCY_LABELS[config.currency.value]),
        ),
        reply_markup=report_delete_confirm(expense.id, callback_data.kind, callback_data.offset),
    )
    await query.answer()


@router.callback_query(RepCb.filter(F.action == "confirm_delete"))
async def confirm_delete(
    query: CallbackQuery, callback_data: RepCb, config: Settings,
    expense_service: ExpenseService, settings_service: SettingsService,
) -> None:  # fmt: skip
    await expense_service.delete([callback_data.eid])
    text, markup = await render_report(
        callback_data.kind,  # type: ignore[arg-type]
        callback_data.offset,
        config,
        expense_service,
        settings_service,
    )
    if isinstance(query.message, Message):
        await query.message.edit_text(text, reply_markup=markup)
    await query.answer(texts.REPORT_DELETED)
