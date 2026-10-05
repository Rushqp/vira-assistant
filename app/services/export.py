"""Excel files (xlsx) for the chat: expenses, reminders and any table.

Every builder returns an `ExportFile` (file name, bytes, title). Dates follow the selected
calendar: Jalali dates are written as sortable text (`1405/07/12`), Gregorian ones as real date
cells. Amounts are numbers with a thousands format. Totals are written as values (not formulas)
so phone viewers that don't calculate still show them.

openpyxl is imported only when a file is built: it (and numpy, which it loads when installed)
would otherwise take ~40 MB of RAM for the whole life of the bot.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from io import BytesIO
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import jdatetime

from app import texts
from app.config import Calendar
from app.core.normalizer import normalize
from app.core.parsers.datetime_parser import RepeatRule
from app.db.models import Expense, Reminder
from app.services.reminders import from_utc, monthly_date
from app.services.reports import month_name
from app.utils.calendar import JALALI_MONTHS

if TYPE_CHECKING:
    from openpyxl import Workbook
    from openpyxl.worksheet.worksheet import Worksheet

EXPENSE_COLUMNS = ("date", "weekday", "time", "description", "category", "quantity", "amount")
SUMMARIES = ("category", "day", "week", "month")

# A summary lists every day / week / month of the range (zeros too) up to these sizes, and
# only the ones with expenses beyond them; charts are added up to the same sizes.
FULL_DAYS, FULL_WEEKS, FULL_MONTHS = 62, 26, 24

HEADER_COLOR = "2F5597"
MONEY = "#,##0"
DECIMAL = "#,##0.00"
PERCENT = "0.0%"
DATE_FORMAT = "yyyy-mm-dd"
MAX_WIDTH = 60


@dataclass
class ExportFile:
    filename: str
    content: bytes
    title: str
    rows: int  # data rows of the main sheet


# --- Dates and labels ---


def date_cell(day: date, calendar: Calendar) -> str | date:
    """Sortable Jalali text, or the Gregorian date itself (a real date cell)."""
    if calendar == Calendar.JALALI:
        j = jdatetime.date.fromgregorian(date=day)
        return f"{j.year}/{j.month:02d}/{j.day:02d}"
    return day


def date_text(day: date, calendar: Calendar) -> str:
    value = date_cell(day, calendar)
    return value if isinstance(value, str) else f"{value:%Y/%m/%d}"


def _month_label(start: date, calendar: Calendar) -> str:
    month, year = month_name(start, calendar)
    names = JALALI_MONTHS["en"] if calendar == Calendar.JALALI else texts.GREGORIAN_MONTH_NAMES
    return f"{names[month - 1]} {year}"


def _is_month(start: date, end: date, calendar: Calendar) -> bool:
    return start == monthly_date(1, calendar.value, start) and end == monthly_date(
        1, calendar.value, start, 1
    )


def _is_year(start: date, end: date, calendar: Calendar) -> bool:
    if calendar == Calendar.JALALI:
        j = jdatetime.date.fromgregorian(date=start)
        first = jdatetime.date(j.year, 1, 1).togregorian()
        return start == first and end == jdatetime.date(j.year + 1, 1, 1).togregorian()
    return start == date(start.year, 1, 1) and end == date(start.year + 1, 1, 1)


def range_label(start: date, end: date, calendar: Calendar) -> tuple[str, str]:
    """(title part, file-name part) of [start, end): `Mehr 1405` / `1405-07`."""
    last = end - timedelta(days=1)
    if start == last:
        text = date_text(start, calendar)
        return text, text.replace("/", "-")
    if _is_month(start, end, calendar):
        number = date_text(start, calendar)[:7]
        return _month_label(start, calendar), number.replace("/", "-")
    if _is_year(start, end, calendar):
        year = date_text(start, calendar)[:4]
        return year, year
    first, final = date_text(start, calendar), date_text(last, calendar)
    return f"{first} – {final}", f"{first}_{final}".replace("/", "-")


def _weekday(day: date) -> str:
    return texts.WEEKDAY_NAMES[day.weekday()]


# --- Sheets ---


def _new_workbook() -> Workbook:
    from openpyxl import Workbook

    return Workbook()


def _style_header(ws: Worksheet) -> None:
    from openpyxl.styles import Alignment, Font, PatternFill

    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=HEADER_COLOR)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"


def _write_table(
    ws: Worksheet,
    headers: list[str],
    rows: list[list[Any]],
    formats: dict[int, str] | None = None,
    total: list[Any] | None = None,
) -> None:
    """Header, rows (with a filter), an optional bold total row; `formats` by column (1-based)."""
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    _append(ws, headers)
    _style_header(ws)
    for row in rows:
        _append(ws, row)
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"
    if total is not None:
        _append(ws, total)
        for cell in ws[ws.max_row]:
            cell.font = Font(bold=True)
    for column, number_format in (formats or {}).items():
        for (cell,) in ws.iter_rows(min_row=2, min_col=column, max_col=column):
            if isinstance(cell.value, int | float | date) and not isinstance(cell.value, bool):
                cell.number_format = number_format
    _fit_columns(ws)


def _append(ws: Worksheet, row: list[Any]) -> None:
    """Add a row. Text is always text: control characters are dropped (Excel refuses them) and
    "=…" stays a string instead of becoming a formula."""
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

    ws.append([ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v for v in row])
    for cell in ws[ws.max_row]:
        if cell.data_type == "f":
            cell.data_type = "s"


def _display(value: Any) -> str:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return f"{value:,}"
    if isinstance(value, date):
        return "0000-00-00"
    return str(value) if value is not None else ""


def _fit_columns(ws: Worksheet) -> None:
    from openpyxl.utils import get_column_letter

    widths: dict[int, int] = defaultdict(int)
    for row in ws.iter_rows():
        for cell in row:
            longest = max((len(line) for line in _display(cell.value).splitlines()), default=0)
            widths[cell.column] = max(widths[cell.column], longest)
    for column, width in widths.items():
        ws.column_dimensions[get_column_letter(column)].width = min(max(width + 3, 8), MAX_WIDTH)


def _chart(ws: Worksheet, kind: str, title: str, rows: int, values_col: int, anchor: str) -> None:
    """A pie (shares) or bar chart of column `values_col` against the labels in column A."""
    from openpyxl.chart import BarChart, PieChart, Reference

    chart = PieChart() if kind == "pie" else BarChart()
    chart.title = title
    data = Reference(ws, min_col=values_col, min_row=1, max_row=rows + 1)
    labels = Reference(ws, min_col=1, min_row=2, max_row=rows + 1)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(labels)
    if isinstance(chart, BarChart):
        chart.legend = None
        chart.y_axis.numFmt = MONEY
        chart.width = min(max(12, rows * 0.8), 30)
    ws.add_chart(chart, anchor)


def _save(wb: Workbook, title: str) -> bytes:
    wb.properties.title = title
    wb.properties.creator = "Vira"
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# --- Expenses ---


@dataclass
class ExpenseExport:
    expenses: list[Expense]
    start: date
    end: date  # exclusive
    today: date
    calendar: Calendar
    tz: ZoneInfo
    currency: str  # label shown in headers, e.g. "Toman"
    columns: list[str] = field(default_factory=lambda: list(EXPENSE_COLUMNS))
    summaries: list[str] = field(default_factory=lambda: ["category", "day"])
    chart: bool = True
    title: str = ""
    label_calendar: Calendar | None = None  # of the title / file name (default: `calendar`)


def _expense_value(column: str, expense: Expense, spec: ExpenseExport) -> Any:
    local = from_utc(expense.spent_at, spec.tz)
    match column:
        case "date":
            return date_cell(local.date(), spec.calendar)
        case "weekday":
            return _weekday(local.date())
        case "time":
            return f"{local:%H:%M}"
        case "description":
            return expense.description or texts.EXPENSE_NO_DESCRIPTION
        case "category":
            return expense.category.name
        case "quantity":
            if expense.quantity is None:
                return ""
            return f"{expense.quantity:g} {expense.unit}" if expense.unit else expense.quantity
        case _:
            return expense.amount


def _expense_header(column: str, currency: str) -> str:
    return texts.XLSX_EXPENSE_HEADERS[column].format(currency=currency)


def _days(spec: ExpenseExport, items: list[tuple[date, Expense]]) -> list[date]:
    last = min(spec.end, spec.today + timedelta(days=1))
    span = (last - spec.start).days
    if 0 < span <= FULL_DAYS:
        return [spec.start + timedelta(days=n) for n in range(span)]
    return sorted({day for day, _ in items})


def _week_start(day: date, calendar: Calendar) -> date:
    first_weekday = 5 if calendar == Calendar.JALALI else 0  # Saturday / Monday
    return day - timedelta(days=(day.weekday() - first_weekday) % 7)


def _grouped(
    items: list[tuple[date, Expense]], key
) -> dict[Any, tuple[int, int]]:  # key → (amount, count)
    totals: dict[Any, list[int]] = defaultdict(lambda: [0, 0])
    for day, expense in items:
        entry = totals[key(day, expense)]
        entry[0] += expense.amount
        entry[1] += 1
    return {k: (v[0], v[1]) for k, v in totals.items()}


def _add_by_category(wb: Workbook, items, spec: ExpenseExport, total: int) -> None:
    ws = wb.create_sheet(texts.XLSX_SHEET_CATEGORIES)
    groups = _grouped(items, lambda _day, e: e.category.name)
    ordered = sorted(groups.items(), key=lambda kv: kv[1][0], reverse=True)
    rows = [
        [name, amount, amount / total if total else 0, count] for name, (amount, count) in ordered
    ]
    headers = [h.format(currency=spec.currency) for h in texts.XLSX_CATEGORY_HEADERS]
    _write_table(
        ws,
        headers,
        rows,
        {2: MONEY, 3: PERCENT},
        [texts.XLSX_TOTAL, total, 1 if total else 0, len(items)],
    )
    if spec.chart and rows:
        _chart(ws, "pie", texts.XLSX_SHEET_CATEGORIES, len(rows), 2, "F2")


def _add_by_day(wb: Workbook, items, spec: ExpenseExport, total: int) -> None:
    ws = wb.create_sheet(texts.XLSX_SHEET_DAYS)
    groups = _grouped(items, lambda day, _e: day)
    days = _days(spec, items)
    rows = [
        [date_cell(day, spec.calendar), _weekday(day), *groups.get(day, (0, 0))] for day in days
    ]
    headers = [h.format(currency=spec.currency) for h in texts.XLSX_DAY_HEADERS]
    _write_table(
        ws, headers, rows, {1: DATE_FORMAT, 3: MONEY}, [texts.XLSX_TOTAL, "", total, len(items)]
    )
    if spec.chart and 0 < len(rows) <= FULL_DAYS:
        _chart(ws, "bar", texts.XLSX_SHEET_DAYS, len(rows), 3, "F2")


def _add_by_week(wb: Workbook, items, spec: ExpenseExport, total: int) -> None:
    ws = wb.create_sheet(texts.XLSX_SHEET_WEEKS)
    groups = _grouped(items, lambda day, _e: _week_start(day, spec.calendar))
    weeks = sorted({_week_start(day, spec.calendar) for day in _days(spec, items)} | set(groups))
    if len(weeks) > FULL_WEEKS:
        weeks = sorted(groups)
    rows = []
    for start in weeks:
        first = max(start, spec.start)  # the range may begin or end mid-week
        last = min(start + timedelta(days=6), spec.end - timedelta(days=1))
        label = f"{date_text(first, spec.calendar)} – {date_text(last, spec.calendar)}"
        rows.append([label, *groups.get(start, (0, 0))])
    headers = [h.format(currency=spec.currency) for h in texts.XLSX_WEEK_HEADERS]
    _write_table(ws, headers, rows, {2: MONEY}, [texts.XLSX_TOTAL, total, len(items)])
    if spec.chart and 0 < len(rows) <= FULL_WEEKS:
        _chart(ws, "bar", texts.XLSX_SHEET_WEEKS, len(rows), 2, "E2")


def _add_by_month(wb: Workbook, items, spec: ExpenseExport, total: int) -> None:
    ws = wb.create_sheet(texts.XLSX_SHEET_MONTHS)
    cal = spec.calendar.value
    groups = _grouped(items, lambda day, _e: monthly_date(1, cal, day))
    months: set[date] = set(groups)
    last = min(spec.end, spec.today + timedelta(days=1)) - timedelta(days=1)
    current = monthly_date(1, cal, spec.start)
    while current <= last and len(months) <= FULL_MONTHS:
        months.add(current)
        current = monthly_date(1, cal, current, 1)
    if len(months) > FULL_MONTHS:
        months = set(groups)
    rows = [[_month_label(m, spec.calendar), *groups.get(m, (0, 0))] for m in sorted(months)]
    headers = [h.format(currency=spec.currency) for h in texts.XLSX_MONTH_HEADERS]
    _write_table(ws, headers, rows, {2: MONEY}, [texts.XLSX_TOTAL, total, len(items)])
    if spec.chart and 0 < len(rows) <= FULL_MONTHS:
        _chart(ws, "bar", texts.XLSX_SHEET_MONTHS, len(rows), 2, "E2")


def build_expenses(spec: ExpenseExport) -> ExportFile:
    ordered = sorted(spec.expenses, key=lambda e: (e.spent_at, e.id))
    items = [(from_utc(e.spent_at, spec.tz).date(), e) for e in ordered]
    total = sum(e.amount for e in ordered)
    columns = [c for c in EXPENSE_COLUMNS if c in spec.columns] or list(EXPENSE_COLUMNS)
    if "amount" not in columns:
        columns.append("amount")

    label, slug = range_label(spec.start, spec.end, spec.label_calendar or spec.calendar)
    title = spec.title or f"{texts.XLSX_EXPENSES_TITLE} · {label}"
    wb = _new_workbook()
    ws = wb.active
    ws.title = texts.XLSX_SHEET_EXPENSES
    rows = [[_expense_value(c, e, spec) for c in columns] for _, e in items]
    total_row: list[Any] = [""] * len(columns)
    total_row[columns.index("amount")] = total
    label_at = next((i for i, c in enumerate(columns) if c != "amount"), None)
    if label_at is not None:
        total_row[label_at] = texts.XLSX_TOTAL
    formats = {columns.index("amount") + 1: MONEY}
    if "date" in columns:
        formats[columns.index("date") + 1] = DATE_FORMAT
    _write_table(ws, [_expense_header(c, spec.currency) for c in columns], rows, formats, total_row)

    builders = {
        "category": _add_by_category,
        "day": _add_by_day,
        "week": _add_by_week,
        "month": _add_by_month,
    }
    for summary in SUMMARIES:
        if summary in spec.summaries:
            builders[summary](wb, items, spec, total)
    return ExportFile(f"vira-expenses-{slug}.xlsx", _save(wb, title), title, len(rows))


# --- Reminders ---


def repeat_text(rule: str | None) -> str:
    if not rule:
        return ""
    parsed = RepeatRule.parse(rule)
    if parsed.kind == "daily":
        return texts.REPEAT_DAILY
    if parsed.kind == "weekly":
        return texts.REPEAT_WEEKLY.format(weekday=texts.WEEKDAY_NAMES[parsed.weekday or 0])
    return texts.REPEAT_MONTHLY.format(
        day=parsed.day, calendar=texts.CALENDAR_NAMES.get(parsed.calendar or "", "")
    )


@dataclass
class ReminderExport:
    reminders: list[Reminder]
    calendar: Calendar
    tz: ZoneInfo
    label: str  # title part, e.g. "Upcoming" or "Mehr 1405"
    slug: str  # file-name part
    title: str = ""


def build_reminders(spec: ReminderExport) -> ExportFile:
    title = spec.title or f"{texts.XLSX_REMINDERS_TITLE} · {spec.label}"
    wb = _new_workbook()
    ws = wb.active
    ws.title = texts.XLSX_SHEET_REMINDERS
    rows = []
    for reminder in sorted(spec.reminders, key=lambda r: (r.event_at, r.id)):
        event = from_utc(reminder.event_at, spec.tz)
        alerts = sorted(a.notify_at for a in reminder.alerts if a.sent_at is None)
        rows.append(
            [
                date_cell(event.date(), spec.calendar),
                _weekday(event.date()),
                texts.REMINDER_ALL_DAY if reminder.all_day else f"{event:%H:%M}",
                reminder.text,
                repeat_text(reminder.repeat_rule),
                ", ".join(
                    f"{date_text(from_utc(t, spec.tz).date(), spec.calendar)} "
                    f"{from_utc(t, spec.tz):%H:%M}"
                    for t in alerts
                ),
                texts.XLSX_YES if reminder.important else "",
                texts.XLSX_STATUS.get(reminder.status, reminder.status),
            ]
        )
    _write_table(ws, list(texts.XLSX_REMINDER_HEADERS), rows, {1: DATE_FORMAT})
    return ExportFile(f"vira-reminders-{spec.slug}.xlsx", _save(wb, title), title, len(rows))


# --- Any table ---

_SHEET_NAME_BAD = re.compile(r"[\[\]:*?/\\]")
_NUMBER = re.compile(r"^-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")
_PERCENT = re.compile(r"^-?\d+(?:\.\d+)?%$")
_FILE_NAME_BAD = re.compile(r"[^\w\-]+", re.UNICODE)
# Number columns a total row must not add up: years, dates, ids, ranks, percentages …
_NOT_SUMMED = re.compile(
    r"year|date|\bid\b|\bno\b|#|code|phone|rank|rate|percent|%|سال|تاریخ|شماره|کد|تلفن|رتبه|درصد|نرخ",
    re.IGNORECASE,
)


@dataclass
class TableSheet:
    name: str
    columns: list[str]
    rows: list[list[Any]]
    totals: bool = False


def table_cell(value: Any) -> Any:
    """Numbers stay numbers; "120,000", «۱۲۰۰۰۰» and "15%" become numbers; codes with a
    leading zero (phone numbers) and very long digit strings stay text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return texts.XLSX_YES if value else texts.XLSX_NO
    if isinstance(value, int | float):
        return value
    text = str(value).strip()
    plain = normalize(text, lowercase=False).replace(" ", "")
    digits = plain.lstrip("-").replace(",", "").split(".")[0]
    if _NUMBER.match(plain) and len(digits) <= 15 and not (len(digits) > 1 and digits[0] == "0"):
        number = float(plain.replace(",", ""))
        return int(number) if number.is_integer() and "." not in plain else number
    if _PERCENT.match(plain):
        return float(plain[:-1]) / 100
    return text


