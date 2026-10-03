"""Expense reports for a day, week or month. Months and weeks follow the selected calendar:
a Jalali month (e.g. 1–30 Mehr) and a Saturday-first week, or a Gregorian month and a
Monday-first week.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

import jdatetime

from app.config import Calendar
from app.db.models import Category, Expense
from app.services.expenses import ExpenseService
from app.services.reminders import monthly_date

Kind = Literal["day", "week", "month"]


@dataclass
class CategoryTotal:
    category: Category
    total: int
    share: float  # 0..1


@dataclass
class Report:
    kind: Kind
    offset: int  # 0 = current period, 1 = previous, ...
    start: date
    end: date  # exclusive
    today: date
    expenses: list[Expense] = field(default_factory=list)
    by_category: list[CategoryTotal] = field(default_factory=list)
    previous_total: int = 0

    @property
    def total(self) -> int:
        return sum(e.amount for e in self.expenses)

    @property
    def largest(self) -> Expense | None:
        return max(self.expenses, key=lambda e: e.amount, default=None)

    @property
    def days_elapsed(self) -> int:
        """Days of the period up to today (for the daily average)."""
        last = min(self.end, self.today + timedelta(days=1))
        return max((last - self.start).days, 1)


def period_range(kind: Kind, today: date, calendar: Calendar, offset: int = 0) -> tuple[date, date]:
    """[start, end) of the period containing `today`, moved `offset` periods back."""
    if kind == "day":
        day = today - timedelta(days=offset)
        return day, day + timedelta(days=1)
    if kind == "week":
        first_weekday = 5 if calendar == Calendar.JALALI else 0  # Saturday / Monday
        start = today - timedelta(days=(today.weekday() - first_weekday) % 7 + 7 * offset)
        return start, start + timedelta(days=7)
    start = monthly_date(1, calendar.value, today, -offset)
    return start, monthly_date(1, calendar.value, today, 1 - offset)


def month_name(start: date, calendar: Calendar) -> tuple[int, int]:
    """(month 1-12, year) of a period start in the given calendar."""
    if calendar == Calendar.JALALI:
        j = jdatetime.date.fromgregorian(date=start)
        return j.month, j.year
    return start.month, start.year


class ReportService:
    def __init__(self, expenses: ExpenseService) -> None:
        self.expenses = expenses

    async def build(self, kind: Kind, today: date, calendar: Calendar, offset: int = 0) -> Report:
        start, end = period_range(kind, today, calendar, offset)
        items = await self.expenses.between(start, end)
        report = Report(kind=kind, offset=offset, start=start, end=end, today=today, expenses=items)

        totals: dict[int, int] = defaultdict(int)
        categories: dict[int, Category] = {}
        for expense in items:
            totals[expense.category_id] += expense.amount
            categories[expense.category_id] = expense.category
        grand = report.total or 1
        report.by_category = sorted(
            (CategoryTotal(categories[cid], total, total / grand) for cid, total in totals.items()),
            key=lambda c: c.total,
            reverse=True,
        )
        prev_start, prev_end = period_range(kind, today, calendar, offset + 1)
        if kind != "day":
            # Compare with the same number of days of the previous period.
            prev_end = min(prev_end, prev_start + timedelta(days=report.days_elapsed))
        report.previous_total = await self.expenses.total_between(prev_start, prev_end)
        return report
