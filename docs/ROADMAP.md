# Vira Assistant — Roadmap & Architecture

> A personal AI assistant for daily tasks, running on a low-spec Linux server, controlled through a Telegram bot with a button menu.
> Repository: `github.com/rushqp/vira-assistant` (public) · Document status: **Approved**

---

## 1. Goals

A single-user assistant that, via Telegram (text, buttons, voice), can:

- Answer **simple questions**
- Create **reminders** and notify on time — e.g. *"I have a doctor's appointment tomorrow at 2, remind me in the morning"*
- Log **expenses** — e.g. *"Paid 3 (million) toman for groceries, and 10 liters of fuel cost 100 thousand"*
- Produce daily / weekly / monthly **reports** and export to **Excel/CSV**
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
| AI | **Local (Ollama)** — model switchable via `.env`; any OpenAI-compatible API also supported |
| Hardware | **Selectable profiles**: `lite` / `standard` / `full` (+ `remote`) |
| Language processing | **Hybrid**: rule-based parser first, LLM only when needed |
| Users | **Single-user** (only `OWNER_ID` is allowed) |
| Extras | Voice → text, Excel/CSV export, full basic-assistant feature set |
| UI language | **English** (all buttons and bot messages) |
| Input language | **Persian + English** (text and voice); replies follow the user's language |
| Calendar | **Gregorian + Jalali**, user-switchable in Settings |
| Versioning | Every version gets its own Git tag + GitHub Release |

---

## 3. High-Level Architecture

