"""Note tools: save (with a title, tags and, for long or voice notes, a summary), find, update,
delete.

`save_note` without `text` saves the user's whole message, so a long voice note is kept
word for word without the model copying it.
"""

from pydantic import Field

from app.agent.tools import Args, Card, Tool, ToolContext, ToolError, ToolOutcome
from app.agent.tools.common import jalali
from app.db.models import Note
from app.services.notes import tag_list
from app.services.reminders import from_utc

PREVIEW = 300  # characters of a note's text sent back to the model
FOUND_MAX = 10


def note_info(note: Note, ctx: ToolContext) -> dict:
    day = from_utc(note.created_at, ctx.config.timezone).date()
    text = note.text if len(note.text) <= PREVIEW else note.text[:PREVIEW] + "…"
    return {
        "id": note.id,
        "title": note.title,
        "tags": tag_list(note),
        "pinned": note.pinned,
        "date": day.isoformat(),
        "date_jalali": jalali(day),
        "summary": note.summary,
        "text": text,
    }


async def _target(ctx: ToolContext, note_id: int | None, query: str | None) -> Note | ToolOutcome:
    if note_id:
        note = await ctx.notes.get(note_id)
        if note is None:
            raise ToolError(f"no note #{note_id}", "use find_notes")
        return note
    if not query:
        raise ToolError("give an id or a query", "use ids from [done: …] notes or find_notes")
    best, matches = await ctx.notes.search(query)
    if best is not None:
        return best
    if not matches:
        raise ToolError(f"no note matches {query!r}", "use find_notes")
    return ToolOutcome(
        result={
            "status": "several_match",
            "candidates": [note_info(n, ctx) for n in matches[:FOUND_MAX]],
            "hint": "ask the user which one, then call again with its id",
        }
    )


# --- save_note ---


class SaveNoteArgs(Args):
    text: str | None = None
    title: str | None = None
    tags: list[str] = Field(default_factory=list)
    summary: str | None = None
    pinned: bool = False


async def save_note(args: SaveNoteArgs, ctx: ToolContext) -> ToolOutcome:
    text = (args.text or "").strip() or ctx.user_text.strip()
    if not text:
        raise ToolError("nothing to save")
    note = await ctx.notes.add(
        text,
        title=args.title or "",
        tags=args.tags,
        summary=args.summary,
        source="voice" if ctx.voice else "text",
        pinned=args.pinned,
    )
    action = await ctx.actions.record(
        "note_saved", {"id": note.id}, f"note #{note.id} saved: {note.title}"
    )
    return ToolOutcome(
        result={"saved": note_info(note, ctx)},
        card=Card("note_saved", action.id, {"id": note.id}),
        note=f"[done: note #{note.id} saved — {note.title}]",
    )


# --- find_notes ---


class FindNotesArgs(Args):
    query: str | None = None


async def find_notes(args: FindNotesArgs, ctx: ToolContext) -> ToolOutcome:
    if args.query and args.query.strip():
        _, notes = await ctx.notes.search(args.query)
    else:
        notes = await ctx.notes.recent(FOUND_MAX)
    notes = notes[:FOUND_MAX]
    if not notes:
        return ToolOutcome(result={"count": 0, "hint": "no note matches: tell the user"})
    return ToolOutcome(
        result={"count": len(notes), "notes": [note_info(n, ctx) for n in notes]},
        card=Card("notes_found", None, {"ids": [n.id for n in notes], "query": args.query or ""}),
    )


# --- update_note ---


class UpdateNoteArgs(Args):
    id: int | None = None
    query: str | None = None
    text: str | None = None
    append: str | None = None
    title: str | None = None
    tags: list[str] | None = None
    summary: str | None = None
    pinned: bool | None = None


async def update_note(args: UpdateNoteArgs, ctx: ToolContext) -> ToolOutcome:
    target = await _target(ctx, args.id, args.query)
    if isinstance(target, ToolOutcome):
        return target
    text = args.text
    if args.append:
        text = f"{(text or target.text).rstrip()}\n{args.append.strip()}"
    changes = (text, args.title, args.tags, args.summary, args.pinned)
    if all(value is None for value in changes):
        raise ToolError("nothing to change", "set text, append, title, tags, summary or pinned")
    changed = await ctx.notes.update(
        target.id,
        text=text,
        title=args.title,
        tags=args.tags,
        summary=args.summary,
        pinned=args.pinned,
    )
    assert changed is not None
    note, previous = changed
    action = await ctx.actions.record(
        "note_updated", {"previous": previous}, f"note #{note.id} updated: {note.title}"
    )
    return ToolOutcome(
        result={"updated": note_info(note, ctx)},
        card=Card("note_updated", action.id, {"id": note.id}),
        note=f"[done: note #{note.id} updated — {note.title}]",
    )


# --- delete_notes ---


class DeleteNotesArgs(Args):
    ids: list[int] = Field(default_factory=list)
    query: str | None = None


async def delete_notes(args: DeleteNotesArgs, ctx: ToolContext) -> ToolOutcome:
    if args.ids:
        notes = await ctx.notes.by_ids(args.ids)
        missing = set(args.ids) - {n.id for n in notes}
        if missing:
            raise ToolError(f"notes not found: {sorted(missing)}", "use find_notes")
    else:
        target = await _target(ctx, None, args.query)
        if isinstance(target, ToolOutcome):
            return target
        notes = [target]
    rows = [ctx.notes.to_row(n) for n in notes]
    titles = [n.title for n in notes]
    await ctx.notes.delete([n.id for n in notes])
    summary = "; ".join(f"#{n.id} {n.title}" for n in notes)
    action = await ctx.actions.record("notes_deleted", {"rows": rows}, f"deleted notes: {summary}")
    return ToolOutcome(
        result={"deleted": titles},
        card=Card("notes_deleted", action.id, {"items": titles}),
        note=f"[done: notes deleted — {summary}]",
    )


# --- Schemas ---

_TAGS = {
    "type": "array",
    "items": {"type": "string"},
    "description": "1-3 short tags in the user's language, e.g. ['خرید', 'ماشین']",
}

NOTE_TOOLS = [
    Tool(
        name="save_note",
        description=(
            "Save a note. Omit text to save the user's whole message word for word (long or "
            "voice notes). Always give a short title and 1-3 tags; add a 1-2 sentence summary "
            "for long notes."
        ),
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "the note; omit = the whole message"},
                "title": {"type": "string", "description": "a few words"},
                "tags": _TAGS,
                "summary": {"type": "string"},
                "pinned": {"type": "boolean"},
            },
            "required": ["title", "tags"],
        },
        args_model=SaveNoteArgs,
        handler=save_note,
    ),
    Tool(
        name="find_notes",
        description="Find notes by words or a #tag (empty = the latest notes); shown to the user.",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        args_model=FindNotesArgs,
        handler=find_notes,
    ),
    Tool(
        name="update_note",
        description="Change a note: replace or append text, title, tags, summary, pin / unpin.",
        parameters={
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "query": {"type": "string", "description": "words of the note, if no id"},
                "text": {"type": "string", "description": "the whole new text"},
                "append": {"type": "string", "description": "a line to add at the end"},
                "title": {"type": "string"},
                "tags": _TAGS,
                "summary": {"type": "string"},
                "pinned": {"type": "boolean"},
            },
        },
        args_model=UpdateNoteArgs,
        handler=update_note,
    ),
    Tool(
        name="delete_notes",
        description="Delete notes by ids, or by a short query when the user names one.",
        parameters={
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "integer"}},
                "query": {"type": "string"},
            },
        },
        args_model=DeleteNotesArgs,
        handler=delete_notes,
    ),
]
