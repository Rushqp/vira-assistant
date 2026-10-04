"""To-dos: a list per day. Unfinished tasks of earlier days stay in today's list (carried over,
shown with their original day) until they are done or deleted."""

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.textmatch import best_match
from app.db.models import Todo, utcnow


@dataclass
class DayList:
    day: date
    carried: list[Todo] = field(default_factory=list)  # unfinished, from earlier days
    planned: list[Todo] = field(default_factory=list)  # this day's tasks (done or not)

    @property
    def items(self) -> list[Todo]:
        return [*self.carried, *self.planned]

    @property
    def open(self) -> list[Todo]:
        return [t for t in self.items if not t.done]

    @property
    def done(self) -> list[Todo]:
        return [t for t in self.items if t.done]


class TodoService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, texts: list[str], day: date) -> list[Todo]:
        todos = [Todo(text=text.strip(), due_date=day) for text in texts if text.strip()]
        self.session.add_all(todos)
        await self.session.commit()
        return todos

    async def get(self, todo_id: int) -> Todo | None:
        return await self.session.get(Todo, todo_id)

    async def by_ids(self, todo_ids: list[int]) -> list[Todo]:
        rows = await self.session.scalars(
            select(Todo).where(Todo.id.in_(todo_ids)).order_by(Todo.id)
        )
        return list(rows.all())

    async def day_list(self, day: date, today: date) -> DayList:
        """Tasks of `day`; today's list also carries the unfinished tasks of earlier days."""
        query = select(Todo).order_by(Todo.due_date, Todo.id)
        if day == today:
            carried = (Todo.due_date < day) & Todo.done_at.is_(None)
            query = query.where(or_(Todo.due_date == day, carried))
        else:
            query = query.where(Todo.due_date == day)
        todos = list((await self.session.scalars(query)).all())
        return DayList(
            day,
            carried=[t for t in todos if t.due_date < day],
            planned=[t for t in todos if t.due_date == day],
        )

    async def open_items(self) -> list[Todo]:
        """Every unfinished task: carried ones, today's and later days' (to find references)."""
        rows = await self.session.scalars(
            select(Todo).where(Todo.done_at.is_(None)).order_by(Todo.due_date, Todo.id)
        )
        return list(rows.all())

    async def search(self, query: str, today: date) -> tuple[Todo | None, list[Todo]]:
        """Among unfinished tasks first, then today's done ones (to undo a tick)."""
        best, matches = best_match(await self.open_items(), query, key=lambda t: t.text)
        if matches:
            return best, matches
        done_today = [t for t in (await self.day_list(today, today)).done]
        return best_match(done_today, query, key=lambda t: t.text)

    async def set_done(self, todo_ids: list[int], done: bool = True) -> list[Todo]:
        todos = await self.by_ids(todo_ids)
        for todo in todos:
            todo.done_at = (todo.done_at or utcnow()) if done else None
        await self.session.commit()
        return todos

    async def toggle(self, todo_id: int) -> Todo | None:
        todo = await self.get(todo_id)
        if todo is None:
            return None
        todo.done_at = None if todo.done else utcnow()
        await self.session.commit()
        return todo

    async def update(
        self, todo_id: int, *, text: str | None = None, day: date | None = None
    ) -> Todo | None:
        todo = await self.get(todo_id)
        if todo is None:
            return None
        if text is not None and text.strip():
            todo.text = text.strip()
        if day is not None:
            todo.due_date = day
        await self.session.commit()
        return todo

    async def delete(self, todo_ids: list[int]) -> int:
        result = await self.session.execute(delete(Todo).where(Todo.id.in_(todo_ids)))
        await self.session.commit()
        return result.rowcount or 0  # type: ignore[attr-defined]

    @staticmethod
    def to_row(todo: Todo) -> dict:
        return {
            "id": todo.id,
            "text": todo.text,
            "due_date": todo.due_date.isoformat(),
            "done_at": todo.done_at.isoformat() if todo.done_at else None,
            "created_at": todo.created_at.isoformat(),
        }

    async def restore(self, rows: list[dict]) -> list[Todo]:
        """Put deleted tasks back (same ids) or revert changed ones to `rows`."""
        restored = []
        for row in rows:
            values = {
                **row,
                "due_date": date.fromisoformat(row["due_date"]),
                "done_at": datetime.fromisoformat(row["done_at"]) if row["done_at"] else None,
                "created_at": datetime.fromisoformat(row["created_at"]),
            }
            todo = await self.get(row["id"])
            if todo is None:
                todo = Todo(**values)
                self.session.add(todo)
            else:
                for key, value in values.items():
                    setattr(todo, key, value)
            restored.append(todo)
        await self.session.commit()
        return restored
