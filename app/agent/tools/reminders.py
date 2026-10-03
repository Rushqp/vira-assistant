"""Reminder tools: create, list, update, cancel.

Time resolution (design §4.2): the model sends its interpretation (`start`) and the user's own
words (`when_text`). The deterministic parser wins where it is certain (explicit dates incl.
Jalali, «فردا», «صبح», "14:30"); the model's value fills what the parser can't decide
(e.g. am/pm of «ساعت ۲» from context).
"""

import re
from datetime import date, datetime, time, timedelta

import jdatetime
from pydantic import Field

from app.agent.tools import Args, Card, Tool, ToolContext, ToolError, ToolOutcome
from app.agent.tools.common import jalali, parse_local_datetime
from app.config import Calendar
from app.core.parsers.datetime_parser import RepeatRule
from app.core.parsers.rules import parse_reminder
from app.db.models import Reminder
from app.services.reminders import ReminderDraft, from_utc

REPEATS = ["none", "daily", "weekly", "monthly"]
_RELATIVE = re.compile(r"^\s*-?\s*(\d+)\s*(m|min|mins|minutes?|h|hours?|d|days?)\s*$", re.I)
_UNIT_MINUTES = {"m": 1, "h": 60, "d": 1440}


def reminder_info(reminder: Reminder, ctx: ToolContext) -> dict:
    event = from_utc(reminder.event_at, ctx.config.timezone)
    pending = sorted(a.notify_at for a in reminder.alerts if a.sent_at is None)
    return {
        "id": reminder.id,
        "subject": reminder.text,
        "start": event.date().isoformat() if reminder.all_day else f"{event:%Y-%m-%dT%H:%M}",
        "start_jalali": jalali(event.date()),
        "repeat": reminder.repeat_rule or "none",
        "alerts": [f"{from_utc(t, ctx.config.timezone):%Y-%m-%dT%H:%M}" for t in pending],
        "important": reminder.important,
    }


def _summary(reminder: Reminder, ctx: ToolContext) -> str:
    info = reminder_info(reminder, ctx)
    return f"#{reminder.id} {reminder.text} — {info['start']}"


# --- Resolving the time ---


def resolve_start(
    start: str | None, when_text: str | None, ctx: ToolContext
) -> tuple[date | None, time | None, bool, RepeatRule | None]:
    """(date, time, flexible_week, repeat from the words) of the event."""
    model_day, model_dt = parse_local_datetime(start) if start else (None, None)
    moment = parse_reminder(when_text, ctx.today, ctx.config.day_times).event if when_text else None

    if moment is not None and moment.delta is not None:  # «۱۰ دقیقه دیگه»
        at = (ctx.now + moment.delta).replace(second=0, microsecond=0, tzinfo=None)
        return at.date(), at.time(), False, moment.repeat

    day = (moment.date if moment and moment.date else None) or model_day
    clock: time | None = None
    if moment and moment.time and not moment.ambiguous:
        clock = moment.time
    elif model_dt is not None:
        clock = model_dt.time()
    elif moment and moment.time:  # «ساعت ۲» and the model didn't decide
        raise ToolError(
            f"the time in {when_text!r} could be AM or PM",
            "ask the user, or pass start with the time you are sure about",
        )
    flexible = bool(moment and moment.date and moment.flexible_week)
    return day, clock, flexible, moment.repeat if moment else None


def _repeat(kind: str | None, from_words: RepeatRule | None, day: date, calendar: Calendar):
    kind = (kind or "none").lower()
    if kind == "none" and from_words is not None:
        kind = from_words.kind
    if kind == "daily":
        return RepeatRule("daily").serialize()
    if kind == "weekly":
        return RepeatRule("weekly", weekday=day.weekday()).serialize()
    if kind == "monthly":
        dom = jdatetime.date.fromgregorian(date=day).day if calendar == Calendar.JALALI else day.day
        return RepeatRule("monthly", day=dom, calendar=calendar.value).serialize()
    return None


