"""Expense drafts, categories (keywords, learning, management), storage and reports."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.config import Calendar
from app.core.parsers.expense_rules import parse_expenses
from app.db.models import Category, Expense
from app.services.expenses import (
    DraftItem,
    ExpenseDraft,
    ExpenseService,
    builtin_category,
    keyword_key,
)
from app.services.reports import ReportService, period_range

TZ = ZoneInfo("Asia/Tehran")
TODAY = date(2026, 10, 4)  # Sunday, 12 Mehr 1405
NOW = datetime(2026, 10, 4, 18, 0, tzinfo=TZ)


def draft(text: str, currency="toman") -> ExpenseDraft:
    return ExpenseDraft.from_parse(parse_expenses(text, TODAY), text, currency)


def service(session, currency="toman") -> ExpenseService:
    return ExpenseService(session, TZ, currency)


# --- Draft ---


def test_draft_asks_scale_then_category():
    d = draft("۳ میلیون خرید خونه دادم، ۱۰ لیتر بنزین هم ۱۰۰ تومن")
    assert d.items[0].amount == 3_000_000
    assert d.next_step() == ("ambiguous", 1)
    assert d.items[1].choices("toman") == (100_000, 100_000_000)
    d.items[1].amount = 100_000
    d.items[1].raw_amount = None
    assert d.next_step() == ("category", 0)
    d.items[0].category_id = d.items[1].category_id = 1
    assert d.next_step() is None
    assert d.total == 3_100_000


def test_draft_missing_amount():
    d = draft("یه کتاب خریدم")
    assert d.next_step() == ("amount", 0)


def test_choices_in_rial():
    item = DraftItem(description="x")
    item.set_amount(3, True, "toman", "rial")
    assert item.choices("rial") == (30_000, 30_000_000)
    item.set_amount(50_000, False, "rial", "toman")
    assert item.amount == 5_000


def test_draft_round_trip():
    d = draft("دیروز ۵۰ هزار نون")
    assert ExpenseDraft.from_dict(d.to_dict()) == d
    assert d.spent_on == "2026-10-03"


# --- Categories ---


def test_builtin_keywords():
    assert builtin_category("بنزین") == "Fuel"
    assert builtin_category("خرید خونه") == "Groceries"
    assert builtin_category("اسنپ فود") == "Restaurant"  # longer match beats "اسنپ" (Transport)
    assert builtin_category("اسنپ") == "Transport"
    assert builtin_category("Pay electricity bill") == "Bills"
    assert builtin_category("عروسک") is None


async def test_classify_and_learn(sessionmaker):
    async with sessionmaker() as session:
        svc = service(session)
        fuel = await svc.classify("۱۰ لیتر بنزین")
        assert fuel is not None and fuel.name == "Fuel"
        assert await svc.classify("عروسک") is None

        gifts = next(c for c in await svc.categories() if c.name == "Gifts")
        await svc.learn("عروسک", gifts.id)
        learned = await svc.classify("عروسک")
        assert learned is not None and learned.name == "Gifts"

        # A learned keyword beats the built-in one.
        home = next(c for c in await svc.categories() if c.name == "Home")
        await svc.learn("خرید خونه", home.id)
        assert (await svc.classify("خرید خونه")).name == "Home"  # type: ignore[union-attr]


def test_keyword_key():
    assert keyword_key("  خرید   خونه ") == "خرید خونه"
    assert keyword_key("Groceries") == "groceries"


async def test_default_categories_are_seeded(sessionmaker):
    async with sessionmaker() as session:
        names = [c.name for c in await service(session).categories()]
    assert names[0] == "Groceries" and names[-1] == "Other"
    assert len(names) == 13


async def test_add_and_delete_category(sessionmaker):
    async with sessionmaker() as session:
        svc = service(session)
        pets = await svc.add_category("Pets", "🐶")
        assert pets is not None
        assert await svc.add_category("pets", "🐱") is None  # duplicate (case-insensitive)

        d = draft("غذای گربه ۲۰۰ هزار")
        d.items[0].category_id = pets.id
        await svc.add(d, NOW)
        assert await svc.delete_category(pets.id)
        expense = await session.scalar(select(Expense))
        other = await svc.other()
        assert expense is not None and expense.category_id == other.id
        assert not await svc.delete_category(other.id)  # "Other" is protected


# --- Storage & reports ---


async def _record(svc: ExpenseService, text: str, category: str, when: datetime = NOW):
    d = draft(text)
    cat = await svc.session.scalar(select(Category).where(Category.name == category))
    for item in d.items:
        item.category_id = cat.id  # type: ignore[union-attr]
        if item.ambiguous:
            item.amount, item.raw_amount = item.choices("toman")[0], None
    return await svc.add(d, when)


async def test_add_uses_the_mentioned_day(sessionmaker):
    async with sessionmaker() as session:
        svc = service(session)
        await _record(svc, "دیروز نون ۵۰ هزار", "Food")
        await _record(svc, "شیر ۳۰ هزار", "Food")
        assert [e.description for e in await svc.between(date(2026, 10, 3), TODAY)] == ["نون"]
        assert [e.description for e in await svc.between(TODAY, date(2026, 10, 5))] == ["شیر"]


async def test_delete(sessionmaker):
    async with sessionmaker() as session:
        svc = service(session)
        saved = await _record(svc, "نون ۵۰ هزار و شیر ۳۰ هزار", "Food")
        assert await svc.delete([e.id for e in saved]) == 2
        assert await session.scalar(select(func.count()).select_from(Expense)) == 0


def test_period_ranges():
    # Jalali: Mehr 1405 = 23 Sep – 22 Oct 2026; weeks start on Saturday.
    assert period_range("month", TODAY, Calendar.JALALI) == (date(2026, 9, 23), date(2026, 10, 23))
    assert period_range("month", TODAY, Calendar.JALALI, 1) == (
        date(2026, 8, 23),
        date(2026, 9, 23),
    )
    assert period_range("week", TODAY, Calendar.JALALI) == (date(2026, 10, 3), date(2026, 10, 10))
    # Gregorian: calendar month; weeks start on Monday.
    assert period_range("month", TODAY, Calendar.GREGORIAN) == (
        date(2026, 10, 1),
        date(2026, 11, 1),
    )
    assert period_range("week", TODAY, Calendar.GREGORIAN) == (date(2026, 9, 28), date(2026, 10, 5))
    assert period_range("day", TODAY, Calendar.JALALI, 1) == (date(2026, 10, 3), TODAY)


async def test_report(sessionmaker):
    async with sessionmaker() as session:
        svc = service(session)
        await _record(svc, "خرید خونه ۳ میلیون", "Groceries")
        await _record(svc, "بنزین ۱۰۰ هزار", "Fuel")
        await _record(svc, "نون ۵۰ هزار", "Food", datetime(2026, 9, 30, 12, tzinfo=TZ))
        # 10 Shahrivar: inside the first 12 days of last month (compared with 1–12 Mehr)
        await _record(svc, "ماه قبل ۲ میلیون", "Other", datetime(2026, 9, 1, 12, tzinfo=TZ))
        # 28 Shahrivar: outside the compared days
        await _record(svc, "آخر ماه ۵ میلیون", "Other", datetime(2026, 9, 19, 12, tzinfo=TZ))

        day = await ReportService(svc).build("day", TODAY, Calendar.JALALI)
        assert day.total == 3_100_000
        assert [c.category.name for c in day.by_category] == ["Groceries", "Fuel"]
        assert day.largest is not None and day.largest.description == "خرید خونه"

        month = await ReportService(svc).build("month", TODAY, Calendar.JALALI)
        assert month.total == 3_150_000  # Mehr: 23 Sep onwards
        assert month.previous_total == 2_000_000  # same days of Shahrivar
        assert month.days_elapsed == 12
        assert month.total // month.days_elapsed == 262_500
        assert round(month.by_category[0].share, 2) == 0.95


async def test_amount_uses_configured_currency(sessionmaker):
    d = draft("۵۰۰۰۰ ریال نون", currency="toman")
    assert d.items[0].amount == 5_000
