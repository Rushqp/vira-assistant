"""JSON schemas for structured LLM output (kept small: small local models follow them better)."""

REMINDER_EXTRACT = {
    "type": "object",
    "properties": {
        "subject": {
            "type": "string",
            "description": "What to remind about, in the user's language",
        },
        "date": {"type": ["string", "null"], "description": "Gregorian date YYYY-MM-DD or null"},
        "time": {"type": ["string", "null"], "description": "24-hour time HH:MM or null"},
        "important": {"type": "boolean"},
    },
    "required": ["subject", "date", "time", "important"],
}

IMPORTANCE = {
    "type": "object",
    "properties": {"important": {"type": "boolean"}},
    "required": ["important"],
}

EXPENSE_EXTRACT = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["description", "amount"],
            },
        }
    },
    "required": ["items"],
}


def expense_categories_schema(names: list[str]) -> dict:
    """One category per description, restricted to the existing category names."""
    return {
        "type": "object",
        "properties": {"categories": {"type": "array", "items": {"type": "string", "enum": names}}},
        "required": ["categories"],
    }
