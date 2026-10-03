"""Measure how well each configured model understands real messages (accuracy + latency).

Runs a fixed set of Persian / English cases (including reported failures) through the agent with
every provider configured in .env, one provider at a time, each case on a fresh database, and
checks what actually happened in the database.

    python scripts/eval_agent.py                 # all configured providers
    python scripts/eval_agent.py --provider local --case doctor
    docker compose exec bot python scripts/eval_agent.py

Use it to pick models for a hardware profile on the real server (docs/AGENT_DESIGN.md §8).
"""

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.agent.actions import ActionLog
from app.agent.core import Agent, AgentUnavailable
from app.agent.tools import ToolContext, build_registry
from app.config import Calendar, Settings, get_settings
from app.db.models import Expense, Reminder
from app.db.session import create_engine, create_sessionmaker, run_migrations
from app.llm.providers import ProviderChain, build_clients
from app.services.expenses import ExpenseService
from app.services.reminders import ReminderService, from_utc
from app.services.settings import SettingsService

Check = Callable[["Outcome"], Awaitable[str | None]]  # returns a problem, or None if fine


@dataclass
class Outcome:
    ctx: ToolContext
    result: object  # AgentResult
    now: datetime

    async def expenses(self) -> list[Expense]:
        rows = await self.ctx.expenses.session.scalars(select(Expense).order_by(Expense.id))
        return list(rows.unique().all())

    async def reminders(self) -> list[Reminder]:
        rows = await self.ctx.reminders.session.scalars(select(Reminder).order_by(Reminder.id))
        return list(rows.all())

    def local(self, reminder: Reminder) -> datetime:
        return from_utc(reminder.event_at, self.ctx.config.timezone).replace(tzinfo=None)

    @property
    def tools(self) -> list[str]:
        return [card.kind for card in self.result.cards]  # type: ignore[attr-defined]


@dataclass
class Case:
    id: str
    message: str
    check: Check
    setup: list[tuple[str, dict]] = field(default_factory=list)  # (tool, args) done before


# --- Checks ---


def expenses_are(*expected: int) -> Check:
    async def check(o: Outcome) -> str | None:
        amounts = [e.amount for e in await o.expenses()]
        return (
            None
            if sorted(amounts) == sorted(expected)
            else f"expenses {amounts} ≠ {list(expected)}"
        )

    return check


def asks_scale() -> Check:
    async def check(o: Outcome) -> str | None:
        if o.result.clarification is None:  # type: ignore[attr-defined]
            return f"no thousand/million question (saved {[e.amount for e in await o.expenses()]})"
        return None

    return check


