"""v0.7 through the real dispatcher: ✅ To-dos, 📝 Notes, agent cards, 💾 backup and restore,
and to-dos in the morning briefing / nightly report."""

import io
import zipfile
from datetime import datetime, time
from zoneinfo import ZoneInfo

from aiogram.types import Chat, Document, Message, User

from app import texts
from app.bot.keyboards.inline import BackupCb
from app.config import Calendar
from app.scheduler import jobs
from app.services.notes import NoteService
from app.services.reminders import to_utc
from app.services.settings import SettingsService
from app.services.todos import TodoService
from app.utils.calendar import now_local
from tests.fakes import OWNER_ID, FakeSTT, calls, make_env, reply, tool, voice_message
from tests.test_reminders import FakeBot

TZ = ZoneInfo("Asia/Tehran")


def today():
    return now_local(TZ).date()


async def add_todos(env, *items: str, day=None) -> list:
    async with env.db() as session:
        return await TodoService(session).add(list(items), day or today())


async def add_note(env, text: str, title: str, tags=(), pinned=False):
    async with env.db() as session:
        return await NoteService(session).add(text, title, tags, pinned=pinned)


def buttons(env) -> list[str]:
    return [b.text for row in env.session.markup.inline_keyboard for b in row]


def document_message(file_id: str, name: str) -> Message:
    return Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=OWNER_ID, type="private"),
        from_user=User(id=OWNER_ID, is_bot=False, first_name="T"),
        document=Document(file_id=file_id, file_unique_id=file_id, file_name=name),
    )


# --- ✅ To-dos ---


async def test_todo_list_and_ticking(env):
    await env.send(texts.BTN_TODOS)
    assert texts.TODOS_EMPTY in env.session.sent[-1]

    await add_todos(env, "نون بخرم", "قبض برق")
    await env.send(texts.BTN_TODOS)
    assert "☐ نون بخرم" in env.session.sent[-1] and "0 of 2 done" in env.session.sent[-1]
    await env.press(env.button("نون بخرم"))
    assert "☑ <s>نون بخرم</s>" in env.session.edits[-1] and env.session.alerts[-1] == "☑"
    assert "☑ نون بخرم" in buttons(env)

    await env.press(env.button(texts.BTN_NEXT_DAY))  # tomorrow: nothing yet
    assert texts.TODOS_EMPTY in env.session.edits[-1]
    assert texts.BTN_TODAY in buttons(env)


async def test_add_button_sends_tasks_to_the_agent(env):
    await env.send(texts.BTN_TODOS)
    await env.press(env.button(texts.BTN_TODO_ADD))
    env.llm.script = [calls(tool("add_todos", items=["شیر بخرم"])), reply("")]
    await env.send("شیر بخرم")
    user = env.llm.respond_calls[0][-1]["content"]
    assert "➕ Add on the to-do list" in user
    assert "☐ شیر بخرم" in env.session.sent[-1]  # the card, with ↩️ Undo
    await env.press(env.button("Undo"))
    async with env.db() as session:
        assert (await TodoService(session).day_list(today(), today())).items == []


async def test_add_button_without_a_model(env):
    await env.send(texts.BTN_TODOS)
    await env.press(env.button(texts.BTN_TODO_ADD))
    await env.send("نون بخرم\nقبض برق رو بدم")  # no model can use tools: one task per line
    async with env.db() as session:
        day = await TodoService(session).day_list(today(), today())
    assert [t.text for t in day.items] == ["نون بخرم", "قبض برق رو بدم"]


async def test_agent_ticks_a_todo(env):
    await add_todos(env, "نون بخرم")
    env.llm.script = [calls(tool("update_todos", query="نون", done=True)), reply("")]
    await env.send("نون رو خریدم")
    assert "☑ <s>نون بخرم</s>" in env.session.sent[-1]


# --- 📝 Notes ---


