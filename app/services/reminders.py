"""Reminders: drafts (what still needs asking), time calculations and storage.

Flow: text → `parse_reminder` → `ReminderDraft` → questions until `next_step()` is None →
`ReminderService.create()`. The scheduler later sends due alerts and moves repeating
reminders to their next occurrence.

Alert specs (relative to the event, rebuilt for every occurrence of a repeating reminder):
    at                — at the event time (all-day events: in the morning)
    before:<minutes>  — e.g. before:15
    day_before:HH:MM  — the day before at a time (e.g. the night before)
    same_day:HH:MM    — on the event day at a time (e.g. in the morning)
"""

import calendar as pycalendar
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import jdatetime
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Calendar
from app.core.parsers.datetime_parser import DayTimes, RepeatRule
from app.core.parsers.rules import ReminderParse
from app.db.models import Reminder, ReminderAlert, utcnow

Step = Literal["subject", "when", "ambiguous", "time", "past", "alerts", "alerts_past"]

# Fallback when the LLM can't be asked whether a reminder is important.
IMPORTANT_KEYWORDS = re.compile(
    r"doctor|dentist|hospital|appointment|flight|airport|interview|exam|meeting|bank|pay|bill"
    r"|rent|medicine|pill|deadline|court|visa|passport|birthday|important|urgent"
    r"|دکتر|دندان|بیمارستان|نوبت|پرواز|فرودگاه|مصاحبه|امتحان|جلسه|بانک|قسط|قبض|اجاره"
    r"|دارو|قرص|ددلاین|دادگاه|ویزا|پاسپورت|گذرنامه|تولد|مهم|فوری",
    re.IGNORECASE,
)


def guess_important(text: str) -> bool:
    return bool(IMPORTANT_KEYWORDS.search(text))


# --- Time helpers ---


def to_utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(tzinfo=None)


def from_utc(dt: datetime, tz: ZoneInfo) -> datetime:
    return dt.replace(tzinfo=UTC).astimezone(tz)


def _hhmm(t: time) -> str:
    return f"{t:%H:%M}"


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _jalali_month_days(year: int, month: int) -> int:
    if month <= 6:
        return 31
    if month <= 11:
        return 30
    return 30 if jdatetime.date(year, 1, 1).isleap() else 29


def monthly_date(day: int, cal: str, year_month_from: date, months_ahead: int = 0) -> date:
    """The `day`-th of the (Jalali or Gregorian) month `months_ahead` after the given date's
    month, clamped to the month length (e.g. 31 → 30 in Mehr)."""
    if cal == Calendar.JALALI:
        j = jdatetime.date.fromgregorian(date=year_month_from)
        index = j.year * 12 + (j.month - 1) + months_ahead
        year, month = divmod(index, 12)
        month += 1
        return jdatetime.date(year, month, min(day, _jalali_month_days(year, month))).togregorian()
    index = year_month_from.year * 12 + (year_month_from.month - 1) + months_ahead
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day, pycalendar.monthrange(year, month)[1]))


def next_occurrence(rule: RepeatRule, event: datetime, after: datetime) -> datetime:
    """First occurrence of a repeating event strictly after `after` (both local)."""
    current = event
    months = 0
    while current <= after:
        if rule.kind == "daily":
            current += timedelta(days=1)
        elif rule.kind == "weekly":
            current += timedelta(days=7)
        else:
            months += 1
            day = monthly_date(
                rule.day or event.day, rule.calendar or "gregorian", event.date(), months
            )
            current = datetime.combine(day, event.timetz())
    return current


def alert_time(spec: str, event: datetime, all_day: bool, day_times: DayTimes) -> datetime | None:
    """When an alert spec fires for a given (local) event time; None if it doesn't apply."""
    tz = event.tzinfo
    if spec == "at":
        if all_day:
            return datetime.combine(event.date(), day_times.morning, tz)
        return event
    kind, _, value = spec.partition(":")
    if kind == "before":
        return None if all_day else event - timedelta(minutes=int(value))
    if kind == "day_before":
        return datetime.combine(event.date() - timedelta(days=1), _parse_hhmm(value), tz)
    if kind == "same_day":
        return datetime.combine(event.date(), _parse_hhmm(value), tz)
    return None


# --- Draft ---