def reminder_at(
    day_offset: int, hour: int, minute: int = 0, alert: str | None = None, repeat=None
) -> Check:
    async def check(o: Outcome) -> str | None:
        items = await o.reminders()
        if len(items) != 1:
            return f"{len(items)} reminders"
        reminder = items[0]
        expected = (o.now + timedelta(days=day_offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0, tzinfo=None
        )
        if o.local(reminder) != expected:
            return f"time {o.local(reminder)} ≠ {expected}"
        if alert and alert not in reminder.alert_specs:
            return f"alerts {reminder.alert_specs!r} lack {alert!r}"
        if repeat and not (reminder.repeat_rule or "").startswith(repeat):
            return f"repeat {reminder.repeat_rule!r} ≠ {repeat}"
        return None

    return check


def weekly_on(weekday: int, hour: int) -> Check:
    async def check(o: Outcome) -> str | None:
        items = await o.reminders()
        if len(items) != 1:
            return f"{len(items)} reminders"
        when = o.local(items[0])
        if (when.weekday(), when.hour) != (weekday, hour):
            return f"first time {when:%A %H:%M}"
        rule = items[0].repeat_rule or ""
        return None if rule.startswith("weekly") else f"repeat {rule!r}"

    return check


def reminder_in_minutes(minutes: int) -> Check:
    async def check(o: Outcome) -> str | None:
        items = await o.reminders()
        if len(items) != 1:
            return f"{len(items)} reminders"
        delta = o.local(items[0]) - o.now.replace(tzinfo=None)
        return None if abs(delta.total_seconds() - minutes * 60) <= 90 else f"in {delta}"

    return check


def reminder_status(status: str) -> Check:
    async def check(o: Outcome) -> str | None:
        statuses = [r.status for r in await o.reminders()]
        return None if statuses == [status] else f"statuses {statuses}"

    return check


def used(kind: str) -> Check:
    async def check(o: Outcome) -> str | None:
        return None if kind in o.tools else f"no {kind} card (got {o.tools})"

    return check


def no_tools_with_answer() -> Check:
    async def check(o: Outcome) -> str | None:
        if o.tools:
            return f"unexpected actions {o.tools}"
        return None if o.result.text else "empty answer"  # type: ignore[attr-defined]

    return check


def answer_contains(*options: str) -> Check:
    async def check(o: Outcome) -> str | None:
        text = o.result.text.replace("٬", ",")  # type: ignore[attr-defined]
        return None if any(opt in text for opt in options) else f"answer {text[:80]!r}"

    return check


def setting_calendar(value: str) -> Check:
    async def check(o: Outcome) -> str | None:
        current = (await o.ctx.settings.get_calendar()).value
        return None if current == value else f"calendar {current}"

    return check


def tomorrow_iso(now: datetime) -> str:
    return (now + timedelta(days=1)).date().isoformat()


CASES = [
    Case(
        "purchases",
        "امروز من ۳ خرید کرد کردم\nسیگار ۱۵۰ هزار تومن\nماست ۲۰۰ هزار تومن\nو اب ۵۰ هزار تومن",
        expenses_are(150_000, 200_000, 50_000),
    ),
    Case(
        "reminder-5min",
        "یک یاد اوری تنظیم کن برای ۵ دقیقه دیگه میخوام کتاب بخونم",
        reminder_in_minutes(5),
    ),
    Case(
        "doctor",
        "فردا ساعت ۲ دکتر دارم، صبح یادم بنداز",
        reminder_at(1, 14, alert="09:00"),
    ),
    Case(
        "english-expenses",
        "Paid 3 million toman for groceries and 100k for fuel",
        expenses_are(3_000_000, 100_000),
    ),
    Case("yesterday", "دیروز دو و نیم میلیون دادم دکتر", expenses_are(2_500_000)),
    Case("ambiguous-amount", "۳ تومن بنزین زدم", asks_scale()),
    Case(
        "weekly",
        "remind me every saturday at 8am to go to the gym",
        weekly_on(5, 8),
    ),
    Case(
        "cancel-follow-up",
        "تایم دکتر رو کنسل کن",
        reminder_status("cancelled"),
        setup=[("create_reminder", {"subject": "دکتر", "start": "{tomorrow}T14:00"})],
    ),
    Case(
        "correct-amount",
        "نه ماست ۲۵۰ هزار بود",
        expenses_are(250_000),
        setup=[("add_expenses", {"items": [{"description": "ماست", "amount_text": "۲۰۰ هزار"}]})],
    ),
    Case("report", "این ماه چقدر خرج کردم؟", used("report")),
    Case("chat", "پایتخت فرانسه کجاست؟", no_tools_with_answer()),
    Case(
        "calculate",
        "۱۵ درصد دو میلیون و چهارصد هزار تومن چقدر میشه؟",
        answer_contains("360,000", "360000", "۳۶۰"),
    ),
    Case("settings", "تقویم رو میلادی کن", setting_calendar("gregorian")),
    Case("night", "یادم بنداز پس فردا شب به مامان زنگ بزنم", reminder_at(2, 22)),
    Case("restaurant", "ناهار امروز با بچه ها ۸۵۰ هزار شد", expenses_are(850_000)),
]


# --- Runner ---


async def run_case(case: Case, client, config: Settings) -> tuple[bool, str, float]:
    folder = Path(tempfile.mkdtemp(prefix="vira-eval-"))
    url = f"sqlite+aiosqlite:///{(folder / 'eval.db').as_posix()}"
    run_migrations(url)
    engine = create_engine(url)
    try:
        async with create_sessionmaker(engine)() as session:
            now = datetime.now(config.timezone)
            settings = SettingsService(session, Calendar.JALALI)
            expenses = ExpenseService(session, config.timezone, config.currency.value)
            reminders = ReminderService(session, config.timezone, config.day_times)
            ctx = ToolContext(
                config, Calendar.JALALI, now, case.message, expenses, reminders, settings,
                ActionLog(session, expenses, reminders, settings),
            )  # fmt: skip
            registry = build_registry()
            history = []
            for name, args in case.setup:
                rendered = {
                    k: (v.replace("{tomorrow}", tomorrow_iso(now)) if isinstance(v, str) else v)
                    for k, v in args.items()
                }
                outcome = await registry.execute(
                    name, json.dumps(rendered, ensure_ascii=False), ctx
                )
                history += [
                    {"role": "user", "content": "(earlier)"},
                    {"role": "assistant", "content": outcome.note},
                ]
            agent = Agent(ProviderChain([client]), registry)
            started = time.perf_counter()
            try:
                result = await agent.run(ctx, history, case.message)
            except AgentUnavailable as exc:
                return False, f"model error: {exc}", time.perf_counter() - started
            elapsed = time.perf_counter() - started
            problem = await case.check(Outcome(ctx, result, now))
            return problem is None, problem or "ok", elapsed
    finally:
        await engine.dispose()
        shutil.rmtree(folder, ignore_errors=True)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", help="only this provider (gemini, groq, github, local)")
    parser.add_argument("--case", help="only cases whose id contains this text")
    args = parser.parse_args()

    config = get_settings()
    clients = [c for c in build_clients(config) if c.supports_tools]
    if args.provider:
        clients = [c for c in clients if c.name == args.provider]
    if not clients:
        sys.exit("No tool-capable provider configured (set an API key or a local model).")
    cases = [c for c in CASES if not args.case or args.case in c.id]

    for client in clients:
        print(f"\n== {client.name}: {client.model}")
        passed, times = 0, []
        for case in cases:
            ok, detail, seconds = await run_case(case, client, config)
            passed += ok
            times.append(seconds)
            print(f"  {'✅' if ok else '❌'} {case.id:<18} {seconds:5.1f}s  {'' if ok else detail}")
        average = sum(times) / len(times)
        print(f"  → {passed}/{len(cases)} passed · average {average:.1f}s per message")
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
