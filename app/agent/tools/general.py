"""Reports, date conversion, calculator and settings tools."""

from app.agent.context import date_line
from app.agent.tools import Args, Card, Tool, ToolContext, ToolError, ToolOutcome
from app.agent.tools.common import PERIODS, parse_date_arg
from app.config import Calendar
from app.services.reports import ReportService
from app.services.settings import KEY_BRIEFING, KEY_CALENDAR
from app.services.tools import CalcError, calculate, format_number

# --- get_report ---


class ReportArgs(Args):
    period: str = "today"


async def get_report(args: ReportArgs, ctx: ToolContext) -> ToolOutcome:
    if args.period not in PERIODS:
        raise ToolError(f"unknown period {args.period!r}", f"use one of: {', '.join(PERIODS)}")
    kind, offset = PERIODS[args.period]
    report = await ReportService(ctx.expenses).build(kind, ctx.today, ctx.calendar, offset)
    return ToolOutcome(
        result={
            "period": {"from": report.start.isoformat(), "to_exclusive": report.end.isoformat()},
            "total": report.total,
            "count": len(report.expenses),
            "previous_period_total": report.previous_total,
            "by_category": [
                {"category": c.category.name, "total": c.total, "share": round(c.share, 3)}
                for c in report.by_category
            ],
            "largest": (
                {"description": report.largest.description, "amount": report.largest.amount}
                if report.largest
                else None
            ),
            "shown_to_user": True,
        },
        card=Card("report", None, {"kind": kind, "offset": offset}),
    )


# --- convert_date ---


class ConvertDateArgs(Args):
    date_text: str


async def convert_date(args: ConvertDateArgs, ctx: ToolContext) -> ToolOutcome:
    day = parse_date_arg(args.date_text, ctx.today)
    if day is None:
        raise ToolError(f"could not understand {args.date_text!r}", "e.g. '1405-08-15', '۱۵ آبان'")
    return ToolOutcome(result={"date": date_line(day), "days_from_today": (day - ctx.today).days})


# --- calculate ---


class CalculateArgs(Args):
    expression: str


async def run_calculate(args: CalculateArgs, ctx: ToolContext) -> ToolOutcome:
    try:
        value = calculate(args.expression)
    except CalcError as exc:
        raise ToolError(f"cannot calculate {args.expression!r}: {exc}") from exc
    return ToolOutcome(result={"expression": args.expression, "result": format_number(value)})


# --- update_settings ---


class SettingsArgs(Args):
    calendar: str | None = None
    morning_briefing: bool | None = None


async def update_settings(args: SettingsArgs, ctx: ToolContext) -> ToolOutcome:
    previous: dict[str, str | None] = {}
    changes: dict[str, str] = {}
    if args.calendar is not None:
        try:
            calendar = Calendar(args.calendar.lower())
        except ValueError as exc:
            raise ToolError("calendar must be 'jalali' or 'gregorian'") from exc
        previous[KEY_CALENDAR] = await ctx.settings.get(KEY_CALENDAR)
        changes[KEY_CALENDAR] = calendar.value
    if args.morning_briefing is not None:
        previous[KEY_BRIEFING] = await ctx.settings.get(KEY_BRIEFING)
        changes[KEY_BRIEFING] = "on" if args.morning_briefing else "off"
    if not changes:
        raise ToolError("nothing to change", "settings: calendar, morning_briefing")
    for key, value in changes.items():
        await ctx.settings.set(key, value)
    summary = ", ".join(f"{k}={v}" for k, v in changes.items())
    action = await ctx.actions.record(
        "settings_updated", {"previous": previous}, f"settings changed: {summary}"
    )
    return ToolOutcome(
        result={"changed": changes},
        card=Card("settings", action.id, {"changes": changes}),
        note=f"[done: settings changed — {summary}]",
    )


# --- Schemas ---

GENERAL_TOOLS = [
    Tool(
        name="get_report",
        description="Show the user an expense report (totals, categories, largest expense).",
        parameters={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": list(PERIODS),
                }
            },
            "required": ["period"],
        },
        args_model=ReportArgs,
        handler=get_report,
    ),
    Tool(
        name="convert_date",
        description="Convert a date between Jalali and Gregorian and get its weekday.",
        parameters={
            "type": "object",
            "properties": {
                "date_text": {
                    "type": "string",
                    "description": "e.g. '1405-08-15', '2026-11-06', '۱۵ آبان'",
                }
            },
            "required": ["date_text"],
        },
        args_model=ConvertDateArgs,
        handler=convert_date,
    ),
    Tool(
        name="calculate",
        description="Evaluate an arithmetic expression exactly (+ - * / % ^ and parentheses).",
        parameters={
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
        args_model=CalculateArgs,
        handler=run_calculate,
    ),
    Tool(
        name="update_settings",
        description="Change the user's settings: calendar (jalali/gregorian), morning briefing.",
        parameters={
            "type": "object",
            "properties": {
                "calendar": {"type": "string", "enum": ["jalali", "gregorian"]},
                "morning_briefing": {"type": "boolean"},
            },
        },
        args_model=SettingsArgs,
        handler=update_settings,
    ),
]