@dataclass
class ReminderDraft:
    """Everything known about a reminder being created. Stored in the FSM between questions."""

    raw: str
    subject: str = ""
    date: str | None = None  # ISO date of the event (local)
    time: str | None = None  # HH:MM (local); None = all day
    ambiguous: bool = False  # hour 1–12 without am/pm: `time` holds the AM reading
    flexible_week: bool = False
    repeat: str | None = None  # serialized RepeatRule
    alerts: list[str] | None = None  # alert specs; None = ask the user
    extra_alerts: list[str] = field(default_factory=list)  # ISO local datetimes
    important: bool | None = None
    replace_id: int | None = None  # editing an existing reminder

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ReminderDraft":
        return cls(**data)

    # --- Building from parsed text ---

    @classmethod
    def from_parse(
        cls, parse: ReminderParse, raw: str, now: datetime, cal: Calendar
    ) -> "ReminderDraft":
        draft = cls(raw=raw, subject=parse.subject)
        draft.apply_event(parse, now, cal)
        draft.apply_notify(parse, now)
        return draft

    def apply_event(self, parse: ReminderParse, now: datetime, cal: Calendar) -> None:
        event = parse.event
        if event.delta is not None:
            at = (now + event.delta).replace(second=0, microsecond=0)
            self.date, self.time, self.ambiguous = at.date().isoformat(), _hhmm(at.time()), False
        else:
            self.date = event.date.isoformat() if event.date else None
            self.time = _hhmm(event.time) if event.time else None
            self.ambiguous = event.ambiguous
            self.flexible_week = event.flexible_week
        if event.repeat:
            rule = event.repeat
            if rule.kind == "weekly" and rule.weekday is None:
                base = date.fromisoformat(self.date) if self.date else now.date()
                rule = RepeatRule("weekly", weekday=base.weekday())
            if rule.kind == "monthly":
                base = date.fromisoformat(self.date) if self.date else now.date()
                day = rule.day or (
                    jdatetime.date.fromgregorian(date=base).day
                    if cal == Calendar.JALALI
                    else base.day
                )
                rule = RepeatRule("monthly", day=day, calendar=cal.value)
                self.date = None  # computed from the rule
            self.repeat = rule.serialize()

    def apply_notify(self, parse: ReminderParse, now: datetime) -> None:
        if parse.notify_at_event:
            self.alerts = ["at"]
            return
        notify = parse.notify
        if notify is None or notify.empty:
            return
        if notify.minutes_before:
            self.alerts = [f"before:{notify.minutes_before}"]
        elif notify.day_before:
            self.alerts = [f"day_before:{_hhmm(notify.day_before)}"]
        elif notify.delta is not None:
            self.alerts = []
            self.extra_alerts = [(now + notify.delta).replace(second=0, microsecond=0).isoformat()]
        elif notify.date:
            when = datetime.combine(notify.date, notify.time or time(9), now.tzinfo)
            self.alerts, self.extra_alerts = [], [when.isoformat()]
        elif notify.time:
            chosen = notify.time
            if notify.ambiguous and self.time and not self.ambiguous:
                pm = time((chosen.hour + 12) % 24, chosen.minute)
                chosen = pm if pm <= _parse_hhmm(self.time) else chosen
            self.alerts = [f"same_day:{_hhmm(chosen)}"]

    # --- What is still missing ---

    def event_datetime(self, now: datetime) -> tuple[datetime, bool]:
        """The (next) event time in local time and whether it is an all-day event."""
        tz = now.tzinfo
        t = _parse_hhmm(self.time) if self.time else time(0)
        all_day = self.time is None
        rule = RepeatRule.parse(self.repeat) if self.repeat else None
        if rule and rule.kind == "monthly":
            day = monthly_date(rule.day or 1, rule.calendar or "gregorian", now.date())
            event = datetime.combine(day, t, tz)
            if event <= now:
                event = datetime.combine(
                    monthly_date(rule.day or 1, rule.calendar or "gregorian", now.date(), 1), t, tz
                )
            return event, all_day
        if self.date:
            event = datetime.combine(date.fromisoformat(self.date), t, tz)
            if self.flexible_week and not all_day and event <= now:
                event += timedelta(days=7)
            return event, all_day
        event = datetime.combine(now.date(), t, tz)
        if not all_day and event <= now:
            event += timedelta(days=1)
        return event, all_day

    def alert_times(self, now: datetime, day_times: DayTimes) -> list[tuple[datetime, str]]:
        """Future alert times as (local datetime, kind), sorted."""
        event, all_day = self.event_datetime(now)
        result: list[tuple[datetime, str]] = []
        for spec in self.alerts or []:
            when = alert_time(spec, event, all_day, day_times)
            if when is not None:
                result.append((when, "spec"))
        for value in self.extra_alerts:
            result.append((datetime.fromisoformat(value), "extra"))
        cutoff = now - timedelta(minutes=1)
        return sorted({(w, k) for w, k in result if w > cutoff})

    def next_step(self, now: datetime, day_times: DayTimes) -> Step | None:
        if not self.subject:
            return "subject"
        if self.date is None and self.time is None and self.repeat is None:
            return "when"
        if self.ambiguous:
            return "ambiguous"
        # "15 minutes before" needs a clock time; all-day events are otherwise fine.
        if self.time is None and any(a.startswith("before:") for a in self.alerts or []):
            return "time"
        event, all_day = self.event_datetime(now)
        if (all_day and event.date() < now.date()) or (not all_day and event <= now):
            return "past"
        if self.alerts is None:
            return "alerts"
        if not self.alert_times(now, day_times):
            return "alerts_past"
        return None


# --- Storage ---


