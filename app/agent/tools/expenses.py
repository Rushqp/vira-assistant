"""Expense tools: add (several at once), list, update, delete."""

from datetime import date

from pydantic import Field

from app.agent.tools import (
    Args,
    Card,
    Clarification,
    Tool,
    ToolContext,
    ToolError,
    ToolOutcome,
)
from app.agent.tools.common import jalali, parse_amount_text, parse_date_arg, period_dates
from app.db.models import Category, Expense
from app.services.expenses import DraftItem, ExpenseDraft
from app.services.reminders import from_utc

PERIOD_ENUM = ["today", "yesterday", "this_week", "last_week", "this_month", "last_month", "recent"]
AMOUNT_HINT = (
    "copy the amount exactly as the user wrote it, with its words, e.g. '۱۵۰ هزار تومن' or '3m'"
)


def expense_info(expense: Expense, ctx: ToolContext) -> dict:
    day = from_utc(expense.spent_at, ctx.config.timezone).date()
    return {
        "id": expense.id,
        "description": expense.description,
        "amount": expense.amount,
        "category": expense.category.name,
        "date": day.isoformat(),
        "date_jalali": jalali(day),
    }


async def _category(ctx: ToolContext, description: str, suggested: str | None) -> Category:
    """Learned correction > the model's suggestion > built-in keywords > Other."""
    return (
        await ctx.expenses.learned_category(description)
        or (await ctx.expenses.category_by_name(suggested) if suggested else None)
        or await ctx.expenses.keyword_category(description)
        or await ctx.expenses.other()
    )


async def save_expense_draft(ctx: ToolContext, draft: ExpenseDraft) -> ToolOutcome:
    """Store a fully resolved draft, record it for ↩️ Undo and describe it."""
    saved = await ctx.expenses.add(draft, ctx.now)
    saved = await ctx.expenses.by_ids([e.id for e in saved])
    summary = "; ".join(f"#{e.id} {e.description} {e.amount:,}" for e in saved)
    action = await ctx.actions.record(
        "expenses_added", {"ids": [e.id for e in saved]}, f"added expenses: {summary}"
    )
    return ToolOutcome(
        result={
            "saved": [expense_info(e, ctx) for e in saved],
            "total": sum(e.amount for e in saved),
        },
        card=Card("expenses_saved", action.id, {"ids": [e.id for e in saved]}),
        note=f"[done: expenses added — {summary}]",
    )


# --- add_expenses ---


class ExpenseItemArgs(Args):
    description: str = ""
    amount_text: str
    quantity: float | None = None
    unit: str | None = None
    category: str | None = None


class AddExpensesArgs(Args):
    items: list[ExpenseItemArgs] = Field(min_length=1, max_length=30)
    date: str | None = None


async def add_expenses(args: AddExpensesArgs, ctx: ToolContext) -> ToolOutcome:
    spent_on = parse_date_arg(args.date, ctx.today, prefer_past=True) if args.date else None
    if args.date and spent_on is None:
        raise ToolError(f"could not understand date {args.date!r}", "use YYYY-MM-DD")
    if spent_on and spent_on > ctx.today:
        raise ToolError("expenses can't be in the future", "use today or a past date")

    draft = ExpenseDraft(
        raw=ctx.user_text,
        spent_on=spent_on.isoformat() if spent_on and spent_on != ctx.today else None,
    )
    problems = []
    for n, item in enumerate(args.items, 1):
        amount = parse_amount_text(item.amount_text)
        if amount is None:
            problems.append(f"item {n} ({item.description}): no amount in {item.amount_text!r}")
            continue
        entry = DraftItem(
            description=item.description.strip(), quantity=item.quantity, unit=item.unit
        )
        entry.set_amount(amount.value, amount.ambiguous, amount.currency, ctx.config.currency)
        entry.category_id = (await _category(ctx, entry.description, item.category)).id
        draft.items.append(entry)
    if problems:
        raise ToolError("; ".join(problems), AMOUNT_HINT)

    if any(item.ambiguous for item in draft.items):
        unclear = [f"{i.description} ({i.raw_amount:g})" for i in draft.items if i.ambiguous]
        return ToolOutcome(
            result={
                "status": "waiting_for_user",
                "asking": f"thousand or million for: {', '.join(unclear)}",
                "hint": "The app is showing buttons; don't ask again and don't save anything.",
            },
            clarification=Clarification("amount_scale", draft.to_dict()),
            note=f"[asked: thousand or million for {', '.join(unclear)}]",
        )
    return await save_expense_draft(ctx, draft)


# --- list_expenses ---


class ListExpensesArgs(Args):
    period: str = "recent"
    query: str | None = None


async def list_expenses(args: ListExpensesArgs, ctx: ToolContext) -> ToolOutcome:
    start, end = period_dates(args.period, ctx.today, ctx.calendar)
    if args.query:
        _, items = await ctx.expenses.search(args.query, start, end)
    else:
        items = await ctx.expenses.between(start, end)
    return ToolOutcome(
        result={
            "period": {"from": start.isoformat(), "to_exclusive": end.isoformat()},
            "count": len(items),
            "total": sum(e.amount for e in items),
            "expenses": [expense_info(e, ctx) for e in items[:40]],
        }
    )


# --- update_expense ---


class UpdateExpenseArgs(Args):
    id: int
    amount_text: str | None = None
    description: str | None = None
    category: str | None = None
    date: str | None = None