```
                 ┌──────────────────────────┐
                 │   User in Telegram       │
                 │  text / buttons / voice  │
                 └────────────┬─────────────┘
                              │ Long polling (no public IP / SSL needed)
                              ▼
┌──────────────────────── docker-compose ────────────────────────────────┐
│                                                                         │
│  ┌─────────────── bot (Python 3.12 / aiogram 3) ───────────────────┐   │
│  │                                                                  │   │
│  │  handlers ──► [ voice? ] ──► stt (faster-whisper) ──┐            │   │
│  │                                                      ▼            │   │
│  │                normalizer (fa/en digits, dates, amounts)          │   │
│  │                                ▼                                  │   │
│  │                    rule parser (regex + patterns)                 │   │
│  │               confident? ──yes──►  service                        │   │
│  │                    │ no                                           │   │
│  │                    ▼                                              │   │
│  │         llm router (JSON-Schema output) ─────────────► ollama ◄──┼───┤
│  │                    ▼                                              │   │
│  │     confirm (inline buttons: ✅ Save / ✏️ Edit / ❌ Cancel)        │   │
│  │                    ▼                                              │   │
│  │  services: reminders · expenses · reports · notes · todos · chat  │   │
│  │                    ▼                         ▲                    │   │
│  │             SQLite (volume)  ◄──── scheduler (APScheduler)        │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌────────── ollama ──────────┐     volumes: ./data  ./models            │
│  │ model per profile          │     (Ollama port is never exposed)       │
│  └────────────────────────────┘                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Design principle:** frequent actions (reminders, expenses, reports) must work **without the LLM and in milliseconds**. The LLM is only called for complex sentences and open questions — this is what makes the bot usable on weak hardware.

---

## 4. Tech Stack

| Area | Tool | Purpose |
|---|---|---|
| Language | Python 3.12 | All bot logic |
| Telegram bot | **aiogram 3** | Handlers, Reply/Inline keyboards, FSM for multi-step forms |
| Local LLM | **Ollama** | CPU model inference; OpenAI-compatible API |
| LLM client | `openai` SDK (custom `base_url`) | One client for Ollama, OpenRouter, Gemini, etc. |
| Structured output | Ollama `format` (JSON Schema) | Sentence → `{intent, datetime, amount, ...}`; more reliable than tool calling on small models |
| Speech-to-text | **faster-whisper** (CTranslate2, int8) | Persian + English voice transcription on CPU |
| Audio conversion | ffmpeg | Telegram OGG/Opus → WAV |
| Scheduling | **APScheduler** + SQLAlchemy JobStore | Reminders and nightly report; survive restarts |
| Database | **SQLite** + SQLAlchemy 2 (async, aiosqlite) | No extra service; single file on a volume |
| Migrations | Alembic | Schema changes across versions without data loss |
| Dual calendar | **jdatetime** + `zoneinfo` (Asia/Tehran) | Gregorian ↔ Jalali input/output; display follows user setting |
| Excel / CSV | **openpyxl** + `csv` | Expense report export |
| Config | pydantic-settings + `.env` | Tokens and model selection; never committed |
| Logging | loguru | Lightweight rotating logs |
| Testing | pytest + pytest-asyncio | fa/en parser and service tests |
| Code quality | ruff | Lint + format |
| CI | GitHub Actions | Lint + tests + image build on each push |
| Image registry | GHCR (optional) | `ghcr.io/rushqp/vira-assistant:<version>` |

---

## 5. Hardware Profiles

Selected with one variable: `PROFILE=lite | standard | full | remote` (or override `LLM_MODEL` / `STT_MODEL` manually).

| Profile | Suggested RAM | Default LLM | Whisper model | Notes |
|---|---|---|---|---|
| `lite` | 2 GB | `gemma3:1b` | `tiny` | Parser + short answers; limited Persian quality |
| `standard` | 4 GB | `qwen2.5:3b` | `base` | Speed/quality balance (default) |
| `full` | 8 GB+ | `qwen2.5:7b` (Q4) | `small` | Better Persian and sentence understanding |
| `remote` | — | Any external API model | — | Ollama not started; uses `LLM_BASE_URL` + `LLM_API_KEY` |

- Models are pulled automatically on first start (`ollama pull` in an init service).
- STT can be disabled entirely with `STT_ENABLED=false`.
- ⚠️ Default models will be benchmarked on real hardware before v0.2 and replaced if needed.

---

## 6. Features (Modules)

### 6.1 Chat (Q&A)
- Answers simple questions in **Persian or English** using the local LLM with short-term memory (last 10 messages)
- **New Chat** button clears the conversation context and starts a fresh session
- Built-in tools without LLM: calculator, Gregorian ↔ Jalali conversion, "what's today's date?" (in both calendars)

### 6.2 Reminders
- Create from free text or a step-by-step form
- **Separate event time and notify time**: "doctor tomorrow at 2, remind me in the morning" → event 14:00, notify 09:00
- Recurring: daily, weekly, monthly (e.g. "every Saturday at 8")
- Notification buttons: [✅ Done] [⏰ +10 min] [⏰ +1 hour]
- List / edit / delete

### 6.3 Expenses
- Multiple expenses in one message → multiple records
- Amount, category, description, quantity and unit (e.g. 10 liters)
- Default categories: Food, Home, Fuel, Transport, Bills, Health, Leisure, Other (editable)
- **Always confirm before saving**, showing the interpreted amount

### 6.4 Reports
- Today / yesterday / week / month / custom range — month boundaries follow the selected calendar (Jalali month or Gregorian month)
- Total + per-category breakdown + largest expense
- **Excel** export (formatted, with totals) and **CSV**
- Automatic nightly report at a configurable time (today's expenses + tomorrow's reminders)
- Optional morning briefing: today's tasks and reminders

### 6.5 Notes & To-Dos
- Quick notes with tags and search
- Daily to-do list with checkboxes

### 6.6 Voice (STT)
- Voice → text → same pipeline as text messages
- Recognized text is shown back to the user for transparency

### 6.7 Settings
- **Calendar: Gregorian / Jalali** (affects all dates in messages, reports and exports)
- Nightly report time, morning briefing on/off
- Active model (read-only display), category management
- Backup: send the database file to the owner

---

## 7. Main Menu (Reply Keyboard)

```
┌──────────────────────┬──────────────────────┐
│     💬 New Chat       │   ⏰ New Reminder     │
├──────────────┬───────┴───────┬──────────────┤
│ 💰 Add Expense│ 📊 Today Report│ 📅 Month Report│
├──────────────┼───────────────┼──────────────┤
│ 📋 Reminders  │ ✅ Today To-Dos │ 📝 Notes      │
├──────────────┴───────┬───────┴──────────────┤
│   📤 Export Excel     │     ⚙️ Settings       │
└──────────────────────┴──────────────────────┘
```

- **New Chat** clears the conversation context and starts a fresh Q&A session.
- Each button either opens a multi-step form (FSM) or shows a result directly.
- The user can send **free text or voice (Persian or English) at any time** without pressing a button.
- Per-item actions use **Inline Keyboards** under each message.
- Commands: `/start` `/help` `/menu` `/new` `/cancel` `/backup`
- All UI strings live in one file (`app/texts.py`) so wording can be changed in one place.

---

## 8. Message Processing Pipeline

```
message ─► (voice? → STT) ─► normalize ─► rule-based parser
                                              │
                         ┌────────────────────┴───────────────────┐
                   high confidence                          low confidence
                         │                                         │
                         │                     LLM → JSON Schema {intent, slots}
                         │                                         │
                         └──────────────► validate slots ◄─────────┘
                                              │ missing? → follow-up question (FSM)
                                              ▼
                                   confirm with inline buttons
                                              ▼
                                     service → database
