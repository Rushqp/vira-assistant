"""Tools the agent can call: a JSON schema for the model + a validated handler.

Handlers never trust the model. Arguments are validated (Pydantic), amounts and dates are
re-checked with the deterministic parsers, and problems are returned to the model as
{"error": ..., "hint": ...} so it can correct itself or ask the user (design §5).

Results reach the user as `Card`s rendered by the bot layer from real data, never from the
model's own text.
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import Calendar, Settings
from app.services.expenses import ExpenseService
from app.services.reminders import ReminderService
from app.services.settings import SettingsService

CardKind = Literal[
    "expenses_saved",
    "expenses_deleted",
    "expense_updated",
    "reminder_saved",
    "reminder_updated",
    "reminders_cancelled",
    "report",
    "settings",
    "file",
]


@dataclass
class Card:
    """What the user sees for one tool result (rendered by `app/bot/agent_ui.py`)."""

    kind: CardKind
    action_id: int | None = None  # for ↩️ Undo / ✏️ Edit
    data: dict = field(default_factory=dict)
    attachment: bytes | None = None  # "file" cards: the document to send


@dataclass
class Clarification:
    """The app must ask the user before finishing (e.g. thousand or million?)."""

    kind: Literal["amount_scale"]
    data: dict


@dataclass
class ToolOutcome:
    result: dict  # sent back to the model as JSON
    card: Card | None = None
    clarification: Clarification | None = None
    note: str = ""  # one line kept in the transcript, e.g. "[done: reminder #12 …]"


class ToolError(Exception):
    """A problem the model can fix (bad argument) or should ask the user about."""

    def __init__(self, error: str, hint: str = "") -> None:
        super().__init__(error)
        self.error = error
        self.hint = hint


@dataclass
class ToolContext:
    config: Settings
    calendar: Calendar
    now: datetime  # local, timezone-aware
    user_text: str
    expenses: ExpenseService
    reminders: ReminderService
    settings: SettingsService
    actions: Any  # ActionLog (imported lazily to avoid a cycle)

    @property
    def today(self) -> date:
        return self.now.date()

    @property
    def currency(self) -> str:
        return self.config.currency.value


class Args(BaseModel):
    """Base for tool arguments: lenient (numbers accepted as text, unknown keys ignored)."""

    model_config = ConfigDict(extra="ignore", coerce_numbers_to_str=True)


Handler = Callable[[Any, ToolContext], Awaitable[ToolOutcome]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON schema (kept simple: plain types, no $ref / anyOf)
    args_model: type[Args]
    handler: Handler

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def error(message: str, hint: str = "") -> ToolOutcome:
    result = {"error": message}
    if hint:
        result["hint"] = hint
    return ToolOutcome(result=result)


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self.tools = {tool.name: tool for tool in tools}
        self._schemas = [tool.schema() for tool in tools]

    def schemas(self) -> list[dict]:
        return self._schemas

    async def execute(self, name: str, raw_arguments: str, ctx: ToolContext) -> ToolOutcome:
        tool = self.tools.get(name)
        if tool is None:
            return error(f"unknown tool {name!r}", f"available: {', '.join(self.tools)}")
        try:
            data = json.loads(raw_arguments or "{}")
            if not isinstance(data, dict):
                raise ValueError("arguments must be a JSON object")
            args = tool.args_model.model_validate(data)
        except (ValueError, ValidationError) as exc:
            return error(f"invalid arguments for {name}: {exc}"[:500])
        try:
            outcome = await tool.handler(args, ctx)
        except ToolError as exc:
            return error(exc.error, exc.hint)
        except Exception:  # never let one tool crash the conversation
            logger.exception("Tool {} failed", name)
            return error(f"{name} failed because of an internal error")
        logger.info("Tool {} → {}", name, json.dumps(outcome.result, ensure_ascii=False)[:300])
        return outcome


def build_registry() -> ToolRegistry:
    from app.agent.tools.expenses import EXPENSE_TOOLS
    from app.agent.tools.files import FILE_TOOLS
    from app.agent.tools.general import GENERAL_TOOLS
    from app.agent.tools.reminders import REMINDER_TOOLS

    return ToolRegistry([*EXPENSE_TOOLS, *REMINDER_TOOLS, *GENERAL_TOOLS, *FILE_TOOLS])