async def update_expense(args: UpdateExpenseArgs, ctx: ToolContext) -> ToolOutcome:
    expense = await ctx.expenses.get(args.id)
    if expense is None:
        raise ToolError(f"expense #{args.id} not found", "use list_expenses to find the id")
    amount: int | None = None
    if args.amount_text:
        found = parse_amount_text(args.amount_text)
        if found is None:
            raise ToolError(f"no amount in {args.amount_text!r}", AMOUNT_HINT)
        if found.ambiguous:
            raise ToolError(
                f"{args.amount_text!r} is ambiguous",
                "ask the user whether it is thousand or million, then call again",
            )
        item = DraftItem(description=expense.description)
        item.set_amount(found.value, False, found.currency, ctx.config.currency)
        amount = item.amount
    category_id = None
    if args.category:
        category = await ctx.expenses.category_by_name(args.category)
        if category is None:
            names = ", ".join(c.name for c in await ctx.expenses.categories())
            raise ToolError(f"unknown category {args.category!r}", f"use one of: {names}")
        category_id = category.id
    spent_on: date | None = None
    if args.date:
        spent_on = parse_date_arg(args.date, ctx.today, prefer_past=True)
        if spent_on is None or spent_on > ctx.today:
            raise ToolError(f"invalid date {args.date!r}", "use a past YYYY-MM-DD")
    changed = await ctx.expenses.update(
        expense.id,
        amount=amount,
        description=args.description,
        category_id=category_id,
        spent_on=spent_on.isoformat() if spent_on else None,
        now=ctx.now,
    )
    assert changed is not None
    updated, previous = changed
    if category_id is not None:
        await ctx.expenses.learn(updated.description, category_id)  # remember the correction
    summary = f"#{updated.id} {updated.description} {updated.amount:,} ({updated.category.name})"
    action = await ctx.actions.record(
        "expense_updated", {"previous": previous}, f"updated expense {summary}"
    )
    return ToolOutcome(
        result={"updated": expense_info(updated, ctx)},
        card=Card("expense_updated", action.id, {"id": updated.id}),
        note=f"[done: expense updated — {summary}]",
    )


# --- delete_expenses ---


class DeleteExpensesArgs(Args):
    ids: list[int] = Field(default_factory=list)
    query: str | None = None
    period: str = "recent"


async def delete_expenses(args: DeleteExpensesArgs, ctx: ToolContext) -> ToolOutcome:
    if args.ids:
        targets = await ctx.expenses.by_ids(args.ids)
        missing = set(args.ids) - {e.id for e in targets}
        if missing:
            raise ToolError(f"expenses not found: {sorted(missing)}", "use list_expenses")
    elif args.query:
        start, end = period_dates(args.period, ctx.today, ctx.calendar)
        best, matches = await ctx.expenses.search(args.query, start, end)
        if best is None:
            if not matches:
                raise ToolError(f"no expense matches {args.query!r}", "use list_expenses")
            return ToolOutcome(
                result={
                    "status": "several_match",
                    "candidates": [expense_info(e, ctx) for e in matches[:10]],
                    "hint": "ask the user which one(s), then call again with ids",
                }
            )
        targets = [best]
    else:
        raise ToolError("give ids or a query", "use ids from [done: …] notes or list_expenses")

    rows = [ctx.expenses.to_row(e) for e in targets]
    info = [expense_info(e, ctx) for e in targets]
    await ctx.expenses.delete([e.id for e in targets])
    summary = "; ".join(f"#{i['id']} {i['description']} {i['amount']:,}" for i in info)
    action = await ctx.actions.record(
        "expenses_deleted", {"rows": rows}, f"deleted expenses: {summary}"
    )
    return ToolOutcome(
        result={"deleted": info},
        card=Card("expenses_deleted", action.id, {"items": info}),
        note=f"[done: expenses deleted — {summary}]",
    )


# --- Schemas ---

EXPENSE_TOOLS = [
    Tool(
        name="add_expenses",
        description=(
            "Record money the user spent. Put every item of the message in one call. "
            "Copy each amount exactly as written."
        ),
        parameters={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "What was bought, user's language, no amount",
                            },
                            "amount_text": {
                                "type": "string",
                                "description": "Amount exactly as written, e.g. '۱۵۰ هزار تومن'",
                            },
                            "quantity": {"type": "number"},
                            "unit": {"type": "string", "description": "e.g. L, kg, pcs"},
                            "category": {"type": "string"},
                        },
                        "required": ["description", "amount_text"],
                    },
                },
                "date": {
                    "type": "string",
                    "description": "YYYY-MM-DD, only if the user named a day",
                },
            },
            "required": ["items"],
        },
        args_model=AddExpensesArgs,
        handler=add_expenses,
    ),
    Tool(
        name="list_expenses",
        description="Find recorded expenses (ids, amounts, categories) to answer or to edit.",
        parameters={
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": PERIOD_ENUM},
                "query": {"type": "string", "description": "Words to look for, e.g. 'ماست'"},
            },
        },
        args_model=ListExpensesArgs,
        handler=list_expenses,
    ),
    Tool(
        name="update_expense",
        description="Change an expense's amount, description, category or date.",
        parameters={
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "amount_text": {"type": "string", "description": "New amount as written"},
                "description": {"type": "string"},
                "category": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["id"],
        },
        args_model=UpdateExpenseArgs,
        handler=update_expense,
    ),
    Tool(
        name="delete_expenses",
        description="Delete expenses by ids, or by a short query when the user names one.",
        parameters={
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "integer"}},
                "query": {"type": "string"},
                "period": {"type": "string", "enum": PERIOD_ENUM},
            },
        },
        args_model=DeleteExpensesArgs,
        handler=delete_expenses,
    ),
]
