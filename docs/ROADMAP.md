# Vira Assistant — Roadmap & Architecture

> A personal AI assistant for daily tasks, running on a low-spec Linux server, controlled through a Telegram bot with a button menu.
> Repository: `github.com/rushqp/vira-assistant` (public) · Document status: **Approved**

---

## 1. Goals

A single-user assistant that, via Telegram (text, buttons, voice), can:

- Answer **simple questions**
- Create **reminders** and notify on time — e.g. *"I have a doctor's appointment tomorrow at 2, remind me in the morning"*
- Log **expenses** — e.g. *"Paid 3 (million) toman for groceries, and 10 liters of fuel cost 100 thousand"*
- Produce daily / weekly / monthly **reports** and **Excel** files (asked for in the chat)
- Keep **notes and daily to-dos**
- Transcribe **voice messages** and process them like text
- Run fully **locally** (LLM + speech-to-text) and start on any device with **Docker**

**Everything is English** — bot UI (buttons, messages), code, docs and repository structure.
The assistant **understands Persian and English input** (text and voice) and answers in the language the user writes in.
Dates are shown in **Gregorian or Jalali (Shamsi)** — switchable by the user in Settings.

---

## 2. Key Decisions (approved)

| Topic | Decision |
|---|---|
| Hosting | Anywhere; the host's network is assumed to reach Telegram (optional proxy in `.env`) |
| Deployment | **Docker Compose** |
| AI | **Free API providers first** (Gemini → Groq → Mistral → GitHub Models → OpenRouter), **local Ollama** as fallback; all OpenAI-compatible, order in `.env`; the model can be switched in the bot (🤖 AI model) and the user is told when the answering model changes (decided in v0.4) |
| Hardware | **Selectable profiles**: `lite` / `standard` / `full` (+ `remote`) |
| Language processing | **AI agent with typed tools** (v0.4); deterministic parsers validate amounts/dates and remain the fallback when no model is reachable — see `docs/AGENT_DESIGN.md` |
| Users | **Single-user** (only `OWNER_ID` is allowed) |
| Extras | Voice → text, Excel files from the chat (xlsx only, decided in v0.5), full basic-assistant feature set |
| UI language | **English** (all buttons and bot messages) |
| Input language | **Persian + English** (text and voice); replies follow the user's language |
| Calendar | **Gregorian + Jalali**, user-switchable in Settings |
| Versioning | Every version gets its own Git tag + GitHub Release |

---

## 3. High-Level Architecture

> Since v0.4 the understanding layer is an **AI agent**; the full design, research and trade-offs
> are in [`AGENT_DESIGN.md`](AGENT_DESIGN.md).