def map_alerts(
    alerts: list[str], event_day: date, repeat: str | None, ctx: ToolContext
) -> tuple[list[str], list[str]]:
    """Alert words → (specs relative to the event, one-off ISO datetimes)."""
    specs: list[str] = []
    extras: list[str] = []
    tz = ctx.config.timezone
    for raw in alerts:
        text = str(raw).strip()
        if not text:
            continue
        if text.lower() in ("at", "at start", "start", "on time"):
            specs.append("at")
            continue
        if match := _RELATIVE.match(text):
            minutes = int(match[1]) * _UNIT_MINUTES[match[2][0].lower()]
            specs.append(f"before:{minutes}")
            continue
        day, moment_dt = parse_local_datetime(text)
        if moment_dt is None and (clock := re.fullmatch(r"(\d{1,2}):(\d{2})", text)):
            day, moment_dt = (
                event_day,
                datetime.combine(event_day, time(int(clock[1]), int(clock[2]))),
            )
        if moment_dt is None:  # words: «صبح», «شب قبلش», "1 hour before"
            moment = parse_reminder(text, ctx.today, ctx.config.day_times).event
            if moment.minutes_before:
                specs.append(f"before:{moment.minutes_before}")
            elif moment.day_before:
                specs.append(f"day_before:{moment.day_before:%H:%M}")
            elif moment.time and not moment.date:
                specs.append(f"same_day:{moment.time:%H:%M}")
            elif moment.date and moment.time:
                day, moment_dt = moment.date, datetime.combine(moment.date, moment.time)
            else:
                raise ToolError(f"could not understand alert {text!r}", 'use "at", "-15m", "-1h"')
        if moment_dt is not None and day is not None:
            if day == event_day:
                specs.append(f"same_day:{moment_dt:%H:%M}")
            elif day == event_day - timedelta(days=1):
                specs.append(f"day_before:{moment_dt:%H:%M}")
            elif repeat:
                raise ToolError("a repeating reminder needs alerts relative to each occurrence")
            else:
                extras.append(moment_dt.replace(tzinfo=tz).isoformat())
    return list(dict.fromkeys(specs)), extras


def _finish_draft(draft: ReminderDraft, ctx: ToolContext) -> tuple[ReminderDraft, str]:
    """Check a draft can be saved; returns it and a note about adjusted alerts."""
    step = draft.next_step(ctx.now, ctx.config.day_times)
    if step == "subject":
        raise ToolError("the reminder has no subject", "ask the user what to remind about")
    if step in ("when", "ambiguous"):
        raise ToolError("no date or time for the reminder", "ask the user when")
    if step == "time":
        raise ToolError(
            "'before' alerts need a clock time", "ask the user for the time, or use 'at'"
        )
    if step == "past":
        raise ToolError("that time has already passed", "ask the user for a future time")
    note = ""
    if step == "alerts_past":
        draft.alerts, draft.extra_alerts = ["at"], []
        note = "the requested notification time had passed; it will notify at the start"
    return draft, note


# --- create_reminder ---


class CreateReminderArgs(Args):
    subject: str = ""
    start: str | None = None
    when_text: str | None = None
    alerts: list[str] = Field(default_factory=list)
    repeat: str = "none"
    important: bool = False


