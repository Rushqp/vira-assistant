# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.7.0] - 2026-10-05

### Added
- ✅ **To-dos**: a list per day. Say what you need to do (*«فردا باید نون بخرم و قبض برق رو
  بدم»*) or use ✅ Today To-Dos → ➕ Add (one task per line; works without a model too)
  - A task without a time and without «یادم بنداز» / "remind me" is a to-do; otherwise a reminder
  - Tick with a tap (☐ / ☑) or by saying it (*«نون رو خریدم»*); rename, move to another day,
    delete; ↩️ Undo on every change
  - Unfinished tasks stay on today's list with their original day until done; ◀️ ▶️ show other
    days
  - Today's open tasks are in the morning briefing (sent now also when there are only to-dos),
    and the nightly report says how many were done and which stay open
- 📝 **Notes**: *«یادداشت کن …»* saves a note with a short title and 1–3 automatic tags
  - A long voice message that isn't a request is saved word for word as a note, with a title
    and a short summary
  - Find notes by asking (*«یادداشت‌های ماشین رو بیار»*, or a `#tag`); 📝 Notes lists them
    (pinned first) with 📌 pin, ✏️ edit (through the agent: *«شیر رو هم اضافه کن»*) and 🗑 delete
- 💾 **Backup**: `/backup` or ⚙️ Settings → 💾 Backup sends all data as one file (a consistent
  copy of the database, zipped); a copy comes every Friday at 23:30 (a missed one is sent at the
  next start; can be turned off)
  - **Restore**: send a backup file to the bot; it checks the file, shows what it contains, asks
    for confirmation, sends the current data first, then restores in place and updates older
    backups to the current version
- 8 agent tools (`add_todos`, `list_todos`, `update_todos`, `delete_todos`, `save_note`,
  `find_notes`, `update_note`, `delete_notes`); eval cases for to-dos and notes
- Migration `0007` (notes, to-dos)
- README: how to update the server

### Changed
- Every main-menu button works now; the "coming soon" placeholders are gone
- The agent is told how long a voice message was

### Fixed
- ⚙️ Settings → 🤖 AI model (and `/model`) did nothing when a local model was configured:
  listing the local models crashed. The menu now also opens when that list can't be read

## [0.6.0] - 2026-10-05

### Added
- 🎙 **Voice messages and audio files** (mp3, m4a, ogg, sent as music or as a file) are
  transcribed and then handled exactly like typed text: the agent, reminders, expenses, Excel
  files, and answers to the bot's own questions (`app/bot/middlewares/voice.py` turns them into
  text before routing)
  - The recognized text is shown first («🎙 …»), so a mistake is visible right away; a caption
    is kept in front of the transcript
  - The agent is told the text comes from speech (recognition errors are possible)
  - Up to 10 minutes and 20 MB per recording; round videos are not transcribed
- Speech engines with failover (`app/stt`), in `STT_PROVIDERS` order:
  - **Groq Whisper large-v3** (free with `GROQ_API_KEY`: about 8 hours of audio a day)
  - **Gemini** (free with `GEMINI_API_KEY`; audio converted to WAV with PyAV; up to 6 minutes)
  - **local faster-whisper** as the backup: `small` on `standard`, `large-v3-turbo` on `full`,
    none on `lite` / `remote`; downloaded to `data/models/whisper` the first time it is needed
  - Persian heard as another language is retried as Persian
  - A switch of engine is reported like a switch of AI model (🔁 / ✅ / ⚠️)
- New settings: `STT_PROVIDERS`, `GROQ_STT_MODEL`
- ⚙️ Settings shows the voice engines

### Changed
- Local Whisper defaults per profile (was tiny / base / small): only a backup now, since the
  small models hardly understand Persian
- Cooldowns and notices moved to `app/llm/failover.py`, shared by AI models and speech engines
- New dependency: `faster-whisper` (with PyAV); the Docker image grows by about 400 MB, models are
  downloaded only when needed

## [0.5.0] - 2026-10-04

