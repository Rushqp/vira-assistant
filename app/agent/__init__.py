"""The assistant's brain: an LLM agent with typed tools (design: docs/AGENT_DESIGN.md).

- `core`    — the agent loop: model call → tool calls → results → final answer
- `tools/`  — what the agent can do (expenses, reminders, reports, dates, settings), each with
              argument validation and deterministic checks
- `actions` — undo log for everything the agent changed
- `context` — per-message context (time, dates table in both calendars)
- `prompt`  — the static system prompt
"""
