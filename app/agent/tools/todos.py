"""To-do tools: add (several at once, for a day), list, update (done / text / day), delete.

A task without a time and without "remind me" is a to-do; with a time or a reminder request it
is a reminder (system prompt). Unfinished tasks of earlier days stay in today's list.
"""

from pydantic import Field

from app.agent.tools import Args, Card, Tool, ToolContext, ToolError, ToolOutcome
from app.agent.tools.common import jalali, parse_date_arg
from app.db.models import Todo


def todo_info(todo: Todo, ctx: ToolContext) -> dict:
    return {
        "id": todo.id,
        "text": todo.text,
        "day": todo.due_date.isoformat(),
        "day_jalali": jalali(todo.due_date),
        "done": todo.done,
        "carried_over": not todo.done and todo.due_date < ctx.today,
    }


def _day(text: str | None, ctx: ToolContext):
    if not text:
        return ctx.today
    day = parse_date_arg(text, ctx.today)
    if day is None:
        raise ToolError(f"could not understand the day {text!r}", "e.g. '2026-10-06', 'فردا'")
    return day


async def _targets(ctx: ToolContext, ids: list[int], query: str | None) -> list[Todo] | ToolOutcome:
    """The tasks the user means, or an outcome listing the candidates."""
    if ids:
        todos = await ctx.todos.by_ids(ids)
        missing = set(ids) - {t.id for t in todos}
        if missing:
            raise ToolError(f"to-dos not found: {sorted(missing)}", "use list_todos")
        return todos
    if not query:
        raise ToolError("give ids or a query", "use ids from [done: …] notes or list_todos")
    best, matches = await ctx.todos.search(query, ctx.today)
    if best is not None:
        return [best]
    if not matches:
        raise ToolError(f"no to-do matches {query!r}", "use list_todos")
    return ToolOutcome(
        result={
            "status": "several_match",
            "candidates": [todo_info(t, ctx) for t in matches[:10]],
            "hint": "ask the user which one(s), then call again with ids",
        }
    )


# --- add_todos ---


class AddTodosArgs(Args):
    items: list[str] = Field(min_length=1)
    date: str | None = None


async def add_todos(args: AddTodosArgs, ctx: ToolContext) -> ToolOutcome:
    day = _day(args.date, ctx)
    if day < ctx.today:
        raise ToolError("that day is in the past", "to-dos are for today or a later day")
    todos = await ctx.todos.add(args.items, day)
    if not todos:
        raise ToolError("no tasks given", "items: one short task each")
    summary = "; ".join(f"#{t.id} {t.text}" for t in todos)
    action = await ctx.actions.record(
        "todos_added", {"ids": [t.id for t in todos]}, f"to-dos for {day}: {summary}"
    )
    return ToolOutcome(
        result={"added": [todo_info(t, ctx) for t in todos], "day": day.isoformat()},
        card=Card("todos_added", action.id, {"ids": [t.id for t in todos]}),
        note=f"[done: to-dos added for {day.isoformat()} — {summary}]",
    )


# --- list_todos ---


class ListTodosArgs(Args):
    date: str | None = None


async def list_todos(args: ListTodosArgs, ctx: ToolContext) -> ToolOutcome:
    day = _day(args.date, ctx)
    day_list = await ctx.todos.day_list(day, ctx.today)
    return ToolOutcome(
        result={
            "day": day.isoformat(),
            "todos": [todo_info(t, ctx) for t in day_list.items],
            "shown_to_user": True,
        },
        card=Card("todos_list", None, {"day": day.isoformat()}),
    )


# --- update_todos ---


class UpdateTodosArgs(Args):
    ids: list[int] = Field(default_factory=list)
    query: str | None = None
    done: bool | None = None
    text: str | None = None
    date: str | None = None


async def update_todos(args: UpdateTodosArgs, ctx: ToolContext) -> ToolOutcome:
    if args.done is None and not args.text and not args.date:
        raise ToolError("nothing to change", "set done, text or date")
    targets = await _targets(ctx, args.ids, args.query)
    if isinstance(targets, ToolOutcome):
        return targets
    if args.text and len(targets) > 1:
        raise ToolError("a new text needs exactly one to-do", "call once per to-do")
    day = _day(args.date, ctx) if args.date else None
    rows = [ctx.todos.to_row(t) for t in targets]
    ids = [t.id for t in targets]
    if args.done is not None:
        await ctx.todos.set_done(ids, args.done)
    for todo in targets:
        if args.text or day:
            await ctx.todos.update(todo.id, text=args.text, day=day)
    updated = await ctx.todos.by_ids(ids)
    summary = "; ".join(
        f"#{t.id} {t.text}{' ✓' if t.done else ''} ({t.due_date.isoformat()})" for t in updated
    )
    action = await ctx.actions.record("todos_updated", {"rows": rows}, f"to-dos: {summary}")
    return ToolOutcome(
        result={"updated": [todo_info(t, ctx) for t in updated]},
        card=Card("todos_updated", action.id, {"ids": ids}),
        note=f"[done: to-dos updated — {summary}]",
    )


# --- delete_todos ---


class DeleteTodosArgs(Args):
    ids: list[int] = Field(default_factory=list)
    query: str | None = None


async def delete_todos(args: DeleteTodosArgs, ctx: ToolContext) -> ToolOutcome:
    targets = await _targets(ctx, args.ids, args.query)
    if isinstance(targets, ToolOutcome):
        return targets
    rows = [ctx.todos.to_row(t) for t in targets]
    items = [t.text for t in targets]
    await ctx.todos.delete([t.id for t in targets])
    summary = "; ".join(f"#{t.id} {t.text}" for t in targets)
    action = await ctx.actions.record("todos_deleted", {"rows": rows}, f"deleted to-dos: {summary}")
    return ToolOutcome(
        result={"deleted": items},
        card=Card("todos_deleted", action.id, {"items": items}),
        note=f"[done: to-dos deleted — {summary}]",
    )


# --- Schemas ---

_IDS = {"type": "array", "items": {"type": "integer"}}
_QUERY = {"type": "string", "description": "words of the task, e.g. 'نون'"}

TODO_TOOLS = [
    Tool(
        name="add_todos",
        description=(
            "Add tasks to the user's to-do list for a day (default today). For things to do "
            "without a time; with a time or 'remind me' use create_reminder instead."
        ),
        parameters={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "one short task each, in the user's language",
                },
                "date": {"type": "string", "description": "YYYY-MM-DD, if not today"},
            },
            "required": ["items"],
        },
        args_model=AddTodosArgs,
        handler=add_todos,
    ),
    Tool(
        name="list_todos",
        description="Show the to-do list of a day (default today, with unfinished earlier ones).",
        parameters={
            "type": "object",
            "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"}},
        },
        args_model=ListTodosArgs,
        handler=list_todos,
    ),
    Tool(
        name="update_todos",
        description=(
            "Tick to-dos as done (or not done), rename one, or move them to another day "
            "(e.g. «نون رو خریدم» → done)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "ids": _IDS,
                "query": _QUERY,
                "done": {"type": "boolean"},
                "text": {"type": "string"},
                "date": {"type": "string", "description": "new day, YYYY-MM-DD"},
            },
        },
        args_model=UpdateTodosArgs,
        handler=update_todos,
    ),
    Tool(
        name="delete_todos",
        description="Delete to-dos by ids, or by a short query when the user names one.",
        parameters={"type": "object", "properties": {"ids": _IDS, "query": _QUERY}},
        args_model=DeleteTodosArgs,
        handler=delete_todos,
    ),
]
