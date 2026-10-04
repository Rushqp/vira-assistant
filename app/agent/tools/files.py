"""File tools: Excel files of expenses and reminders, and any table as an Excel file.

The file is built here (`app/services/export.py`) and sent by the bot layer as a Telegram
document (`Card("file")`). Ranges are resolved deterministically: the model passes a period, a
month («مهر», "1405-07"), a year or the user's own dates, never computed date ranges.
"""

import re
from datetime import date, datetime, time, timedelta
from typing import Any

import jdatetime
from pydantic import Field, model_validator

from app import texts
from app.agent.tools import Args, Card, Tool, ToolContext, ToolError, ToolOutcome
from app.agent.tools.common import PERIODS, parse_date_arg
from app.config import Calendar
from app.core.normalizer import normalize
from app.core.textmatch import best_match
from app.db.models import Expense
from app.services.export import (
    EXPENSE_COLUMNS,
    FULL_DAYS,
    SUMMARIES,
    ExpenseExport,
    ExportFile,
    ReminderExport,
    TableSheet,
    build_expenses,
    build_reminders,
    build_table,
    range_label,
)
from app.services.reminders import monthly_date
from app.services.reports import period_range
from app.utils.calendar import GREGORIAN_MONTHS, JALALI_MONTHS

EXPENSE_PERIODS = [*PERIODS, "this_year", "last_year", "all"]
REMINDER_PERIODS = [
    "upcoming", "today", "tomorrow", "this_week", "next_week", "this_month", "next_month", "all",
]  # fmt: skip
MAX_SHEETS, MAX_COLUMNS, MAX_ROWS, MAX_CELL = 10, 40, 2000, 2000
MAX_TITLE = 100  # the title is also in the Telegram caption

# Month names in both calendars and languages → (calendar, month number)
_MONTHS: dict[str, tuple[Calendar, int]] = {}
for _names, _cal in (
    (JALALI_MONTHS["en"], Calendar.JALALI),
    (JALALI_MONTHS["fa"], Calendar.JALALI),
    (GREGORIAN_MONTHS["en"], Calendar.GREGORIAN),
    (GREGORIAN_MONTHS["fa"], Calendar.GREGORIAN),
    (texts.GREGORIAN_MONTH_NAMES, Calendar.GREGORIAN),
):
    for _number, _name in enumerate(_names, 1):
        _MONTHS[normalize(_name)] = (_cal, _number)


def file_card(file: ExportFile, caption: dict) -> Card:
    return Card("file", None, {"filename": file.filename, "caption": caption}, file.content)


# --- Ranges ---


def year_range(year: int) -> tuple[date, date, Calendar]:
    """A whole year: Jalali when the year looks Jalali (1300–1699)."""
    if year < 1700:
        start = jdatetime.date(year, 1, 1).togregorian()
        return start, jdatetime.date(year + 1, 1, 1).togregorian(), Calendar.JALALI
    return date(year, 1, 1), date(year + 1, 1, 1), Calendar.GREGORIAN


def month_range(text: str, ctx: ToolContext) -> tuple[date, date, Calendar]:
    """'1405-07', '2026-10', '7' (this year, user's calendar), «مهر», «مهر ۱۴۰۴», 'October'."""
    raw = normalize(text).replace("ماه", " ").strip()
    year: int | None = None
    if match := re.fullmatch(r"(\d{4})\s*[-/.]\s*(\d{1,2})", raw):
        year, month = int(match[1]), int(match[2])
        calendar = Calendar.JALALI if year < 1700 else Calendar.GREGORIAN
    elif match := re.fullmatch(r"(\d{1,2})", raw):
        month, calendar = int(match[1]), ctx.calendar
    else:
        if found := re.search(r"\d{4}", raw):
            year = int(found[0])
        name = re.sub(r"\d{4}", " ", raw).strip()
        if name not in _MONTHS:
            raise ToolError(f"unknown month {text!r}", "e.g. '1405-07', 'مهر', 'October'")
        calendar, month = _MONTHS[name]
    if not 1 <= month <= 12:
        raise ToolError(f"unknown month {text!r}", "months are 1-12")
    if year is None:  # this year, or last year if the month hasn't started yet
        if calendar == Calendar.JALALI:
            year = jdatetime.date.fromgregorian(date=ctx.today).year
        else:
            year = ctx.today.year
        if _month_start(year, month, calendar) > ctx.today:
            year -= 1
    start = _month_start(year, month, calendar)
    return start, monthly_date(1, calendar.value, start, 1), calendar


def _month_start(year: int, month: int, calendar: Calendar) -> date:
    if calendar == Calendar.JALALI:
        return jdatetime.date(year, month, 1).togregorian()
    return date(year, month, 1)


