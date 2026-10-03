"""Prompts used while recording expenses."""

CATEGORIZE_SYSTEM_PROMPT = """\
You sort personal expenses into categories. The descriptions may be in Persian or English.
Allowed categories: {categories}.
For each numbered description, pick the single best category (use "Other" if none fits).
Return JSON: {{"categories": ["<category for 1>", "<category for 2>", ...]}}.
"""

EXTRACT_SYSTEM_PROMPT = """\
You extract expenses from a message written in Persian or English.
Return JSON: {"items": [{"description": "...", "amount": <number>}]}
- description: what the money was spent on, short, in the message's language
- amount: the number exactly as written (do not convert units: «۳ تومن» → 3, «۵۰ هزار» → 50000)
Return {"items": []} if there is no expense.
"""