```
                 ┌──────────────────────────┐
                 │   User in Telegram       │
                 │  text / buttons / voice  │
                 └────────────┬─────────────┘
                              │ Long polling (no public IP / SSL needed)
                              ▼
┌──────────────────────── docker-compose ────────────────────────────────┐
│  ┌─────────────── bot (Python 3.12 / aiogram 3) ───────────────────┐   │
│  │  handlers ──► [ voice? ] ──► stt (faster-whisper, v0.6)          │   │
│  │      │                                                            │   │
│  │      ▼                                                            │   │
│  │  agent: system prompt + transcript + [dates table fa/en] + text   │   │
│  │      │                                                            │   │
│  │      ▼                                                            │   │
│  │  provider chain ── Gemini → Groq → Mistral → GitHub → … → local ──┼─► free APIs
│  │      │                         (failover, cooldowns)       └──────┼─► ollama
│  │      ▼                                                            │   │
│  │  typed tools ── validated by deterministic parsers (dates, amounts)│  │
│  │      ▼                                                            │   │
│  │  services: reminders · expenses · reports · settings · chat       │   │
│  │      ▼                          ▲                                 │   │
│  │  SQLite (volume) ◄──── scheduler (APScheduler, no AI needed)      │   │
│  │      ▼                                                            │   │
│  │  result cards with ↩️ Undo / ✏️ Edit                               │   │
│  │                                                                   │   │
│  │  no model reachable → rule-based pipeline (v0.3) as fallback      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│  ┌────────── ollama ──────────┐     volumes: ./data  ./models            │
│  │ model per profile          │     (Ollama port is never exposed)       │
│  └────────────────────────────┘                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Design principles:** the model decides, the app verifies and acts; cards show only real results;
the model never does date or currency arithmetic; reminders never depend on a model.

---

## 4. Tech Stack

| Area | Tool | Purpose |
|---|---|---|
| Language | Python 3.12 | All bot logic |
| Telegram bot | **aiogram 3** | Handlers, Reply/Inline keyboards, FSM for multi-step forms |
| Local LLM | **Ollama** | CPU model inference; OpenAI-compatible API |
| LLM client | `openai` SDK (custom `base_url`) | One client per provider (Gemini, Groq, GitHub Models, Ollama, OpenRouter …) + failover chain |
| Agent | OpenAI-style tool calling + Pydantic validation | Typed tools; arguments re-checked by deterministic parsers |
| Speech-to-text | Free **Groq Whisper large-v3** → **Gemini** (audio input) → local **faster-whisper** (CTranslate2, int8) | Persian + English voice transcription, with failover like the AI models (v0.6) |
| Audio conversion | PyAV (bundled FFmpeg, comes with faster-whisper) | Telegram OGG/Opus → WAV for Gemini; no system packages |
| Scheduling | **APScheduler** (in-memory) | A 20-second job sends due alerts stored in SQLite (the DB is the source of truth, so nothing is lost on restart) + daily jobs |
| Database | **SQLite** + SQLAlchemy 2 (async, aiosqlite) | No extra service; single file on a volume |
| Migrations | Alembic | Schema changes across versions without data loss |
| Dual calendar | **jdatetime** + `zoneinfo` (Asia/Tehran) | Gregorian ↔ Jalali input/output; display follows user setting |
| Excel | **openpyxl** | Excel files of expenses, reminders and any table (v0.5) |
| Config | pydantic-settings + `.env` | Tokens and model selection; never committed |
| Logging | loguru | Lightweight rotating logs |
| Testing | pytest + pytest-asyncio | fa/en parser and service tests |
| Code quality | ruff | Lint + format |
| CI | GitHub Actions | Lint + tests + image build on each push |
| Image registry | GHCR (optional) | `ghcr.io/rushqp/vira-assistant:<version>` |

---

## 5. Hardware Profiles

Selected with one variable: `PROFILE=lite | standard | full | remote` (or override `LLM_MODEL` /
`STT_MODEL`). With a free API key the agent runs on the API in every profile; the local model is
the fallback (or the brain, without keys).

| Profile | Suggested RAM | Local model | Local Whisper (voice backup) | Without an API key |
|---|---|---|---|---|
| `lite` | 2 GB | `gemma3:1b` (chat only) | none | rule-based understanding + local chat, no voice |
| `standard` | 4 GB | `qwen3:4b` (agent, tools) | `small` | local agent (slow on CPU) |
| `full` | 8 GB+ | `qwen3:8b` (agent, tools) | `large-v3-turbo` | local agent |
| `remote` | — | — | — | needs an API key or a custom `LLM_MODEL` |

- Models are pulled automatically on first start (`ollama pull` in an init service).
- STT can be disabled entirely with `STT_ENABLED=false`. Voice uses the free APIs first (Groq
  Whisper, then Gemini); local Whisper is only the backup and downloads when first needed
  (decided in v0.6: tiny / base models hardly understand Persian).
- `scripts/eval_agent.py` benchmarks accuracy and latency of every configured model on real
  Persian/English cases; run it on the target server before changing defaults.

---

## 6. Features (Modules)

### 6.1 Chat (Q&A)
- Answers simple questions in **Persian or English** using the local LLM with short-term memory (last 10 messages)
- **New Chat** button clears the conversation context and starts a fresh session
- **Previous chats** (🗂 Chats): list the newest 20 chats, continue one (recap of the last 3 exchanges) or delete it
- Built-in tools without LLM: calculator, Gregorian ↔ Jalali conversion, "what's today's date?" (in both calendars)

### 6.2 Reminders
- Create from free text or a step-by-step form
- **Separate event time and notify time**: "doctor tomorrow at 2, remind me in the morning" → event 14:00, notify 09:00
- Recurring: daily, weekly, monthly (e.g. "every Saturday at 8"); monthly follows the selected calendar
- Missing details are asked: am/pm for hours 1–12, the time, and **when to notify** if not said
  (multi-select: at the time / 15 min / 1 hour before / morning of the day / night before / custom)
- **⭐ Important** decided by the LLM (keyword fallback), editable on the confirmation card
- Notification buttons: [✅ Done] [⏰ +10 min] [⏰ +1 hour]
- List / edit / delete
- Morning briefing (08:00): today's reminders, important ones first

### 6.3 Expenses
- Multiple expenses in one message → multiple records
- Amount, category, description, quantity and unit (e.g. 10 liters)
- Default categories (13): Groceries, Food, Restaurant, Home, Fuel, Transport, Bills, Health, Clothing,
  Education, Gifts, Leisure, Other — add / delete in Settings
- Category chosen by keywords → LLM → Other; **corrections are learned** for next time
- Amount without thousand / million is **always asked** (buttons)
- Undo right after saving; delete from the day report
- **Always confirm before saving**, showing the interpreted amount

### 6.4 Reports
- Today / yesterday / week / month / custom range — month boundaries follow the selected calendar (Jalali month or Gregorian month)
- Total + per-category breakdown + largest expense
- **Excel** files from the chat, no menu button (v0.5): expenses (any range, filters, totals per
  category / day / week / month with charts), reminders, or any table the assistant writes.
  CSV was dropped (decided in v0.5)
- Automatic nightly report at a configurable time (today's expenses + tomorrow's reminders) — v0.5
- Optional morning briefing: today's tasks and reminders (reminders part done in v0.3)

### 6.5 Notes & To-Dos — v0.7
- Quick notes with automatic tags and search; a long voice message is kept word for word
  with a title and a short summary; pin, edit, delete
- Daily to-do list with checkboxes; unfinished tasks stay on today's list (with their day)
  until done; also in the morning briefing and the nightly report
- A task without a time and without "remind me" is a to-do, otherwise a reminder (decided
  in v0.7)

### 6.6 Voice (STT) — v0.6
- Voice messages and audio files → text → same pipeline as text messages (also as the answer
  to a form's question); round videos are not transcribed
- Recognized text is shown back to the user for transparency («🎙 …»)
- Engines with failover and switch notices: Groq Whisper large-v3 → Gemini → local
  faster-whisper; up to 10 minutes per recording
- Replies stay text (voice replies were not wanted for now)

### 6.7 Settings
- **Calendar: Gregorian / Jalali** (affects all dates in messages, reports and exports)
- Nightly report and morning briefing: on/off and time (v0.5)
- Active model (read-only display), category management
- Backup: send the database file to the owner (`/backup`, ⚙️ Settings → 💾 Backup, every
  Friday night); sending a backup file back restores it after a confirmation (v0.7)

---

## 7. Main Menu (Reply Keyboard)

```
┌──────────────┬───────────────┬──────────────┐
│ 💬 New Chat   │   🗂 Chats     │ ⏰ New Reminder│
├──────────────┼───────────────┼──────────────┤
│ 💰 Add Expense│ 📊 Today Report│ 📅 Month Report│
├──────────────┼───────────────┼──────────────┤
│ 📋 Reminders  │ ✅ Today To-Dos │ 📝 Notes      │
├──────────────┴───────────────┴──────────────┤
│                  ⚙️ Settings                  │
└─────────────────────────────────────────────┘
```

- **New Chat** clears the conversation context and starts a fresh Q&A session; **Chats** continues an older one.
- Each button either opens a multi-step form (FSM) or shows a result directly.
- Excel files have no button (removed in v0.5): they are asked for in the chat.
- The user can send **free text or voice (Persian or English) at any time** without pressing a button.
- Per-item actions use **Inline Keyboards** under each message.
- Commands: `/start` `/help` `/menu` `/new` `/chats` `/model` `/cancel` `/backup`
- All UI strings live in one file (`app/texts.py`) so wording can be changed in one place.

---

## 8. Message Processing Pipeline

```
message ─► (voice? → STT) ─► instant tools (calculator, today's date)
                                  │ otherwise
                                  ▼
                 agent: model + tools (max 4 rounds per message)
                   │  tool call → validate (Pydantic + deterministic parsers)
                   │            → service → database → result back to the model
                   │  missing / ambiguous → the model asks, or the app shows buttons
                   ▼
          short answer in the user's language + result cards (↩️ Undo / ✏️ Edit)

  no tool-capable model reachable → rule-based parser (normalizer → rules → forms)
```

**Tools:** `add_expenses` · `list_expenses` · `update_expense` · `delete_expenses` · `get_report` ·
`create_reminder` · `list_reminders` · `update_reminder` · `cancel_reminders` · `convert_date` ·
`calculate` · `update_settings` · `export_expenses` · `export_reminders` · `make_spreadsheet` ·
`add_todos` · `list_todos` · `update_todos` · `delete_todos` · `save_note` · `find_notes` ·
`update_note` · `delete_notes`

### Input normalization (Persian + English)
- Persian/Arabic digits → ASCII; `ي/ك` → `ی/ک`; zero-width non-joiner handling
- Number words in both languages: «سه», «صد و پنجاه», "three" → 3, 150, 3
- Time: «ساعت ۲» / "at 2" (with afternoon inference), «۲ و نیم» / "2:30", morning / noon / evening / night
- Relative dates: today, tomorrow, day after tomorrow, weekdays (fa + en)
- Absolute dates in **both calendars**: «۱۵ مهر» / "15 Mehr" (Jalali) and "Oct 7" / «۷ اکتبر» (Gregorian) — detected automatically
- **Amounts (base unit: toman):**
  - «۱۰۰ هزار», «۲ میلیون», «۵۰ تومن» → explicit
  - Colloquial «۳ تومن» is **ambiguous**: an amount below 1000 without thousand / million is asked
    every time (buttons: 3,000 / 3,000,000) — decided in v0.4
  - «دو میلیون و پونصد» = 2,500,000 (colloquial remainder after million)
  - Rial/toman base unit configurable in `.env`

---

## 9. Data Model (SQLite)

| Table | Main fields |
|---|---|
| `settings` | key, value |
| `reminders` | id, text, raw_text, event_at, all_day, repeat_rule, alert_specs, important, status, created_at |
| `reminder_alerts` | id, reminder_id, notify_at, kind (spec / extra), sent_at — several per reminder |
| `expenses` | id, amount (whole CURRENCY units), category_id, description, quantity, unit, spent_at, raw_text, created_at |
| `categories` | id, name, emoji, is_default, position |
| `category_keywords` | id, keyword (normalized description), category_id — learned from corrections |
| `notes` | id, title, text, summary, tags, pinned, source (text / voice), created_at, updated_at |
| `todos` | id, text, due_date, done_at, created_at |
| `chat_sessions` | id, title, started_at, updated_at, ended_at |
| `chat_history` | id, session_id, role, content, created_at (capped; assistant lines carry `[done: …]` action notes for references) |
| `agent_actions` | id, kind, payload (JSON), summary, created_at, undone_at — undo log of the agent |

All timestamps are stored in **UTC** and displayed in the user's timezone (default Asia/Tehran) using the **selected calendar** (Gregorian or Jalali).

---

## 10. Repository Structure

```
vira-assistant/
├── app/
│   ├── main.py                 # entry point
│   ├── config.py               # pydantic-settings
│   ├── texts.py                # all English UI strings
│   ├── agent/                  # the AI agent (v0.4)
│   │   ├── core.py             # loop: model → tools → results → answer
│   │   ├── tools/              # expenses, reminders, files (Excel), general (reports, dates, settings)
│   │   ├── actions.py          # undo log
│   │   ├── context.py          # per-message dates table (Gregorian = Jalali)
│   │   └── prompt.py           # system prompt
│   ├── bot/
│   │   ├── handlers/           # assistant (free text → agent), start, menu, chat, chats, reminders, expenses, reports, categories, settings, ai_models, fallback (+ notes later)
│   │   ├── agent_ui.py         # result cards with Undo / Edit, model switch notices
│   │   ├── keyboards/          # reply.py, inline.py
│   │   ├── views.py            # message rendering (reminder cards, notifications, briefing, reports)
│   │   ├── streaming.py        # streamed LLM answers via message edits
│   │   ├── states.py           # FSM states
│   │   └── middlewares/        # owner_only.py, logging.py, db.py, voice.py (voice → text before routing), menu_reset.py, notices.py
│   ├── core/
│   │   ├── normalizer.py       # fa/en digits, number words, ZWNJ
│   │   ├── textmatch.py        # fuzzy references to stored items
│   │   └── parsers/            # datetime_parser.py, rules.py, amount_parser.py, expense_rules.py (fa + en)
│   ├── llm/
│   │   ├── client.py           # one OpenAI-compatible endpoint (tools, streaming)
│   │   ├── models.py           # catalog of free models (friendly names)
│   │   ├── providers.py        # failover chain of free APIs + local model, chosen model
│   │   ├── failover.py         # cooldowns and switch notices (AI models and speech engines)
│   │   ├── prompts/            # helper prompts (bilingual)
│   │   └── schemas.py          # JSON schemas for structured output
│   ├── stt/                    # engines.py (Groq Whisper, Gemini, local faster-whisper), chain.py
│   ├── services/               # reminders, reminder_ai, expenses, expense_ai, reports, export, notes, todos, chat, tools
│   ├── scheduler/              # jobs.py (alerts, morning briefing, nightly report), setup.py
│   ├── db/                     # models.py, session.py
│   └── utils/                  # calendar.py (Gregorian/Jalali), formatting.py
├── scripts/eval_agent.py       # accuracy / latency benchmark of the configured models
├── migrations/                 # Alembic
├── tests/                      # parser and service tests
├── docker/
│   ├── Dockerfile
│   ├── entrypoint.sh           # fixes data/ ownership, drops to non-root
│   └── ollama-init.sh          # pulls models per profile
├── docs/
│   ├── ROADMAP.md              # this document
│   ├── AGENT_DESIGN.md         # agent design, research, trade-offs
│   ├── INSTALL.md
│   └── screenshots/
├── .github/workflows/ci.yml
├── docker-compose.yml
├── .env.example
├── pyproject.toml
├── CHANGELOG.md
├── LICENSE                     # MIT
└── README.md                   # English + Persian
```

### `.env.example` (draft)
```env
BOT_TOKEN=
OWNER_ID=
TZ=Asia/Tehran
DEFAULT_CALENDAR=jalali     # jalali | gregorian (user can change in Settings)
PROFILE=standard            # lite | standard | full | remote
LLM_BASE_URL=http://ollama:11434/v1
LLM_MODEL=                  # empty = profile default
LLM_API_KEY=ollama
STT_ENABLED=true
STT_PROVIDERS=groq,gemini,local
STT_MODEL=                  # local Whisper; empty = profile default
CURRENCY=toman
DAILY_REPORT_TIME=22:00
TELEGRAM_PROXY=             # optional: socks5://host:port
```

---

## 11. Security

- Only `OWNER_ID` can use the bot; all other updates are ignored (middleware)
- `.env`, `data/` and `models/` are in `.gitignore`
- Ollama is only reachable on the internal Docker network; the bot exposes no ports
- Containers run as a non-root user
- Database backups are sent only to the owner

---

## 12. Versioning & GitHub

- **SemVer**: `vMAJOR.MINOR.PATCH`
- Branches: `main` (stable) and `dev` (development); each version merged into `main`
- Every version: **Git tag + GitHub Release** with notes and CHANGELOG → all versions always available
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`)
- CI: ruff + pytest on every push; Docker image build on every tag (optional push to GHCR)