async def expense_range(
    args: "ExportExpensesArgs", ctx: ToolContext
) -> tuple[date, date, Calendar]:
    """[start, end) and the calendar of its label. Dates > month > year > period."""
    tomorrow = ctx.today + timedelta(days=1)
    if args.from_date or args.to_date:
        start = parse_date_arg(args.from_date, ctx.today, prefer_past=True)
        last = parse_date_arg(args.to_date, ctx.today, prefer_past=True)
        if (args.from_date and start is None) or (args.to_date and last is None):
            raise ToolError(
                "could not understand the dates", "use 'YYYY-MM-DD' (Jalali or Gregorian)"
            )
        if start is None:
            start = await ctx.expenses.first_day() or last
        end = last + timedelta(days=1) if last else tomorrow
        if start is None or start >= end:
            raise ToolError("from_date must be before to_date")
        return start, end, ctx.calendar
    if args.month:
        return month_range(args.month, ctx)
    if args.year:
        try:
            return year_range(int(normalize(args.year).strip()))
        except ValueError as exc:
            raise ToolError(f"unknown year {args.year!r}", "e.g. '1405' or '2026'") from exc
    period = args.period or "this_month"
    if period in PERIODS:
        kind, offset = PERIODS[period]
        start, end = period_range(kind, ctx.today, ctx.calendar, offset)
        return start, end, ctx.calendar
    if period in ("this_year", "last_year"):
        if ctx.calendar == Calendar.JALALI:
            current = jdatetime.date.fromgregorian(date=ctx.today).year
        else:
            current = ctx.today.year
        return year_range(current - (period == "last_year"))
    if period == "all":
        return (await ctx.expenses.first_day() or ctx.today), tomorrow, ctx.calendar
    raise ToolError(f"unknown period {period!r}", f"use one of: {', '.join(EXPENSE_PERIODS)}")


# --- export_expenses ---


class ExportExpensesArgs(Args):
    period: str | None = None
    month: str | None = None
    year: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    categories: list[str] = Field(default_factory=list)
    query: str | None = None
    columns: list[str] = Field(default_factory=list)
    summaries: list[str] | None = None
    chart: bool = True
    title: str | None = None


async def _filter_expenses(items: list[Expense], args: ExportExpensesArgs, ctx: ToolContext):
    if args.categories:
        wanted = set()
        for name in args.categories:
            category = await ctx.expenses.category_by_name(name)
            if category is None:
                names = ", ".join(c.name for c in await ctx.expenses.categories())
                raise ToolError(f"unknown category {name!r}", f"categories: {names}")
            wanted.add(category.id)
        items = [e for e in items if e.category_id in wanted]
    if args.query:
        _, matches = best_match(items, args.query, key=lambda e: e.description or "")
        keep = {e.id for e in matches}
        items = [e for e in items if e.id in keep]
    return items


async def export_expenses(args: ExportExpensesArgs, ctx: ToolContext) -> ToolOutcome:
    start, end, label_calendar = await expense_range(args, ctx)
    unknown = [c for c in args.columns if c not in EXPENSE_COLUMNS]
    unknown += [s for s in args.summaries or [] if s not in SUMMARIES]
    if unknown:
        raise ToolError(
            f"unknown columns / summaries: {', '.join(unknown)}",
            f"columns: {', '.join(EXPENSE_COLUMNS)}; summaries: {', '.join(SUMMARIES)}",
        )
    items = await _filter_expenses(await ctx.expenses.between(start, end), args, ctx)
    last = end - timedelta(days=1)
    span = {"from": start.isoformat(), "to": last.isoformat()}
    if not items:
        return ToolOutcome(
            result={
                "count": 0,
                "range": span,
                "file": None,
                "hint": "no expenses match, so no file was sent: tell the user",
            }
        )
    summaries = args.summaries
    if summaries is None:  # long ranges: months instead of days
        summaries = ["category", "day" if (end - start).days <= FULL_DAYS else "month"]
    label, _ = range_label(start, end, label_calendar)
    title = (args.title or "").strip()[:MAX_TITLE] or f"{texts.XLSX_EXPENSES_TITLE} · {label}"
    file = build_expenses(
        ExpenseExport(
            expenses=items,
            start=start,
            end=end,
            today=ctx.today,
            calendar=ctx.calendar,
            tz=ctx.config.timezone,
            currency=texts.CURRENCY_LABELS[ctx.currency],
            columns=args.columns or list(EXPENSE_COLUMNS),
            summaries=summaries,
            chart=args.chart,
            title=title,
            label_calendar=label_calendar,
        )
    )
    total = sum(e.amount for e in items)
    return ToolOutcome(
        result={
            "sent_file": file.filename,
            "title": title,
            "count": len(items),
            "total": total,
            "range": span,
            "sheets": ["expenses", *summaries],
            "shown_to_user": True,
        },
        card=file_card(
            file, {"kind": "expenses", "title": title, "count": len(items), "total": total}
        ),
        note=f"[done: sent Excel file {file.filename} — {title}, {len(items)} expenses]",
    )