class ReminderService:
    def __init__(self, session: AsyncSession, timezone: ZoneInfo, day_times: DayTimes) -> None:
        self.session = session
        self.timezone = timezone
        self.day_times = day_times

    def now(self) -> datetime:
        return datetime.now(self.timezone)

    async def create(self, draft: ReminderDraft, now: datetime | None = None) -> Reminder:
        now = now or self.now()
        event, all_day = draft.event_datetime(now)
        if draft.replace_id:
            await self.delete(draft.replace_id)
        reminder = Reminder(
            text=draft.subject,
            raw_text=draft.raw,
            event_at=to_utc(event),
            all_day=all_day,
            repeat_rule=draft.repeat,
            alert_specs=",".join(draft.alerts or []),
            important=bool(draft.important),
            status="active",
        )
        reminder.alerts = [
            ReminderAlert(notify_at=to_utc(when), kind=kind)
            for when, kind in draft.alert_times(now, self.day_times)
        ]
        self.session.add(reminder)
        await self.session.commit()
        return reminder

    async def get(self, reminder_id: int) -> Reminder | None:
        return await self.session.scalar(
            select(Reminder)
            .options(selectinload(Reminder.alerts))
            .where(Reminder.id == reminder_id)
        )

    async def upcoming(self, limit: int = 20) -> list[Reminder]:
        rows = await self.session.scalars(
            select(Reminder)
            .options(selectinload(Reminder.alerts))
            .where(Reminder.status == "active")
            .order_by(Reminder.event_at)
            .limit(limit)
        )
        return list(rows.all())

    async def on_day(self, day: date) -> list[Reminder]:
        """Active reminders whose event falls on `day` (local), important first."""
        start = to_utc(datetime.combine(day, time(0), self.timezone))
        end = to_utc(datetime.combine(day + timedelta(days=1), time(0), self.timezone))
        rows = await self.session.scalars(
            select(Reminder)
            .where(Reminder.status == "active", Reminder.event_at >= start, Reminder.event_at < end)
            .order_by(Reminder.important.desc(), Reminder.event_at)
        )
        return list(rows.all())

    async def delete(self, reminder_id: int) -> None:
        await self.session.execute(
            delete(ReminderAlert).where(ReminderAlert.reminder_id == reminder_id)
        )
        await self.session.execute(delete(Reminder).where(Reminder.id == reminder_id))
        await self.session.commit()

    async def mark_done(self, reminder_id: int) -> Reminder | None:
        """✅ Done: one-off reminders are closed; repeating ones skip to the next occurrence."""
        reminder = await self.get(reminder_id)
        if reminder is None:
            return None
        self._drop_pending(reminder)
        if reminder.repeat_rule:
            self._advance(reminder, max(self.now(), from_utc(reminder.event_at, self.timezone)))
        else:
            reminder.status = "done"
        await self.session.commit()
        return reminder

    async def snooze(self, reminder_id: int, minutes: int) -> datetime | None:
        reminder = await self.get(reminder_id)
        if reminder is None:
            return None
        when = self.now().replace(second=0, microsecond=0) + timedelta(minutes=minutes)
        reminder.status = "active"
        reminder.alerts.append(ReminderAlert(notify_at=to_utc(when), kind="extra"))
        await self.session.commit()
        return when

    # --- Used by the scheduler ---

    async def due_alerts(self, now_utc: datetime) -> list[ReminderAlert]:
        rows = await self.session.scalars(
            select(ReminderAlert)
            .join(Reminder)
            .options(selectinload(ReminderAlert.reminder))
            .where(
                ReminderAlert.sent_at.is_(None),
                ReminderAlert.notify_at <= now_utc,
                Reminder.status == "active",
            )
            .order_by(ReminderAlert.notify_at)
        )
        return list(rows.all())

    async def mark_sent(self, alert: ReminderAlert) -> None:
        alert.sent_at = utcnow()
        await self.session.commit()

    async def roll_forward(self, now_utc: datetime) -> None:
        """Past events without pending alerts: repeating ones move on, one-off ones are done."""
        rows = await self.session.scalars(
            select(Reminder)
            .options(selectinload(Reminder.alerts))
            .where(Reminder.status == "active", Reminder.event_at <= now_utc)
        )
        now_local = from_utc(now_utc, self.timezone)
        for reminder in rows.all():
            if any(a.sent_at is None for a in reminder.alerts):
                continue
            if reminder.repeat_rule:
                self._advance(reminder, now_local)
            else:
                reminder.status = "done"
        await self.session.commit()

    # --- Internals ---

    def _drop_pending(self, reminder: Reminder) -> None:
        reminder.alerts = [a for a in reminder.alerts if a.sent_at is not None]

    def _advance(self, reminder: Reminder, after: datetime) -> None:
        """Move a repeating reminder to its next occurrence after `after` and rebuild alerts."""
        rule = RepeatRule.parse(reminder.repeat_rule or "daily")
        event = from_utc(reminder.event_at, self.timezone)
        upcoming = next_occurrence(rule, event, after)
        reminder.event_at = to_utc(upcoming)
        reminder.alerts = [a for a in reminder.alerts if a.sent_at is None and a.kind == "extra"]
        specs = [s for s in reminder.alert_specs.split(",") if s] or ["at"]
        for spec in specs:
            when = alert_time(spec, upcoming, reminder.all_day, self.day_times)
            if when is not None and when > after:
                reminder.alerts.append(ReminderAlert(notify_at=to_utc(when), kind="spec"))