async def create_reminder(args: CreateReminderArgs, ctx: ToolContext) -> ToolOutcome:
    if not args.start and not args.when_text:
        raise ToolError("no date or time for the reminder", "ask the user when")
    day, clock, flexible, words_repeat = resolve_start(args.start, args.when_text, ctx)
    event_day = day or ctx.today
    repeat = _repeat(args.repeat, words_repeat, event_day, ctx.calendar)
    specs, extras = map_alerts(args.alerts, event_day, repeat, ctx)
    ask_alerts = not specs and not extras
    draft = ReminderDraft(
        raw=ctx.user_text,
        subject=args.subject.strip(),
        date=day.isoformat() if day else None,
        time=f"{clock:%H:%M}" if clock else None,
        flexible_week=flexible,
        repeat=repeat,
        alerts=specs or (["at"] if ask_alerts else []),
        extra_alerts=extras,
        important=args.important,
    )
    draft, adjusted = _finish_draft(draft, ctx)
    reminder = await ctx.reminders.create(draft, ctx.now)
    reminder = await ctx.reminders.get(reminder.id)
    summary = _summary(reminder, ctx)
    action = await ctx.actions.record(
        "reminder_created", {"id": reminder.id}, f"created reminder {summary}"
    )
    result = {"created": reminder_info(reminder, ctx)}
    if adjusted:
        result["note"] = adjusted
    if ask_alerts:
        result["note"] = "no notification time given: notifies at the start; the app offers buttons"
    return ToolOutcome(
        result=result,
        card=Card("reminder_saved", action.id, {"id": reminder.id, "ask_alerts": ask_alerts}),
        note=f"[done: reminder created — {summary}]",
    )


# --- list_reminders ---


class ListRemindersArgs(Args):
    query: str | None = None


async def list_reminders(args: ListRemindersArgs, ctx: ToolContext) -> ToolOutcome:
    if args.query:
        _, items = await ctx.reminders.search(args.query)
    else:
        items = await ctx.reminders.upcoming(limit=40)
    return ToolOutcome(
        result={"count": len(items), "reminders": [reminder_info(r, ctx) for r in items]}
    )


async def _target(ctx: ToolContext, rid: int | None, query: str | None) -> Reminder | ToolOutcome:
    """The one reminder the user means, or an outcome listing the candidates."""
    if rid:
        found = await ctx.reminders.active_by_ids([rid])
        if not found:
            raise ToolError(f"no active reminder #{rid}", "use list_reminders")
        return found[0]
    if not query:
        raise ToolError("give an id or a query", "use ids from [done: …] notes or list_reminders")
    best, matches = await ctx.reminders.search(query)
    if best is not None:
        return best
    if not matches:
        raise ToolError(f"no upcoming reminder matches {query!r}", "use list_reminders")
    return ToolOutcome(
        result={
            "status": "several_match",
            "candidates": [reminder_info(r, ctx) for r in matches[:10]],
            "hint": "ask the user which one, then call again with its id",
        }
    )


# --- cancel_reminders ---


class CancelRemindersArgs(Args):
    ids: list[int] = Field(default_factory=list)
    query: str | None = None


async def cancel_reminders(args: CancelRemindersArgs, ctx: ToolContext) -> ToolOutcome:
    if args.ids:
        targets = await ctx.reminders.active_by_ids(args.ids)
        if not targets:
            raise ToolError(f"no active reminders with ids {args.ids}", "use list_reminders")
    else:
        found = await _target(ctx, None, args.query)
        if isinstance(found, ToolOutcome):
            return found
        targets = [found]
    info = [reminder_info(r, ctx) for r in targets]
    await ctx.reminders.set_status([r.id for r in targets], "cancelled")
    summary = "; ".join(f"#{i['id']} {i['subject']} — {i['start']}" for i in info)
    action = await ctx.actions.record(
        "reminders_cancelled", {"ids": [r.id for r in targets]}, f"cancelled {summary}"
    )
    return ToolOutcome(
        result={"cancelled": info},
        card=Card("reminders_cancelled", action.id, {"items": info}),
        note=f"[done: reminders cancelled — {summary}]",
    )


# --- update_reminder ---


class UpdateReminderArgs(Args):
    id: int | None = None
    query: str | None = None
    subject: str | None = None
    start: str | None = None
    when_text: str | None = None
    alerts: list[str] | None = None
    repeat: str | None = None
    important: bool | None = None