async def test_notes_list_open_pin_and_delete(env):
    await env.send(texts.BTN_NOTES)
    assert texts.NOTES_EMPTY in env.session.sent[-1]

    await add_note(env, "شیر، نون", "لیست خرید", ["خرید"])
    await add_note(env, "رمز: 1234", "رمز وای‌فای", ["رمز"])
    await env.send(texts.BTN_NOTES)
    listing = env.session.sent[-1]
    assert "<b>رمز وای‌فای</b> #رمز" in listing and "Notes</b> (2)" in listing

    await env.press(env.button("لیست خرید"))
    assert "شیر، نون" in env.session.edits[-1] and "#خرید" in env.session.edits[-1]
    await env.press(env.button(texts.BTN_NOTE_PIN))
    assert env.session.alerts[-1] == texts.NOTE_PINNED and " 📌" in env.session.edits[-1]

    await env.press(env.button(texts.BTN_DELETE))
    assert "لیست خرید" in env.session.edits[-1]
    await env.press(env.button(texts.BTN_YES_DELETE))
    assert env.session.alerts[-1] == texts.NOTE_DELETED
    assert "Notes</b> (1)" in env.session.edits[-1]


async def test_edit_note_through_the_agent(env):
    note = await add_note(env, "شیر", "لیست خرید")
    await env.send(texts.BTN_NOTES)
    await env.press(env.button("لیست خرید"))
    await env.press(env.button(texts.BTN_EDIT))
    assert env.session.sent[-1] == texts.NOTE_EDIT_PROMPT
    env.llm.script = [calls(tool("update_note", id=note.id, append="نون")), reply("")]
    await env.send("نون رو هم اضافه کن")
    assert f"note #{note.id}" in env.llm.respond_calls[0][-1]["content"]
    assert "Note updated" in env.session.sent[-1] and "نون" in env.session.sent[-1]


async def test_long_voice_note_is_saved_word_for_word(config, sessionmaker):
    transcript = "فکرهای امروز: باید برای سفر شمال برنامه بریزیم و بودجه رو حساب کنیم."
    env = make_env(config, sessionmaker, stt=FakeSTT(transcript))
    env.llm.script = [
        calls(tool("save_note", title="برنامه سفر", tags=["سفر"], summary="برنامه و بودجه سفر")),
        reply("به‌عنوان یادداشت ذخیره شد."),
    ]
    await env.feed(voice_message(duration=95))
    assert "(1 min 35 s)" in env.llm.respond_calls[0][-1]["content"]
    async with env.db() as session:
        [note] = await NoteService(session).recent()
    assert (note.text, note.source, note.summary) == (transcript, "voice", "برنامه و بودجه سفر")
    assert "برنامه سفر" in env.session.sent[-1] and "Summary" in env.session.sent[-1]  # the card


# --- 💾 Backup and restore ---


async def test_backup_and_restore(env):
    await add_note(env, "رمز: 1234", "رمز وای‌فای")
    await env.send("/backup")
    [(name, content, caption)] = env.session.documents
    assert name.startswith("vira-backup-") and name.endswith(".zip") and "1 notes" in caption
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert {"vira.db", "backup.json"} <= set(archive.namelist())

    async with env.db() as session:  # the data changes after the backup
        notes = NoteService(session)
        await notes.delete([n.id for n in await notes.recent()])
        await notes.add("بعداً", "یادداشت بعدی")

    env.session.files["backup-file"] = content
    await env.feed(document_message("backup-file", name))
    assert "Restore this backup?" in env.session.sent[-1] and "1 notes" in env.session.sent[-1]
    await env.press(BackupCb(action="restore").pack())
    assert env.session.documents[-1][2] == texts.BACKUP_BEFORE_RESTORE  # current data first
    assert env.session.edits[-1].startswith("✅ Restored.")
    async with env.db() as session:
        assert [n.title for n in await NoteService(session).recent()] == ["رمز وای‌فای"]

    await env.press(BackupCb(action="restore").pack())  # the request is used up
    assert env.session.alerts[-1] == texts.RESTORE_EXPIRED


async def test_restore_refuses_other_files(env):
    env.session.files["junk"] = b"PK not really a zip"
    await env.feed(document_message("junk", "photos.zip"))
    assert env.session.sent[-1].startswith("This file isn't a Vira backup")


async def test_restore_can_be_cancelled(env):
    await env.send("/backup")
    env.session.files["b"] = env.session.documents[0][1]
    await env.feed(document_message("b", "vira-backup.zip"))
    await env.press(BackupCb(action="cancel").pack())
    assert env.session.edits[-1] == texts.RESTORE_CANCELLED


