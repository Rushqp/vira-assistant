# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.4.0] - 2026-10-04

### Added
- 🧠 **AI agent** (`app/agent`, design in `docs/AGENT_DESIGN.md`): every free-text message is
  understood by a model that calls typed tools, instead of keyword rules
  - Understands any phrasing, typos and colloquial Persian, several requests in one message, and
    follow-ups that refer to earlier messages («تایم دکتر رو کنسل کن», «نه، ماست ۲۵۰ هزار بود»)
  - 12 tools: add / list / update / delete expenses, create / list / update / cancel reminders,
    reports, Jalali ↔ Gregorian dates, calculator, settings
  - Every tool call is validated; amounts and dates are re-checked with the deterministic parsers;
    errors go back to the model so it can fix them or ask the user
  - Acts directly and shows a card for each real result with **↩️ Undo** and **✏️ Edit**; undo
    survives restarts (`agent_actions`, migration `0006`)
  - Asks only when needed: amounts without thousand / million («۳ تومن») still get buttons (typing
    «هزار» / «میلیون» works too); a reminder without a notification time notifies at the start and
    offers buttons for earlier alerts
  - A claim of an action without a tool call gets one corrective retry
  - The model never computes dates: each message carries a dates table in both calendars
- 🔀 **Free AI providers with failover** (`app/llm/providers.py`): Gemini → Groq → GitHub Models →
  local model, in `LLM_PROVIDERS` order; providers that fail or hit their free quota are paused
  (`Retry-After`, growing back-off) and the next one answers
- New settings: `LLM_PROVIDERS`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `GROQ_API_KEY`, `GROQ_MODEL`,
  `GITHUB_TOKEN`, `GITHUB_MODEL`, `LOCAL_TOOLS`
- `scripts/eval_agent.py`: accuracy and latency of each configured model on real Persian / English
  cases (including reported failures), to choose models per hardware profile on the real server
- 💰 **Expenses**: several items in one message, quantities («۱۰ لیتر»), past days («دیروز»,
  «شنبه»), amount parser («۲ و نیم میلیون», «دو میلیون و پونصد» = 2,500,000, `100k`, `1.2m`,
  toman / rial)
- 🏷 **Categories**: 13 defaults; chosen by the AI (learned corrections first, keywords as a
  fallback); corrections are **learned**; add / delete in ⚙️ Settings → 🏷 Categories
- 📊 **Reports**: today (each expense with 🗑), week and month following the selected calendar
  (Jalali month / Saturday-first week, or Gregorian / Monday-first): total, comparison with the same
  days of the previous period, daily average, per-category text bars, largest expense; ◀️ ▶️
- Migrations `0005` (categories, learned keywords, expenses) and `0006` (agent actions)

### Changed
- Local models per profile: `standard` → `qwen3:4b`, `full` → `qwen3:8b` (native tool calling);
  `lite` keeps `gemma3:1b` for chat only
- `PROFILE=remote` works with just an API key (or a custom `LLM_MODEL` as before)
- The v0.3 rule-based understanding is kept as the fallback when no tool-capable model is reachable
- ⚙️ Settings shows the AI provider chain

### Fixed
- Reported: «یک یاد اوری تنظیم کن برای ۵ دقیقه دیگه …» went to the chat
- Reported: «امروز ۳ خرید کردم …» asked "3 thousand or 3 million?" for the count «۳»
- Reported: a reminder could not be cancelled by a follow-up message
- Number words: «دو میلیون و پونصد» now means 2,500,000 (was 2,000,500); a scale word without a
  number («میلیون‌ها») is no longer turned into 1000000

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
  - Many phrasings recognised: «یادآوری تنظیم کن», «یاد اوری» (without madda), «آلارم بذار»,
    "set a reminder", and, when a time is given, «خبرم کن», «بیدارم کن», "wake me up"
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

[0.4.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.4.0
[0.3.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.3.0
[0.2.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.2.0
[0.1.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.1.0
