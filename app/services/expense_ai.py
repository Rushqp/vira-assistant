"""LLM help for expenses: choosing categories and extracting items when the rules find no amount.

Both degrade gracefully: on any LLM error they return None and the caller falls back.
"""

import asyncio

from loguru import logger

from app.llm.client import LLMClient, LLMError
from app.llm.prompts.expense import CATEGORIZE_SYSTEM_PROMPT, EXTRACT_SYSTEM_PROMPT
from app.llm.schemas import EXPENSE_EXTRACT, expense_categories_schema

CATEGORIZE_TIMEOUT = 40
EXTRACT_TIMEOUT = 60


async def categorize(
    llm: LLMClient, descriptions: list[str], names: list[str]
) -> list[str | None] | None:
    """A category name (from `names`) for each description, or None if the LLM can't help."""
    numbered = "\n".join(f"{i + 1}. {d}" for i, d in enumerate(descriptions))
    try:
        data = await asyncio.wait_for(
            llm.complete_json(
                [
                    {
                        "role": "system",
                        "content": CATEGORIZE_SYSTEM_PROMPT.format(categories=", ".join(names)),
                    },
                    {"role": "user", "content": numbered},
                ],
                expense_categories_schema(names),
                name="categories",
            ),
            CATEGORIZE_TIMEOUT,
        )
    except (LLMError, TimeoutError) as exc:
        logger.info("Categories by keywords only (LLM unavailable: {})", exc)
        return None
    picked = data.get("categories")
    if not isinstance(picked, list):
        return None
    result = [p if p in names else None for p in picked[: len(descriptions)]]
    return result + [None] * (len(descriptions) - len(result))


async def extract(llm: LLMClient, text: str) -> list[tuple[str, float]] | None:
    """[(description, amount as written)] or None."""
    try:
        data = await asyncio.wait_for(
            llm.complete_json(
                [
                    {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                EXPENSE_EXTRACT,
                name="expenses",
            ),
            EXTRACT_TIMEOUT,
        )
    except (LLMError, TimeoutError) as exc:
        logger.info("Expense extraction by LLM failed: {}", exc)
        return None
    items = []
    for item in data.get("items") or []:
        try:
            amount = float(item["amount"])
        except (KeyError, TypeError, ValueError):
            continue
        if amount > 0:
            items.append((str(item.get("description") or "").strip(), amount))
    return items or None