async def update_reminder(args: UpdateReminderArgs, ctx: ToolContext) -> ToolOutcome:
    found = await _target(ctx, args.id, args.query)
    if isinstance(found, ToolOutcome):
        return found
    reminder = found
    snapshot = ctx.reminders.snapshot(reminder)
    draft = ctx.reminders.to_draft(reminder)
    draft.raw = ctx.user_text or draft.raw
    if args.subject:
        draft.subject = args.subject.strip()
    if args.important is not None:
        draft.important = args.important
    if args.start or args.when_text:
        day, clock, flexible, words_repeat = resolve_start(args.start, args.when_text, ctx)
        if day is not None:
            draft.date = day.isoformat()
        if clock is not None or (args.start and "T" not in args.start):
            draft.time = f"{clock:%H:%M}" if clock else None
        draft.flexible_week = flexible
        if words_repeat and args.repeat is None:
            args.repeat = words_repeat.kind
    event_day = date.fromisoformat(draft.date) if draft.date else ctx.today
    if args.repeat is not None:
        draft.repeat = _repeat(args.repeat, None, event_day, ctx.calendar)
    if args.alerts is not None:
        draft.alerts, draft.extra_alerts = map_alerts(args.alerts, event_day, draft.repeat, ctx)
        if not draft.alerts and not draft.extra_alerts:
            draft.alerts = ["at"]
    draft, adjusted = _finish_draft(draft, ctx)
    updated = await ctx.reminders.update(reminder.id, draft)
    assert updated is not None
    summary = _summary(updated, ctx)
    action = await ctx.actions.record(
        "reminder_updated", {"snapshot": snapshot}, f"updated reminder {summary}"
    )
    result = {"updated": reminder_info(updated, ctx)}
    if adjusted:
        result["note"] = adjusted
    return ToolOutcome(
        result=result,
        card=Card("reminder_updated", action.id, {"id": updated.id}),
        note=f"[done: reminder updated — {summary}]",
    )


# --- Schemas ---

_ALERTS_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
    "description": 'Only if the user said when to notify: "at", "-15m", "-1h", "-1d" or '
    '"YYYY-MM-DDTHH:MM"',
}

REMINDER_TOOLS = [
    Tool(
        name="create_reminder",
        description="Create a reminder for an event or task.",
        parameters={
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "What to remind about"},
                "start": {
                    "type": "string",
                    "description": "Event time 'YYYY-MM-DDTHH:MM' or 'YYYY-MM-DD' (whole day)",
                },
                "when_text": {
                    "type": "string",
                    "description": "The user's own words for the event date/time",
                },
                "alerts": _ALERTS_SCHEMA,
                "repeat": {"type": "string", "enum": REPEATS},
                "important": {"type": "boolean"},
            },
            "required": ["subject"],
        },
        args_model=CreateReminderArgs,
        handler=create_reminder,
    ),
    Tool(
        name="list_reminders",
        description="List upcoming reminders (ids, times), optionally matching a query.",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        args_model=ListRemindersArgs,
        handler=list_reminders,
    ),
    Tool(
        name="update_reminder",
        description="Change a reminder: subject, time, alerts, repeat or importance.",
        parameters={
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "query": {"type": "string", "description": "If no id: words of its subject"},
                "subject": {"type": "string"},
                "start": {"type": "string"},
                "when_text": {"type": "string"},
                "alerts": _ALERTS_SCHEMA,
                "repeat": {"type": "string", "enum": REPEATS},
                "important": {"type": "boolean"},
            },
        },
        args_model=UpdateReminderArgs,
        handler=update_reminder,
    ),
    Tool(
        name="cancel_reminders",
        description="Cancel reminders by ids, or by a short query of the subject (e.g. 'دکتر').",
        parameters={
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "integer"}},
                "query": {"type": "string"},
            },
        },
        args_model=CancelRemindersArgs,
        handler=cancel_reminders,
    ),
]
