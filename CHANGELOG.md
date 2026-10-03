# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-10-04

### Added
- ⏰ **Reminders** from free text in Persian or English ("remind me …", «… یادم بنداز») or the
  ⏰ New Reminder form
  - Rule-based date/time parser (`app/core/parsers`): today / tomorrow / weekdays, Jalali and
    Gregorian dates («۱۵ مهر», "Oct 7", `1405/07/15`), times («ساعت ۲ و نیم», «ربع به ۳», "2pm",
    "half past 7"), parts of the day, "in 10 minutes", "1 hour before", "the night before"
  - Separate event and notification times: «فردا ساعت ۲ دکتر دارم، صبح یادم بنداز»
  - Asks what is missing: am/pm for hours like "2", the time, and when to notify (multi-select:
    at the time, 15 min / 1 hour before, morning of the day, night before, or a custom time)
  - Repeats: daily, weekly, monthly (monthly follows the selected calendar, e.g. every 5th of the
    Jalali month)
  - ⭐ Importance decided by the LLM (keyword fallback), editable before saving
  - LLM extraction (JSON schema) when the rules can't find a date/time
  - Confirmation card with Save / ⭐ / Edit / Cancel
  - Notifications with ✅ Done, ⏰ +10 min, ⏰ +1 hour; alerts missed while offline are sent late
  - 📋 Reminders: list, view, edit, delete
- ☀️ **Morning briefing** (`MORNING_BRIEFING_TIME`, default 08:00): today's reminders, important ones
  first; toggle in ⚙️ Settings; a missed briefing is sent after a morning restart
- 🗂 **Previous chats**: list (10 per page), continue a chat (shows the last 3 exchanges), delete;
  the newest `CHAT_KEEP` (default 20) chats are kept; `/chats` command
- Number words in Persian and English («صد و پنجاه», "twenty five") and Arabic letter unification
- Settings: `MORNING_TIME`, `NOON_TIME`, `AFTERNOON_TIME`, `EVENING_TIME`, `NIGHT_TIME`,
  `MORNING_BRIEFING_TIME`, `CHAT_KEEP`
- Pressing a menu button or sending a command leaves any unfinished form
- Migrations `0003` (chat titles, AUTOINCREMENT ids) and `0004` (reminders, reminder alerts)

### Changed
- Main menu: first row is now 💬 New Chat · 🗂 Chats · ⏰ New Reminder
- Chats keep their full history (up to 100 messages); only `CHAT_MEMORY` messages go to the model

## [0.2.0] - 2026-10-03

### Added
- Ollama service in Docker Compose plus an `ollama-init` service that pulls the model for the selected
  `PROFILE` on first start. The Ollama port is never exposed.
- `COMPOSE_PROFILES=ollama` switch: leave it empty with `PROFILE=remote` to use any OpenAI-compatible API
- OpenAI-compatible LLM client (`app/llm/client.py`) with clear errors for unreachable / missing models
- 💬 Chat: free text is answered by the LLM in the user's language (Persian or English), streamed
  into the message as it is generated
- Short-term memory: the last `CHAT_MEMORY` messages (default 10) are sent as context
- 💬 New Chat button and `/new` start a fresh conversation
- Built-in tools without the LLM: calculator (Persian digits, `×`, `÷`, `^`) and "what's today's
  date?" in both calendars
- Persian month and weekday names; Persian replies use Persian digits
- New settings: `LLM_TIMEOUT`, `CHAT_MEMORY`, `OLLAMA_KEEP_ALIVE`
- Database tables `chat_sessions` and `chat_history` (migration `0002`)
- Unknown commands, voice messages and media get a clear reply

### Changed
- `PROFILE=remote` now requires `LLM_MODEL`
- CI actions updated to their current major versions

## [0.1.0] - 2026-10-03

### Added
- Project skeleton (Python 3.12, aiogram 3) with a readable layout: `bot` / `services` / `db` / `utils`
- Configuration via `.env` (pydantic-settings) with hardware profiles `lite` / `standard` / `full` / `remote`
- `/start`, `/help`, `/menu`, `/cancel` commands and the English main menu (reply keyboard)
- Owner-only middleware: updates from anyone other than `OWNER_ID` are ignored
- SQLite + SQLAlchemy 2 (async) with Alembic migrations applied automatically on startup
- Settings screen with a Jalali / Gregorian calendar toggle (persisted) and read-only system info
- "Coming in vX.Y" placeholders for features planned in later versions
- Docker image (non-root) and Docker Compose setup
- GitHub Actions CI: ruff lint + format check, pytest, Docker image build
- Bilingual (English / Persian) README

[0.3.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.3.0
[0.2.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.2.0
[0.1.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.1.0
