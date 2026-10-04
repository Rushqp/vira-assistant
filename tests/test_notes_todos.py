"""To-dos and notes: the services and the agent tools (no model).

"Now" is Sunday 4 Oct 2026 10:00 Tehran (= 12 Mehr 1405).
"""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.agent.actions import ActionLog
from app.agent.tools import ToolContext, build_registry
from app.config import Calendar
from app.services.expenses import ExpenseService
from app.services.notes import NoteService, clean_tags, short_title
from app.services.reminders import ReminderService
from app.services.settings import SettingsService
from app.services.todos import TodoService

TZ = ZoneInfo("Asia/Tehran")
NOW = datetime(2026, 10, 4, 10, 0, tzinfo=TZ)
TODAY = NOW.date()
REGISTRY = build_registry()


@pytest.fixture
async def ctx(config, sessionmaker):
    async with sessionmaker() as session:
        settings = SettingsService(session, Calendar.JALALI)
        expenses = ExpenseService(session, TZ, "toman")
        reminders = ReminderService(session, TZ, config.day_times)
        yield ToolContext(
            config=config,
            calendar=Calendar.JALALI,
            now=NOW,
            user_text="(test)",
            expenses=expenses,
            reminders=reminders,
            settings=settings,
            actions=ActionLog(session, expenses, reminders, settings),
        )


async def call(ctx, name: str, **args):
    return await REGISTRY.execute(name, json.dumps(args, ensure_ascii=False), ctx)


# --- To-dos ---


async def test_unfinished_tasks_are_carried_to_today(ctx):
    todos: TodoService = ctx.todos
    [old, finished] = await todos.add(["قبض برق", "زنگ به مامان"], TODAY - timedelta(days=2))
    await todos.set_done([finished.id])
    [today_task] = await todos.add(["نون بخرم"], TODAY)
    await todos.add(["کتابخونه"], TODAY + timedelta(days=1))

    day = await todos.day_list(TODAY, TODAY)
    assert [t.text for t in day.carried] == ["قبض برق"]
    assert [t.text for t in day.planned] == ["نون بخرم"]
    tomorrow = await todos.day_list(TODAY + timedelta(days=1), TODAY)
    assert [t.text for t in tomorrow.items] == ["کتابخونه"]  # carried ones only show today
    past = await todos.day_list(TODAY - timedelta(days=2), TODAY)
    assert [(t.text, t.done) for t in past.items] == [("قبض برق", False), ("زنگ به مامان", True)]

    await todos.toggle(old.id)
    assert (await todos.day_list(TODAY, TODAY)).carried == []
    assert today_task.id in {t.id for t in (await todos.day_list(TODAY, TODAY)).open}


async def test_add_list_and_tick_todos(ctx):
    added = await call(ctx, "add_todos", items=["نون بخرم", "قبض برق رو بدم"], date="فردا")
    assert added.result["day"] == "2026-10-05" and len(added.result["added"]) == 2
    assert added.card.kind == "todos_added" and "[done: to-dos added" in added.note

    past = await call(ctx, "add_todos", items=["x"], date="دیروز")
    assert "past" in past.result["error"]

    listed = await call(ctx, "list_todos", date="2026-10-05")
    assert [t["text"] for t in listed.result["todos"]] == ["نون بخرم", "قبض برق رو بدم"]
    assert listed.card.kind == "todos_list"

    done = await call(ctx, "update_todos", query="نون", done=True)
    assert done.result["updated"][0]["done"] is True
    await ctx.actions.undo(done.card.action_id)  # ↩️ Undo: not done again
    assert not (await ctx.todos.by_ids([done.result["updated"][0]["id"]]))[0].done


async def test_move_rename_and_delete_todos(ctx):
    await call(ctx, "add_todos", items=["خرید هدیه", "خرید شیر"])
    several = await call(ctx, "update_todos", query="خرید", done=True)
    assert several.result["status"] == "several_match" and len(several.result["candidates"]) == 2

    ids = [c["id"] for c in several.result["candidates"]]
    moved = await call(ctx, "update_todos", ids=ids, date="2026-10-06")
    assert {t["day"] for t in moved.result["updated"]} == {"2026-10-06"}
    renamed = await call(ctx, "update_todos", ids=ids, text="x")
    assert "exactly one" in renamed.result["error"]

    deleted = await call(ctx, "delete_todos", ids=ids)
    assert deleted.result["deleted"] == ["خرید هدیه", "خرید شیر"]
    await ctx.actions.undo(deleted.card.action_id)
    assert len(await ctx.todos.by_ids(ids)) == 2


# --- Notes ---


def test_tags_and_titles():
    assert clean_tags(["#خرید", "لیست خرید", "Car", "car", ""]) == ["خرید", "لیست_خرید", "car"]
    assert short_title("رمز وای‌فای مهمون\nخط دوم") == "رمز وای‌فای مهمون"
    assert short_title("x " * 50).endswith("…")


async def test_note_search_by_words_and_tags(ctx):
    notes: NoteService = ctx.notes
    await notes.add("روغن ماشین رو هر ۵۰۰۰ کیلومتر عوض کن", "سرویس ماشین", ["ماشین"])
    await notes.add("رمز وای‌فای: 1234", "رمز وای‌فای", ["رمز", "خانه"], pinned=True)
    best, _ = await notes.search("روغن ماشین")
    assert best is not None and best.title == "سرویس ماشین"
    _, tagged = await notes.search("#خانه")
    assert [n.title for n in tagged] == ["رمز وای‌فای"]
    assert (await notes.recent())[0].title == "رمز وای‌فای"  # pinned first


async def test_save_note_keeps_the_whole_message(ctx):
    ctx.user_text = "امروز جلسه با علی بود. قرار شد گزارش رو تا شنبه بفرستم و بودجه رو هم ببینیم."
    ctx.voice = True
    saved = await call(ctx, "save_note", title="جلسه با علی", tags=["کار"], summary="گزارش تا شنبه")
    note = await ctx.notes.get(saved.result["saved"]["id"])
    assert note.text == ctx.user_text and note.source == "voice" and note.summary == "گزارش تا شنبه"
    assert saved.card.kind == "note_saved"

    await ctx.actions.undo(saved.card.action_id)  # ↩️ Undo deletes it
    assert await ctx.notes.get(note.id) is None


async def test_find_update_and_delete_notes(ctx):
    await call(ctx, "save_note", text="شیر، نون", title="لیست خرید", tags=["خرید"])
    found = await call(ctx, "find_notes", query="خرید")
    assert found.result["count"] == 1 and found.card.kind == "notes_found"
    none = await call(ctx, "find_notes", query="هواپیما")
    assert none.card is None and none.result["count"] == 0

    updated = await call(ctx, "update_note", query="لیست خرید", append="تخم‌مرغ", pinned=True)
    note = await ctx.notes.get(updated.result["updated"]["id"])
    assert note.text == "شیر، نون\nتخم‌مرغ" and note.pinned
    await ctx.actions.undo(updated.card.action_id)
    note = await ctx.notes.get(note.id)
    assert note.text == "شیر، نون" and not note.pinned

    deleted = await call(ctx, "delete_notes", query="لیست خرید")
    assert deleted.result["deleted"] == ["لیست خرید"]
    await ctx.actions.undo(deleted.card.action_id)
    assert (await ctx.notes.get(note.id)).title == "لیست خرید"


async def test_note_tools_need_something(ctx):
    nothing = await call(ctx, "update_note", query="x")
    assert "no note" in nothing.result["error"]
    ctx.user_text = "  "
    empty = await call(ctx, "save_note", title="t", tags=[])
    assert "nothing to save" in empty.result["error"]
