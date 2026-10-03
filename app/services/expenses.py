"""Expenses: drafts (what still needs asking), categories (keywords + learning) and storage.

Flow: text → `parse_expenses` → `ExpenseDraft` → questions until `next_step()` is None
(missing amount → thousand-or-million? → category) → `ExpenseService.add()`.

Categorising an item, in order:
1. learned keywords: descriptions whose category the user corrected before
2. built-in keywords below (Persian + English)
3. the LLM (see `expense_ai`), and finally "Other"
"""

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.normalizer import normalize
from app.core.parsers.amount_parser import Currency, to_currency
from app.core.parsers.expense_rules import ExpenseParse
from app.core.textmatch import best_match
from app.db.models import Category, CategoryKeyword, Expense
from app.services.reminders import to_utc

OTHER = "Other"

# Built-in keywords for the default categories (matched against the normalized description).
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Groceries": [
        "خرید خونه", "خرید خانه", "سوپر", "سوپرمارکت", "هایپر", "فروشگاه", "بقالی", "تره بار",
        "groceries", "grocery", "supermarket", "market",
    ],
    "Food": [
        "نون", "نان", "شیر", "پنیر", "ماست", "تخم مرغ", "گوشت", "مرغ", "برنج", "میوه", "سبزی",
        "روغن", "قند", "شکر", "چای", "تنقلات", "خوراکی", "bread", "milk", "cheese", "eggs",
        "meat", "chicken", "rice", "fruit", "vegetables", "snack", "snacks",
    ],
    "Restaurant": [
        "رستوران", "کافه", "فست فود", "پیتزا", "ساندویچ", "همبرگر", "اسنپ فود", "سفارش غذا",
        "ناهار", "شام", "صبحانه بیرون", "قهوه", "بستنی", "restaurant", "cafe", "coffee", "pizza",
        "burger", "sandwich", "takeaway", "delivery", "lunch", "dinner",
    ],
    "Home": [
        "لوازم خانه", "لوازم خونه", "اثاث", "مبل", "فرش", "تعمیر", "تعمیرات", "شوینده", "ظرف",
        "لامپ", "furniture", "repair", "cleaning", "household", "kitchen",
    ],
    "Fuel": ["بنزین", "گازوئیل", "سوخت", "cng", "fuel", "gas", "petrol", "diesel"],
    "Transport": [
        "تاکسی", "اسنپ", "تپسی", "مترو", "اتوبوس", "بلیط", "کرایه", "پارکینگ", "عوارض", "آژانس",
        "taxi", "uber", "metro", "bus", "train", "ticket", "parking", "toll",
    ],
    "Bills": [
        "قبض", "برق", "گاز خانه", "قبض گاز", "قبض آب", "اینترنت", "شارژ", "موبایل", "تلفن",
        "اجاره", "قسط", "اشتراک", "bill", "electricity", "water bill", "internet", "phone",
        "rent", "loan", "subscription",
    ],
    "Health": [
        "دکتر", "پزشک", "دارو", "داروخانه", "بیمارستان", "آزمایش", "دندون", "دندان", "عینک",
        "ویزیت", "doctor", "medicine", "pharmacy", "hospital", "dentist", "clinic",
    ],
    "Clothing": [
        "لباس", "کفش", "پیراهن", "شلوار", "مانتو", "کاپشن", "تیشرت", "jacket", "clothes",
        "shoes", "shirt", "pants", "dress",
    ],
    "Education": [
        "کتاب", "کلاس", "دوره", "شهریه", "آموزش", "دانشگاه", "مدرسه", "book", "course", "class",
        "tuition", "school", "university",
    ],
    "Gifts": ["هدیه", "کادو", "gift", "present"],
    "Leisure": [
        "سینما", "تئاتر", "کنسرت", "بازی", "سفر", "تفریح", "پارک", "استخر", "باشگاه", "cinema",
        "movie", "concert", "game", "trip", "travel", "netflix", "gym",
    ],
}  # fmt: skip


def keyword_key(text: str) -> str:
    """Normalized form used for keyword matching and learning."""
    return re.sub(r"\s+", " ", normalize(text)).strip()


