"""The agent loop: model → tool calls → results → … → short final answer.

One user message = up to `MAX_ROUNDS` model calls. Tool results go back to the model so it can
correct mistakes or ask the user. What the user sees about actions comes from the tool results
(cards), never from the model's own claims; a claim without a tool call gets one corrective
retry (pattern from majordomo, see docs/AGENT_DESIGN.md §3).
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.agent.context import build_context
from app.agent.prompt import build_system_prompt
from app.agent.tools import Card, Clarification, ToolContext, ToolRegistry
from app.llm.client import ChatMessage, LLMError

MAX_ROUNDS = 4

# "I've saved it / it was cancelled / ثبت شد / کنسل کردم ..." said without calling any tool.
_DONE_EN = (
    r"(?:saved|recorded|added|created|set|scheduled|cancel+ed|deleted|removed|updated"
    r"|sent|exported|attached)"
)
# Only things the assistant manages: "The Eiffel Tower was created in 1889" is not a claim.
_THINGS = (
    r"(?:it|this|that|they|reminders?|expenses?|alarms?|files?|spreadsheets?"
    r"|(?:your|the)\s+(?:reminders?|expenses?|alarms?|items?|records?|settings?|files?"
    r"|excel(?:\s+file)?|spreadsheets?))"
)
CLAIMS = re.compile(
    rf"\bi(?:'ve| have)?\s+(?:just\s+)?{_DONE_EN}\b"
    rf"|\b{_THINGS}\s+(?:has been|have been|is|was|are|were)\s+(?:now\s+)?{_DONE_EN}\b"
    r"|(?:ثبت|ذخیره|اضافه|ساخته|تنظیم|کنسل|لغو|حذف|پاک|عوض|تغییر)\s*(?:شد|کردم)"
    r"|(?:فرستادم|ارسال\s*کردم)",
    re.IGNORECASE,
)
CORRECTION = (
    "You did not call any tool in this turn, so nothing was saved, changed or cancelled. "
    "If the user asked for an action, call the right tool now. Otherwise answer without "
    "claiming to have done anything."
)


class AgentUnavailable(Exception):
    """No tool-capable model could be reached: use the rule-based fallback."""


@dataclass
class AgentResult:
    text: str = ""
    cards: list[Card] = field(default_factory=list)
    clarification: Clarification | None = None
    notes: list[str] = field(default_factory=list)  # kept in the transcript for references
    provider: str = ""


class Agent:
    def __init__(self, llm: Any, registry: ToolRegistry) -> None:
        self.llm = llm  # ProviderChain (or any object with `respond`)
        self.registry = registry

    async def run(
        self,
        ctx: ToolContext,
        history: list[ChatMessage],
        text: str,
        on_text: Callable[[str], Any] | None = None,
        hint: str = "",
    ) -> AgentResult:
        categories = [c.name for c in await ctx.expenses.categories()]
        system = build_system_prompt(categories, ctx.config.day_times)
        context = build_context(ctx.now, ctx.calendar, ctx.currency)
        user = f"{context}\n{hint}\n\n{text}" if hint else f"{context}\n\n{text}"
        messages: list[ChatMessage] = [
            {"role": "system", "content": system},
            *history,
            {"role": "user", "content": user},
        ]
        result = AgentResult()
        tools_ran = corrected = False
        shown: list[str] = []  # text already streamed to the user

        async def relay(piece: str) -> None:
            shown.append(piece)
            if on_text:
                outcome = on_text(piece)
                if hasattr(outcome, "__await__"):
                    await outcome

        for _ in range(MAX_ROUNDS):
            try:
                response = await self.llm.respond(messages, self.registry.schemas(), relay)
            except LLMError as exc:
                if shown:
                    raise  # part of an answer is on screen: report the error, don't fall back
                if not tools_ran:
                    raise AgentUnavailable(str(exc)) from exc
                logger.warning("Agent stopped after tools ran: {}", exc)
                break
            result.provider = response.provider

            if not response.tool_calls:
                answer = response.content.strip()
                if not tools_ran and not corrected and not shown and CLAIMS.search(answer):
                    corrected = True
                    logger.warning("Model claimed an action without a tool: {!r}", answer[:120])
                    messages += [
                        {"role": "assistant", "content": answer},
                        {"role": "user", "content": CORRECTION},
                    ]
                    continue
                result.text = answer
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": response.content or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.name, "arguments": call.arguments or "{}"},
                        }
                        for call in response.tool_calls
                    ],
                }
            )
            for call in response.tool_calls:
                outcome = await self.registry.execute(call.name, call.arguments, ctx)
                tools_ran = True
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(outcome.result, ensure_ascii=False),
                    }
                )
                if outcome.card:
                    result.cards.append(outcome.card)
                if outcome.note:
                    result.notes.append(outcome.note)
                if outcome.clarification:
                    result.clarification = outcome.clarification
            if result.clarification:
                break  # the app asks the user (buttons) before anything else happens
        return result