def sheet_name(name: str, used: set[str]) -> str:
    base = _SHEET_NAME_BAD.sub("", name).strip()[:31] or texts.XLSX_SHEET_DEFAULT
    candidate, n = base, 2
    while candidate.lower() in used:
        suffix = f" ({n})"
        candidate = base[: 31 - len(suffix)] + suffix
        n += 1
    used.add(candidate.lower())
    return candidate


def file_slug(title: str) -> str:
    slug = _FILE_NAME_BAD.sub("-", normalize(title, lowercase=False)).strip("-_")
    return slug[:60].strip("-_") or "vira-table"


def build_table(title: str, sheets: list[TableSheet]) -> ExportFile:
    wb = _new_workbook()
    used: set[str] = set()
    rows_total = 0
    for index, sheet in enumerate(sheets):
        ws = wb.active if index == 0 else wb.create_sheet()
        ws.title = sheet_name(sheet.name, used)
        width = max([len(sheet.columns), *(len(r) for r in sheet.rows)], default=0)
        headers = [*sheet.columns, *[""] * (width - len(sheet.columns))]
        rows = [[table_cell(v) for v in row] + [""] * (width - len(row)) for row in sheet.rows]
        formats: dict[int, str] = {}
        numeric: list[int] = []
        for col in range(width):
            values = [r[col] for r in rows if r[col] != ""]
            if not values or not all(isinstance(v, int | float) for v in values):
                continue
            numeric.append(col)
            raw = [
                str(r[col]).strip() for r in sheet.rows if col < len(r) and r[col] not in ("", None)
            ]
            if all(v.endswith("%") for v in raw):
                formats[col + 1] = PERCENT
            elif all(isinstance(v, int) for v in values):
                # Thousands separators for amounts, not for years or small counts.
                formats[col + 1] = MONEY if max(abs(v) for v in values) >= 10_000 else "0"
            else:
                formats[col + 1] = DECIMAL
        total = None
        summed = [
            col
            for col in numeric
            if formats.get(col + 1) != PERCENT and not _NOT_SUMMED.search(str(headers[col]))
        ]
        if sheet.totals and summed:
            total = [""] * width
            for col in summed:
                total[col] = sum(r[col] for r in rows if r[col] != "")
            if 0 not in summed:
                total[0] = texts.XLSX_TOTAL
        _write_table(ws, headers, rows, formats, total)
        rows_total += len(rows)
    return ExportFile(f"{file_slug(title)}.xlsx", _save(wb, title), title, rows_total)