# --- export_reminders ---


class ExportRemindersArgs(Args):
    period: str = "upcoming"
    from_date: str | None = None
    to_date: str | None = None
    query: str | None = None
    important_only: bool = False
    include_done: bool = False
    title: str | None = None


def _local(day: date, ctx: ToolContext) -> datetime:
    return datetime.combine(day, time(0), ctx.config.timezone)


def reminder_range(
    args: ExportRemindersArgs, ctx: ToolContext
) -> tuple[datetime | None, datetime | None, str, str]:
    """(start, end, title label, file-name part)."""
    if args.from_date or args.to_date:
        first = parse_date_arg(args.from_date, ctx.today) if args.from_date else ctx.today
        last = parse_date_arg(args.to_date, ctx.today) if args.to_date else None
        if first is None or (args.to_date and last is None):
            raise ToolError(
                "could not understand the dates", "use 'YYYY-MM-DD' (Jalali or Gregorian)"
            )
        if last is None:  # from a day on
            day, slug = range_label(first, first + timedelta(days=1), ctx.calendar)
            return _local(first, ctx), None, texts.XLSX_FROM.format(date=day), f"from-{slug}"
        if first > last:
            raise ToolError("from_date must be before to_date")
        end = last + timedelta(days=1)
        label, slug = range_label(first, end, ctx.calendar)
        return _local(first, ctx), _local(end, ctx), label, slug
    match args.period:
        case "upcoming":
            return ctx.now, None, texts.XLSX_UPCOMING, "upcoming"
        case "all":
            return None, None, texts.XLSX_ALL, "all"
        case "today" | "tomorrow":
            day = ctx.today + timedelta(days=args.period == "tomorrow")
            first, end = day, day + timedelta(days=1)
        case "this_week" | "next_week":
            first, end = period_range(
                "week", ctx.today, ctx.calendar, -(args.period == "next_week")
            )
        case "this_month" | "next_month":
            offset = -(args.period == "next_month")
            first, end = period_range("month", ctx.today, ctx.calendar, offset)
        case _:
            raise ToolError(
                f"unknown period {args.period!r}", f"use one of: {', '.join(REMINDER_PERIODS)}"
            )
    label, slug = range_label(first, end, ctx.calendar)
    return _local(first, ctx), _local(end, ctx), label, slug


async def export_reminders(args: ExportRemindersArgs, ctx: ToolContext) -> ToolOutcome:
    start, end, label, slug = reminder_range(args, ctx)
    statuses = ("active", "done") if args.include_done else ("active",)
    items = await ctx.reminders.listing(start, end, statuses)
    if args.important_only:
        items = [r for r in items if r.important]
    if args.query:
        _, matches = best_match(items, args.query, key=lambda r: r.text)
        keep = {r.id for r in matches}
        items = [r for r in items if r.id in keep]
    if not items:
        return ToolOutcome(
            result={"count": 0, "file": None, "hint": "no reminders match: tell the user"}
        )
    title = (args.title or "").strip()[:MAX_TITLE] or f"{texts.XLSX_REMINDERS_TITLE} · {label}"
    file = build_reminders(
        ReminderExport(items, ctx.calendar, ctx.config.timezone, label, slug, title)
    )
    return ToolOutcome(
        result={
            "sent_file": file.filename,
            "title": title,
            "count": len(items),
            "shown_to_user": True,
        },
        card=file_card(file, {"kind": "reminders", "title": title, "count": len(items)}),
        note=f"[done: sent Excel file {file.filename} — {title}, {len(items)} reminders]",
    )


# --- make_spreadsheet ---


class SheetArgs(Args):
    name: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    totals: bool = False

    @model_validator(mode="before")
    @classmethod
    def rows_as_lists(cls, data: Any) -> Any:
        """Rows given as objects ({"Day": "Sat", …}) become lists in column order."""
        if not isinstance(data, dict) or not any(
            isinstance(r, dict) for r in data.get("rows") or []
        ):
            return data
        columns = list(data.get("columns") or [])
        for row in data["rows"]:
            if isinstance(row, dict):
                columns += [str(k) for k in row if str(k) not in columns]
        rows = [
            [row.get(c, "") for c in columns] if isinstance(row, dict) else row
            for row in data["rows"]
        ]
        return {**data, "columns": columns, "rows": rows}


class MakeSpreadsheetArgs(Args):
    title: str
    sheets: list[SheetArgs] = Field(default_factory=list)


