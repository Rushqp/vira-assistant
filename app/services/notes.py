"""Notes: save with a title and tags, search, pin, edit, delete (and restore for ↩️ Undo)."""

import re
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.normalizer import normalize
from app.core.textmatch import best_match
from app.db.models import Note, utcnow

MAX_TAGS = 5
MAX_TAG_LENGTH = 30
MAX_TITLE = 120
_TAG_SEPARATORS = re.compile(r"[\s,،]+")


def clean_tags(tags: Iterable[str]) -> list[str]:
    """«#لیست خرید», "Car" → ["لیست_خرید", "car"]: no "#", one word each, no duplicates."""
    result: list[str] = []
    for tag in tags:
        word = "_".join(_TAG_SEPARATORS.split(normalize(str(tag)).strip().lstrip("#").strip()))
        word = word.strip("_")[:MAX_TAG_LENGTH]
        if word and word not in result:
            result.append(word)
    return result[:MAX_TAGS]


def tag_list(note: Note) -> list[str]:
    return [t for t in note.tags.split() if t]


def short_title(text: str, limit: int = 60) -> str:
    """The first line of a text, shortened at a word boundary."""
    first = text.strip().splitlines()[0] if text.strip() else ""
    if len(first) <= limit:
        return first
    cut = first[:limit].rsplit(" ", 1)[0]
    return (cut or first[:limit]) + "…"


class NoteService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        text: str,
        title: str = "",
        tags: Iterable[str] = (),
        summary: str | None = None,
        source: str = "text",
        pinned: bool = False,
    ) -> Note:
        note = Note(
            text=text.strip(),
            title=(title.strip() or short_title(text))[:MAX_TITLE],
            tags=" ".join(clean_tags(tags)),
            summary=summary.strip() if summary and summary.strip() else None,
            source=source,
            pinned=pinned,
        )
        self.session.add(note)
        await self.session.commit()
        return note

    async def get(self, note_id: int) -> Note | None:
        return await self.session.get(Note, note_id)

    async def by_ids(self, note_ids: list[int]) -> list[Note]:
        rows = await self.session.scalars(
            select(Note).where(Note.id.in_(note_ids)).order_by(Note.id)
        )
        return list(rows.all())

    async def recent(self, limit: int = 10, offset: int = 0) -> list[Note]:
        """Pinned notes first, then the newest."""
        rows = await self.session.scalars(
            select(Note)
            .order_by(Note.pinned.desc(), Note.created_at.desc(), Note.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.all())

    async def count(self) -> int:
        return int(await self.session.scalar(select(func.count(Note.id))) or 0)

    async def all(self) -> list[Note]:
        rows = await self.session.scalars(select(Note).order_by(Note.id))
        return list(rows.all())

    async def search(self, query: str) -> tuple[Note | None, list[Note]]:
        """(the single clear match, all matches best first) by title, tags, summary and text.
        `#tag` looks for that tag only."""
        notes = await self.all()
        if query.strip().startswith("#"):
            wanted = clean_tags([query])
            matches = [n for n in notes if wanted and wanted[0] in tag_list(n)]
            matches.sort(key=lambda n: n.created_at, reverse=True)
            return (matches[0] if len(matches) == 1 else None), matches
        return best_match(
            notes,
            query,
            key=lambda n: f"{n.title} {n.tags.replace('_', ' ')} {n.summary or ''} {n.text}",
        )

    async def update(
        self,
        note_id: int,
        *,
        text: str | None = None,
        title: str | None = None,
        tags: Iterable[str] | None = None,
        summary: str | None = None,
        pinned: bool | None = None,
    ) -> tuple[Note, dict] | None:
        """Change fields of a note. Returns (note, previous row) for ↩️ Undo."""
        note = await self.get(note_id)
        if note is None:
            return None
        previous = self.to_row(note)
        if text is not None:
            note.text = text.strip()
        if title is not None:
            note.title = title.strip()[:MAX_TITLE]
        if tags is not None:
            note.tags = " ".join(clean_tags(tags))
        if summary is not None:
            note.summary = summary.strip() or None
        if pinned is not None:
            note.pinned = pinned
        note.updated_at = utcnow()
        await self.session.commit()
        return note, previous

    async def delete(self, note_ids: list[int]) -> int:
        result = await self.session.execute(delete(Note).where(Note.id.in_(note_ids)))
        await self.session.commit()
        return result.rowcount or 0  # type: ignore[attr-defined]

    @staticmethod
    def to_row(note: Note) -> dict:
        return {
            "id": note.id,
            "title": note.title,
            "text": note.text,
            "summary": note.summary,
            "tags": note.tags,
            "pinned": note.pinned,
            "source": note.source,
            "created_at": note.created_at.isoformat(),
            "updated_at": note.updated_at.isoformat(),
        }

    async def restore(self, rows: list[dict]) -> list[Note]:
        """Put deleted notes back (same ids) or revert edited ones to `rows`."""
        restored = []
        for row in rows:
            values = {
                **row,
                "created_at": datetime.fromisoformat(row["created_at"]),
                "updated_at": datetime.fromisoformat(row["updated_at"]),
            }
            note = await self.get(row["id"])
            if note is None:
                note = Note(**values)
                self.session.add(note)
            else:
                for key, value in values.items():
                    setattr(note, key, value)
            restored.append(note)
        await self.session.commit()
        return restored