def _contains(haystack: str, needle: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


def builtin_category(description: str) -> str | None:
    """Category name from the built-in keywords (longest match wins)."""
    key = keyword_key(description)
    best: tuple[int, str] | None = None
    for name, words in CATEGORY_KEYWORDS.items():
        for word in words:
            if _contains(key, keyword_key(word)) and (best is None or len(word) > best[0]):
                best = (len(word), name)
    return best[1] if best else None


# --- Draft ---


@dataclass
class DraftItem:
    description: str
    amount: int | None = None  # in the configured currency; None until known
    raw_amount: float | None = None  # ambiguous value as typed (thousand or million?)
    raw_currency: str | None = None  # currency written next to the ambiguous value
    quantity: float | None = None
    unit: str | None = None
    category_id: int | None = None

    @property
    def ambiguous(self) -> bool:
        return self.amount is None and self.raw_amount is not None

    def set_amount(
        self, value: float, ambiguous: bool, given: str | None, currency: Currency
    ) -> None:
        """Store a parsed amount: ambiguous values wait for "thousand or million?"."""
        if ambiguous:
            self.amount, self.raw_amount, self.raw_currency = None, value, given
        else:
            self.amount = to_currency(value, given, currency)  # type: ignore[arg-type]
            self.raw_amount = self.raw_currency = None

    def choices(self, currency: Currency) -> tuple[int, int]:
        """(as thousands, as millions) for an ambiguous amount."""
        raw = self.raw_amount or 0
        given = self.raw_currency  # type: ignore[arg-type]
        return (
            to_currency(raw * 1_000, given, currency),  # type: ignore[arg-type]
            to_currency(raw * 1_000_000, given, currency),  # type: ignore[arg-type]
        )


@dataclass
class ExpenseDraft:
    raw: str
    items: list[DraftItem] = field(default_factory=list)
    spent_on: str | None = None  # ISO date; None = today

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ExpenseDraft":
        return cls(
            raw=data["raw"],
            items=[DraftItem(**item) for item in data["items"]],
            spent_on=data.get("spent_on"),
        )

    @classmethod
    def from_parse(cls, parse: ExpenseParse, raw: str, currency: Currency) -> "ExpenseDraft":
        draft = cls(raw=raw, spent_on=parse.spent_on.isoformat() if parse.spent_on else None)
        for item in parse.items:
            entry = DraftItem(description=item.description, quantity=item.quantity, unit=item.unit)
            if item.amount is not None:
                entry.set_amount(item.amount, item.ambiguous, item.currency, currency)
            draft.items.append(entry)
        return draft

    def next_step(self) -> tuple[str, int] | None:
        """("amount" | "ambiguous" | "category", item index) or None when ready."""
        for i, item in enumerate(self.items):
            if item.amount is None and item.raw_amount is None:
                return "amount", i
        for i, item in enumerate(self.items):
            if item.ambiguous:
                return "ambiguous", i
        for i, item in enumerate(self.items):
            if item.category_id is None:
                return "category", i
        return None

    @property
    def total(self) -> int:
        return sum(item.amount or 0 for item in self.items)


# --- Storage ---


class ExpenseService:
    def __init__(self, session: AsyncSession, timezone: ZoneInfo, currency: Currency) -> None:
        self.session = session
        self.timezone = timezone
        self.currency = currency

    # --- Categories ---

    async def categories(self) -> list[Category]:
        rows = await self.session.scalars(select(Category).order_by(Category.position, Category.id))
        return list(rows.all())

    async def category(self, category_id: int) -> Category | None:
        return await self.session.get(Category, category_id)

    async def other(self) -> Category:
        found = await self.session.scalar(select(Category).where(Category.name == OTHER))
        if found is None:  # the user can't delete it, but be safe
            found = Category(name=OTHER, emoji="📦", is_default=True, position=999)
            self.session.add(found)
            await self.session.commit()
        return found

    async def add_category(self, name: str, emoji: str) -> Category | None:
        """None if a category with that name exists."""
        exists = await self.session.scalar(
            select(Category).where(func.lower(Category.name) == name.lower())
        )
        if exists:
            return None
        position = (await self.session.scalar(select(func.max(Category.position)))) or 0
        category = Category(name=name, emoji=emoji, is_default=False, position=position + 1)
        self.session.add(category)
        await self.session.commit()
        return category

    async def delete_category(self, category_id: int) -> bool:
        """Expenses of the category move to "Other". "Other" itself can't be deleted."""
        category = await self.category(category_id)
        if category is None or category.name == OTHER:
            return False
        other = await self.other()
        await self.session.execute(
            update(Expense).where(Expense.category_id == category_id).values(category_id=other.id)
        )
        await self.session.execute(
            delete(CategoryKeyword).where(CategoryKeyword.category_id == category_id)
        )
        await self.session.delete(category)
        await self.session.commit()
        return True

    async def classify(self, description: str) -> Category | None:
        """Learned keywords first, then the built-in ones. None if nothing matches."""
        return await self.learned_category(description) or await self.keyword_category(description)

    async def learned_category(self, description: str) -> Category | None:
        """The category the user chose before for this description (corrections are learned)."""
        key = keyword_key(description)
        if not key:
            return None
        learned = (await self.session.execute(select(CategoryKeyword))).scalars().all()
        matches = [k for k in learned if k.keyword == key or _contains(key, k.keyword)]
        if not matches:
            return None
        best = max(matches, key=lambda k: len(k.keyword))
        return await self.category(best.category_id)

    async def keyword_category(self, description: str) -> Category | None:
        name = builtin_category(description)
        return await self.category_by_name(name) if name else None

    async def category_by_name(self, name: str) -> Category | None:
        """Case-insensitive; an emoji in front of the name is ignored ("🛒 Groceries")."""
        clean = re.sub(r"^[^\w]+", "", name.strip()).lower()
        if not clean:
            return None
        return await self.session.scalar(select(Category).where(func.lower(Category.name) == clean))

    async def learn(self, description: str, category_id: int) -> None:
        key = keyword_key(description)
        if not key:
            return
        existing = await self.session.scalar(
            select(CategoryKeyword).where(CategoryKeyword.keyword == key)
        )
        if existing:
            existing.category_id = category_id
        else:
            self.session.add(CategoryKeyword(keyword=key[:100], category_id=category_id))
        await self.session.commit()

    # --- Expenses ---

    def _spent_at(self, spent_on: str | None, now: datetime) -> datetime:
        if spent_on is None or date.fromisoformat(spent_on) == now.date():
            return to_utc(now)
        return to_utc(datetime.combine(date.fromisoformat(spent_on), time(12), self.timezone))

    async def add(self, draft: ExpenseDraft, now: datetime) -> list[Expense]:
        spent_at = self._spent_at(draft.spent_on, now)
        expenses = [
            Expense(
                amount=item.amount or 0,
                category_id=item.category_id,
                description=item.description,
                quantity=item.quantity,
                unit=item.unit,
                spent_at=spent_at,
                raw_text=draft.raw,
            )
            for item in draft.items
        ]
        self.session.add_all(expenses)
        await self.session.commit()
        return expenses

    async def get(self, expense_id: int) -> Expense | None:
        return await self.session.get(Expense, expense_id)

    async def by_ids(self, expense_ids: list[int]) -> list[Expense]:
        rows = await self.session.scalars(
            select(Expense).where(Expense.id.in_(expense_ids)).order_by(Expense.id)
        )
        return list(rows.unique().all())

    async def search(
        self, query: str, start: date, end: date
    ) -> tuple[Expense | None, list[Expense]]:
        """(the single clear match, all matches) among expenses of [start, end)."""
        return best_match(
            await self.between(start, end),
            query,
            key=lambda e: f"{e.description} {e.category.name}",
        )

    async def update(
        self,
        expense_id: int,
        *,
        amount: int | None = None,
        description: str | None = None,
        category_id: int | None = None,
        spent_on: str | None = None,
        now: datetime | None = None,
    ) -> tuple[Expense, dict] | None:
        """Change fields of an expense. Returns (expense, previous row) for ↩️ Undo."""
        expense = await self.get(expense_id)
        if expense is None:
            return None
        previous = self.to_row(expense)
        if amount is not None:
            expense.amount = amount
        if description is not None:
            expense.description = description
        if category_id is not None:
            expense.category_id = category_id
        if spent_on is not None:
            expense.spent_at = self._spent_at(spent_on, now or datetime.now(self.timezone))
        await self.session.commit()
        await self.session.refresh(expense)
        return expense, previous

    @staticmethod
    def to_row(expense: Expense) -> dict:
        return {
            "id": expense.id,
            "amount": expense.amount,
            "category_id": expense.category_id,
            "description": expense.description,
            "quantity": expense.quantity,
            "unit": expense.unit,
            "spent_at": expense.spent_at.isoformat(),
            "raw_text": expense.raw_text,
            "created_at": expense.created_at.isoformat(),
        }

    async def restore(self, rows: list[dict]) -> list[Expense]:
        """Put deleted expenses back (same ids) or revert edited ones to `rows`."""
        restored = []
        for row in rows:
            values = {
                **row,
                "spent_at": datetime.fromisoformat(row["spent_at"]),
                "created_at": datetime.fromisoformat(row["created_at"]),
            }
            expense = await self.get(row["id"])
            if expense is None:
                expense = Expense(**values)
                self.session.add(expense)
            else:
                for key, value in values.items():
                    setattr(expense, key, value)
            restored.append(expense)
        await self.session.commit()
        return restored

    async def delete(self, expense_ids: list[int]) -> int:
        result = await self.session.execute(delete(Expense).where(Expense.id.in_(expense_ids)))
        await self.session.commit()
        return result.rowcount or 0  # type: ignore[attr-defined]

    async def between(self, start: date, end: date) -> list[Expense]:
        """Expenses with local date in [start, end), newest first."""
        lo = to_utc(datetime.combine(start, time(0), self.timezone))
        hi = to_utc(datetime.combine(end, time(0), self.timezone))
        rows = await self.session.scalars(
            select(Expense)
            .where(Expense.spent_at >= lo, Expense.spent_at < hi)
            .order_by(Expense.spent_at.desc(), Expense.id.desc())
        )
        return list(rows.unique().all())

    async def total_between(self, start: date, end: date) -> int:
        lo = to_utc(datetime.combine(start, time(0), self.timezone))
        hi = to_utc(datetime.combine(end, time(0), self.timezone))
        total = await self.session.scalar(
            select(func.coalesce(func.sum(Expense.amount), 0)).where(
                Expense.spent_at >= lo, Expense.spent_at < hi
            )
        )
        return int(total or 0)