def _check_table(args: MakeSpreadsheetArgs) -> None:
    if not args.sheets:
        raise ToolError("no sheets", "give at least one sheet with columns and rows")
    if len(args.sheets) > MAX_SHEETS:
        raise ToolError(f"too many sheets (max {MAX_SHEETS})")
    for sheet in args.sheets:
        if not sheet.columns and not sheet.rows:
            raise ToolError(f"sheet {sheet.name!r} is empty", "fill columns and rows")
        if len(sheet.rows) > MAX_ROWS:
            raise ToolError(f"too many rows in {sheet.name!r} (max {MAX_ROWS})")
        widest = max([len(sheet.columns), *(len(row) for row in sheet.rows)])
        if widest > MAX_COLUMNS:
            raise ToolError(f"too many columns in {sheet.name!r} (max {MAX_COLUMNS})")
        for row in sheet.rows:
            for value in row:
                if isinstance(value, dict | list):
                    raise ToolError("cells must be plain text or numbers")


def _cell(value: Any) -> Any:
    return value[:MAX_CELL] if isinstance(value, str) else value


async def make_spreadsheet(args: MakeSpreadsheetArgs, ctx: ToolContext) -> ToolOutcome:
    _check_table(args)
    title = args.title.strip()[:MAX_TITLE] or texts.XLSX_SHEET_DEFAULT
    sheets = [
        TableSheet(
            name=sheet.name or f"{texts.XLSX_SHEET_DEFAULT} {n}",
            columns=[str(c)[:MAX_CELL] for c in sheet.columns],
            rows=[[_cell(v) for v in row] for row in sheet.rows],
            totals=sheet.totals,
        )
        for n, sheet in enumerate(args.sheets, 1)
    ]
    file = build_table(title, sheets)
    return ToolOutcome(
        result={
            "sent_file": file.filename,
            "sheets": [{"name": s.name, "rows": len(s.rows)} for s in sheets],
            "shown_to_user": True,
        },
        card=file_card(file, {"kind": "table", "title": title}),
        note=f"[done: sent Excel file {file.filename} — {title}]",
    )


# --- Schemas ---

_DATE = "'YYYY-MM-DD' (Jalali or Gregorian) or the user's words"

FILE_TOOLS = [
    Tool(
        name="export_expenses",
        description=(
            "Send the user an Excel file of their expenses: every expense plus summary sheets "
            "with totals and charts. Default: this month."
        ),
        parameters={
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": EXPENSE_PERIODS},
                "month": {
                    "type": "string",
                    "description": "a whole month: 'مهر', 'October', '1405-07', '2026-10'",
                },
                "year": {"type": "string", "description": "a whole year: '1405' or '2026'"},
                "from_date": {"type": "string", "description": _DATE},
                "to_date": {"type": "string", "description": "last day (inclusive), same format"},
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "only these categories",
                },
                "query": {"type": "string", "description": "description filter, e.g. 'بنزین'"},
                "columns": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(EXPENSE_COLUMNS)},
                    "description": "default: all",
                },
                "summaries": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(SUMMARIES)},
                    "description": "default: category + day (month for long ranges); [] = none",
                },
                "chart": {"type": "boolean", "description": "default true"},
                "title": {"type": "string"},
            },
        },
        args_model=ExportExpensesArgs,
        handler=export_expenses,
    ),
    Tool(
        name="export_reminders",
        description="Send the user an Excel file of their reminders. Default: upcoming.",
        parameters={
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": REMINDER_PERIODS},
                "from_date": {"type": "string", "description": _DATE},
                "to_date": {"type": "string", "description": "last day (inclusive), same format"},
                "query": {"type": "string", "description": "only reminders matching this text"},
                "important_only": {"type": "boolean"},
                "include_done": {"type": "boolean", "description": "also reminders marked done"},
                "title": {"type": "string"},
            },
        },
        args_model=ExportRemindersArgs,
        handler=export_reminders,
    ),
    Tool(
        name="make_spreadsheet",
        description=(
            "Send any table as an Excel file (.xlsx): plans, schedules, lists, comparisons, or a "
            "table from this conversation. You write the content; numbers as plain digits "
            "(e.g. 120000, 12.5, 15%)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "also the file name"},
                "sheets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "columns": {"type": "array", "items": {"type": "string"}},
                            "rows": {
                                "type": "array",
                                "items": {"type": "array", "items": {"type": "string"}},
                            },
                            "totals": {
                                "type": "boolean",
                                "description": "add a total row for number columns",
                            },
                        },
                        "required": ["columns", "rows"],
                    },
                },
            },
            "required": ["title", "sheets"],
        },
        args_model=MakeSpreadsheetArgs,
        handler=make_spreadsheet,
    ),
]