### Added
- 📤 **Excel files from the chat** (no menu button: just ask). Built with openpyxl
  (`app/services/export.py`), sent as a Telegram document, English, dates in the selected
  calendar (Jalali as sortable `1405/07/12` text, Gregorian as real dates)
  - Expenses (`export_expenses` tool): any range («این ماه», «مهر», "October", «۱۴۰۵», from / to
    dates in either calendar, this / last week, month or year, all), categories and description
    filters, chosen columns; a sheet of every expense with a total row, plus summary sheets per
    category (share, pie chart), day, week or month (bar charts). Default: this month, with the
    category and daily summaries (monthly for ranges over two months)
  - Reminders (`export_reminders`): upcoming, today, tomorrow, this / next week or month, all, or
    dates; repeat, pending alerts, importance and status
  - Any table (`make_spreadsheet`): plans, schedules, lists, comparisons or a table from the
    conversation, written by the AI; numbers stay numbers («۱۲۰۰۰۰», "120,000", "15%"), phone
    numbers stay text, optional total row (years, dates and percentages are not added up)
  - Without a model, «اکسل …» / "export to Excel" still sends the expenses of the named period
- 🌙 **Nightly report** (default 22:00): today's expenses (total, categories, items) or a nudge
  to record forgotten ones, this month so far with the daily average, and tomorrow's reminders
  (important first)
- ⚙️ Settings → **☀️ Morning briefing** and **🌙 Nightly report**: on / off, preset times or
  any other time («۹:۳۰» is read as 21:30 for the nightly report); the agent can change them too
  («گزارش شبانه رو ساعت ۱۱ بفرست»), with ↩️ Undo
- Eval cases for Excel files and the nightly report time (`scripts/eval_agent.py`)

### Changed
- The 📤 Export Excel menu button is gone (files are asked for in the chat; the old button
  still works as a message)
- Daily messages are checked every 30 s against the times chosen in Settings, instead of a fixed
  cron time; one missed while offline is still sent within 4 hours of its time (same day)
- New dependency: `openpyxl`
- CSV export is not planned any more (decided in v0.5: xlsx only)

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
- 🔀 **Free AI models with failover** (`app/llm/providers.py`, catalog in `app/llm/models.py`):
  Gemini → Groq → Mistral → GitHub Models → OpenRouter → local model, in `LLM_PROVIDERS` order.
  A model that fails is paused and the next one answers: free quota used up waits for
  `Retry-After` or 1 min, 2 min, 4 min … (up to 30 min); a rejected key or unknown model 1 hour;
  other errors 30 s, 1 min … (up to 10 min)
  - Free models: Gemini Flash / Flash-Lite; GPT-OSS 120B / 20B, Llama 3.3 70B, Qwen 3.8 27B (Groq);
    Mistral Small / Medium / Large; GPT-4.1 mini, GPT-4.1, GPT-4o mini, GPT-5 mini (GitHub Models);
    OpenRouter's free router; every model pulled in the local Ollama
- 🤖 **AI model** screen (⚙️ Settings → 🤖 AI model, or `/model`): the order, the model answering
  now, paused models with the reason and the time they are tried again, and the keys that would
  add more free models. Choosing a model puts it first (the others stay as backups); ✨ Auto goes
  back to the configured order. The choice is saved and applied again after a restart
- 🔁 **Model notices**: when a model stops answering (free quota used up, key rejected, not
  reachable), Vira says which one answered instead and when the first one is tried again; it also
  tells when the model is back, and when no model is left and it works in basic mode. One notice
  per change (an outage is reported once, not on every message)
- New settings: `LLM_PROVIDERS`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `GROQ_API_KEY`, `GROQ_MODEL`,
  `MISTRAL_API_KEY`, `MISTRAL_MODEL`, `GITHUB_TOKEN`, `GITHUB_MODEL`, `OPENROUTER_API_KEY`,
  `OPENROUTER_MODEL`, `LOCAL_TOOLS`
- `scripts/eval_agent.py`: accuracy and latency of each configured model on real Persian / English
  cases (including reported failures), to choose models per hardware profile on the real server;
  `--all` measures every model of the 🤖 AI model menu
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
- ⚙️ Settings shows the AI model order (the chosen model first)

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

[0.7.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.7.0
[0.6.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.6.0
[0.5.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.5.0
[0.4.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.4.0
[0.3.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.3.0
[0.2.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.2.0
[0.1.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.1.0