async def test_backup_screen_in_settings(env):
    await env.send(texts.BTN_SETTINGS)
    await env.press(env.button(texts.BTN_BACKUP))
    assert "Weekly copy: <b>on</b> (Fridays at 23:30)" in env.session.edits[-1]
    await env.press(env.button(texts.BTN_BACKUP_WEEKLY_OFF))
    assert "Weekly copy: <b>off</b>" in env.session.edits[-1]
    await env.press(env.button(texts.BTN_BACKUP_NOW))
    assert len(env.session.documents) == 1


async def test_weekly_backup(config, sessionmaker, monkeypatch):
    sent = []

    async def fake_send(bot, cfg, calendar, caption=None):
        sent.append(calendar)
        return datetime(2026, 10, 10, 9, 0, tzinfo=TZ)

    monkeypatch.setattr(jobs, "send_backup", fake_send)

    def at(local: datetime):
        monkeypatch.setattr(jobs, "now_local", lambda tz: local)

    at(datetime(2026, 10, 2, 23, 40, tzinfo=TZ))  # Friday night, first run: start counting
    await jobs.send_weekly_backup(None, sessionmaker, config)  # type: ignore[arg-type]
    assert sent == []
    at(datetime(2026, 10, 8, 12, 0, tzinfo=TZ))  # Thursday: this week's copy is done
    await jobs.send_weekly_backup(None, sessionmaker, config)  # type: ignore[arg-type]
    assert sent == []
    at(datetime(2026, 10, 10, 9, 0, tzinfo=TZ))  # Saturday: Friday's copy was missed → now
    await jobs.send_weekly_backup(None, sessionmaker, config)  # type: ignore[arg-type]
    await jobs.send_weekly_backup(None, sessionmaker, config)  # type: ignore[arg-type]
    assert len(sent) == 1

    async with sessionmaker() as session:
        await SettingsService(session, Calendar.JALALI).set_backup(False)
    at(datetime(2026, 10, 17, 23, 45, tzinfo=TZ))
    await jobs.send_weekly_backup(None, sessionmaker, config)  # type: ignore[arg-type]
    assert len(sent) == 1


# --- Briefing and nightly report ---


async def test_todos_in_the_briefing_and_the_nightly_report(config, sessionmaker, monkeypatch):
    morning = datetime(2026, 10, 4, 8, 0, tzinfo=TZ)
    monkeypatch.setattr(jobs, "now_local", lambda tz: morning)
    monkeypatch.setattr(jobs, "utcnow", lambda: to_utc(morning))
    async with sessionmaker() as session:
        todos = TodoService(session)
        [done, _] = await todos.add(["نون بخرم", "قبض برق"], morning.date())
        await todos.add(["تعویض روغن"], morning.date().replace(day=3))  # carried from yesterday
        await todos.set_done([done.id])
    bot = FakeBot()
    await jobs.send_morning_briefing(bot, sessionmaker, config)  # type: ignore[arg-type]
    briefing = bot.sent[0][1]
    assert "To-dos" in briefing and "☐ قبض برق" in briefing and "نون بخرم" not in briefing
    assert "☐ تعویض روغن <i>(Sat 11 Mehr 1405)</i>" in briefing

    night = datetime(2026, 10, 4, 22, 0, tzinfo=TZ)
    monkeypatch.setattr(jobs, "now_local", lambda tz: night)
    await jobs.send_nightly_report(bot, sessionmaker, config)  # type: ignore[arg-type]
    assert "To-dos: 1 of 3 done · still open: تعویض روغن, قبض برق" in bot.sent[1][1]


def test_backup_slots():
    from app.bot.handlers.backup import last_slot

    friday = datetime(2026, 10, 2, 23, 30, tzinfo=TZ)
    assert last_slot(friday) == friday
    assert last_slot(datetime(2026, 10, 2, 23, 29, tzinfo=TZ)).day == 25  # the week before
    assert last_slot(datetime(2026, 10, 7, 9, 0, tzinfo=TZ)) == friday
    assert time(23, 30) == friday.timetz().replace(tzinfo=None)