---

## 13. Version Roadmap

| Version | Scope | Acceptance criteria |
|---|---|---|
| **v0.1.0** | Project skeleton, Docker Compose, `/start`, English button menu, owner middleware, SQLite + Alembic, settings (calendar toggle), CI | `docker compose up` starts the bot and the menu appears |
| **v0.2.0** | Ollama service + profiles, LLM client, chat with short memory + New Chat | Simple Persian and English questions get answers; model switchable via `.env` |
| **v0.3.0** | Normalizer + fa/en date/time parser (both calendars), reminders (create/list/delete/repeat/snooze), scheduler, morning briefing (reminders), previous chats | "Doctor tomorrow at 2, remind me in the morning" is saved and delivered correctly |
| **v0.4.0** | **AI agent with tools + free provider chain** (model switching in the bot, switch notices), amount parser, expenses (multi-item), categories, daily/monthly reports | The groceries + fuel example creates two correct records |
| **v0.5.0** | Excel files from the chat (expenses, reminders, any table), nightly report, briefing and report times in Settings | Current month's Excel file is received |
| **v0.6.0** | Voice messages and audio files → text (Groq Whisper / Gemini, local faster-whisper backup) | Persian and English voice is processed like text |
| **v0.7.0** | Notes (tags, search, voice notes with a summary, pin), to-dos (daily, carried over), backup (weekly + restore) | All menu buttons functional |
| **v1.0.0** | Full test coverage, memory optimization, README, INSTALL guide, screenshots | Clean-server install using only the README |

---

## 14. Open Items

1. ~~Final rule for interpreting colloquial "X toman" amounts~~ — decided in v0.4: always ask
2. Publish image to GHCR or build locally only
3. License (default MIT)
4. Final model per profile after benchmarking on real hardware