```

**Intents:** `reminder.create` · `reminder.list` · `expense.add` · `report.get` · `export.get` · `note.add` · `todo.add` · `chat` · `unknown`

### Input normalization (Persian + English)
- Persian/Arabic digits → ASCII; `ي/ك` → `ی/ک`; zero-width non-joiner handling
- Number words in both languages: «سه», «صد و پنجاه», "three" → 3, 150, 3
- Time: «ساعت ۲» / "at 2" (with afternoon inference), «۲ و نیم» / "2:30", morning / noon / evening / night
- Relative dates: today, tomorrow, day after tomorrow, weekdays (fa + en)
- Absolute dates in **both calendars**: «۱۵ مهر» / "15 Mehr" (Jalali) and "Oct 7" / «۷ اکتبر» (Gregorian) — detected automatically
- **Amounts (base unit: toman):**
  - «۱۰۰ هزار», «۲ میلیون», «۵۰ تومن» → explicit
  - Colloquial «۳ تومن» is **ambiguous**; default rule: number < 100 without a unit = million, 100–999 = thousand — the interpreted amount is always shown for confirmation
  - Rial/toman base unit configurable in `.env`

---

## 9. Data Model (SQLite)

| Table | Main fields |
|---|---|
| `settings` | key, value |
| `reminders` | id, text, event_at, notify_at, repeat_rule, status, created_at |
| `expenses` | id, amount, category_id, description, quantity, unit, spent_at, raw_text |
| `categories` | id, name, emoji, is_default |
| `notes` | id, text, tags, created_at |
| `todos` | id, text, due_date, done, created_at |
| `chat_sessions` | id, started_at, ended_at |
| `chat_history` | id, session_id, role, content, created_at (capped) |
| `apscheduler_jobs` | managed by APScheduler |

All timestamps are stored in **UTC** and displayed in the user's timezone (default Asia/Tehran) using the **selected calendar** (Gregorian or Jalali).

---

## 10. Repository Structure

```
vira-assistant/
├── app/
│   ├── main.py                 # entry point
│   ├── config.py               # pydantic-settings
│   ├── texts.py                # all English UI strings
│   ├── bot/
│   │   ├── handlers/           # start, menu, chat, reminders, expenses, reports, notes, voice, settings, fallback
│   │   ├── keyboards/          # reply.py, inline.py
│   │   ├── streaming.py        # streamed LLM answers via message edits
│   │   ├── states.py           # FSM states
│   │   └── middlewares/        # owner_only.py, logging.py, db.py
│   ├── core/
│   │   ├── normalizer.py       # fa/en digits, number words, ZWNJ
│   │   ├── parsers/            # datetime_parser.py, amount_parser.py, rules.py (fa + en)
│   │   └── router.py           # rule vs LLM routing
│   ├── llm/
│   │   ├── client.py           # OpenAI-compatible client
│   │   ├── prompts/            # system/intent prompts (bilingual)
│   │   └── schemas.py          # intent JSON schemas
│   ├── stt/whisper.py
│   ├── services/               # reminders, expenses, reports, export, notes, todos, chat
│   ├── scheduler/              # jobs.py, setup.py
│   ├── db/                     # models.py, session.py
│   └── utils/                  # calendar.py (Gregorian/Jalali), formatting.py
├── migrations/                 # Alembic
├── tests/                      # parser and service tests
├── docker/
│   ├── Dockerfile
│   ├── entrypoint.sh           # fixes data/ ownership, drops to non-root
│   └── ollama-init.sh          # pulls models per profile
├── docs/
│   ├── ROADMAP.md              # this document
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
STT_MODEL=                  # empty = profile default
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
| **v0.3.0** | Normalizer + fa/en date/time parser (both calendars), reminders (create/list/delete/repeat/snooze), scheduler | "Doctor tomorrow at 2, remind me in the morning" is saved and delivered correctly |
| **v0.4.0** | Amount parser, expenses (multi-item), categories, daily/monthly reports | The groceries + fuel example creates two correct records |
| **v0.5.0** | Excel/CSV export, nightly report, morning briefing | Current month's Excel file is received |
| **v0.6.0** | Voice → text (faster-whisper) | Persian and English voice is processed like text |
| **v0.7.0** | Notes, to-dos, settings, backup | All menu buttons functional |
| **v1.0.0** | Full test coverage, memory optimization, README, INSTALL guide, screenshots | Clean-server install using only the README |

---

## 14. Open Items

1. Final rule for interpreting colloquial "X toman" amounts (default above) — revisit in v0.4
2. Publish image to GHCR or build locally only
3. License (default MIT)
4. Final model per profile after benchmarking on real hardware
