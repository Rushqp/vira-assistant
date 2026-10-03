"""LLM help for reminders: importance classification and extraction when the rules fail.

Both functions degrade gracefully: on any LLM error they return a rule-based answer / None.
"""

import asyncio
from datetime import date, datetime, time

from loguru import logger

from app.llm.client import LLMClient, LLMError
from app.llm.prompts.reminder import EXTRACT_SYSTEM_PROMPT, IMPORTANCE_SYSTEM_PROMPT
from app.llm.schemas import IMPORTANCE, REMINDER_EXTRACT
from app.services.reminders import guess_important

# Keep the confirmation snappy even on slow hardware.
IMPORTANCE_TIMEOUT = 30
EXTRACT_TIMEOUT = 60


async def classify_importance(llm: LLMClient, subject: str) -> bool:
    try:
        data = await asyncio.wait_for(
            llm.complete_json(
                [
                    {"role": "system", "content": IMPORTANCE_SYSTEM_PROMPT},
                    {"role": "user", "content": subject},
                ],
                IMPORTANCE,
                name="importance",
            ),
            IMPORTANCE_TIMEOUT,
        )
        return bool(data.get("important"))
    except (LLMError, TimeoutError) as exc:
        logger.info("Importance by keywords (LLM unavailable: {})", exc)
        return guess_important(subject)


async def extract_reminder(
    llm: LLMClient, text: str, now: datetime
) -> tuple[str, date | None, time | None, bool] | None:
    """(subject, date, time, important) or None if the LLM can't help."""
    prompt = EXTRACT_SYSTEM_PROMPT.format(
        today=now.date().isoformat(), weekday=f"{now:%A}", time=f"{now:%H:%M}"
    )
    try:
        data = await asyncio.wait_for(
            llm.complete_json(
                [{"role": "system", "content": prompt}, {"role": "user", "content": text}],
                REMINDER_EXTRACT,
                name="reminder",
            ),
            EXTRACT_TIMEOUT,
        )
    except (LLMError, TimeoutError) as exc:
        logger.info("Reminder extraction by LLM failed: {}", exc)
        return None
    try:
        day = date.fromisoformat(data["date"]) if data.get("date") else None
        clock = time.fromisoformat(data["time"]) if data.get("time") else None
    except (TypeError, ValueError):
        return None
    subject = str(data.get("subject") or "").strip()
    if day is None and clock is None:
        return None
    return subject, day, clock, bool(data.get("important"))
