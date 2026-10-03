<div align="center">

# 🤖 Vira Assistant

**A personal AI assistant on Telegram that understands what you say and does it:**
**reminders, expenses, reports, notes and voice. Persian and English. Runs with Docker.**

[English](#english) · [فارسی](#فارسی)

![version](https://img.shields.io/badge/version-0.4.0-blue)
![python](https://img.shields.io/badge/python-3.12-3776AB)
![license](https://img.shields.io/badge/license-MIT-green)
[![CI](https://github.com/Rushqp/vira-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/Rushqp/vira-assistant/actions/workflows/ci.yml)

</div>

---

<a id="english"></a>

## 🇬🇧 English

### What is Vira?

Vira is a **single-user** assistant you run on your own server (even a weak one) and talk to through
Telegram. Write the way you talk, in **Persian or English**, typos and all, and Vira understands and
acts:

- *«امروز ۳ خرید کردم: سیگار ۱۵۰ هزار، ماست ۲۰۰ هزار، آب ۵۰ هزار»* → three expenses saved
- *«فردا ساعت ۲ دکتر دارم، صبح یادم بنداز»* → reminder at 14:00, notification at 09:00
- *«تایم دکتر رو کنسل کن»* → that reminder is cancelled
- *«نه، ماست ۲۵۰ هزار بود»* → the expense is corrected
- *«این ماه چقدر خرج کردم؟»* → a monthly report
- and ordinary questions, answered in your language

Every action shows what was done, with **↩️ Undo** and **✏️ Edit** buttons. Vira only asks when
something is really unclear, for example whether «۳ تومن» means 3 thousand or 3 million.

Under the hood an **AI agent** reads each message and calls typed tools (add expenses, create /
cancel reminders, reports, …). The app checks every tool call with deterministic Persian/English
parsers (Jalali dates, «هزار / میلیون» amounts) before acting. Reminders and the morning briefing
never depend on the AI. Design: [docs/AGENT_DESIGN.md](docs/AGENT_DESIGN.md).

### Status

| Version | Scope | State |
|---|---|---|
| **v0.1.0** | Skeleton, Docker, menu, owner-only access, SQLite + Alembic, calendar setting, CI | ✅ Done |
| **v0.2.0** | Ollama + hardware profiles, streaming chat with short memory, calculator, today's date | ✅ Done |
| **v0.3.0** | Reminders (fa/en date parser, both calendars, repeats, snooze), morning briefing, previous chats | ✅ Done |
| **v0.4.0** | **AI agent** (understands any phrasing, follow-ups, undo / edit), free AI providers with failover, expenses, 13 categories with learning, reports | ✅ Done |
| v0.5.0 | Excel/CSV export, nightly report | ⏳ Next |
| v0.6.0 | Voice → text (faster-whisper) | |
| v0.7.0 | Notes, to-dos, backup | |
| v1.0.0 | Full tests, optimization, install guide | |

The full plan is in [docs/ROADMAP.md](docs/ROADMAP.md).

### Quick start

**Requirements:** Docker with Docker Compose, a Telegram bot token, and your numeric Telegram ID.

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Get your numeric user ID from [@userinfobot](https://t.me/userinfobot).
3. **Recommended:** get a free AI key, so Vira is smart and fast even on a small server:
   [Google AI Studio](https://aistudio.google.com/apikey) (Gemini) and/or
   [Groq](https://console.groq.com/keys). Several keys = automatic failover.
4. Clone and configure:

   ```bash
   git clone https://github.com/Rushqp/vira-assistant.git
   cd vira-assistant
   cp .env.example .env      # set BOT_TOKEN, OWNER_ID and GEMINI_API_KEY / GROQ_API_KEY
   ```

5. Start it:

   ```bash
   docker compose up -d --build
   docker compose logs -f bot
   ```

6. Open your bot in Telegram and send `/start`.

On the first start, the `ollama-init` container downloads the local model for your profile (the local
fallback). Follow it with `docker compose logs -f ollama-init`. With `PROFILE=remote` and
`COMPOSE_PROFILES=` (empty) no local model is used at all.

### How Vira thinks

| Step | What happens |
|---|---|
| 1 | Calculator and "what's the date?" are answered instantly, without AI |
| 2 | The **agent** reads the message with recent context (and the dates of the coming days in both calendars) and decides which tools to call |
| 3 | Each tool call is validated: amounts and dates are re-checked by deterministic parsers; mistakes go back to the AI to fix |
| 4 | You get a card for every real result, with ↩️ Undo / ✏️ Edit |
| — | AI providers are tried in order (`LLM_PROVIDERS`): a provider that is down or out of free quota is paused and the next one answers |
| — | If no AI is reachable, the v0.3 rule-based understanding still handles reminders, expenses and reports |

Privacy: with an API provider, your message text is sent to that provider (your database stays on
your server). For fully local operation use `standard` / `full` without API keys.

### Using it

- **Just talk.** Several requests in one message are fine. Follow-ups work: "cancel it", «پاکش کن»,
  «ساعتش رو بکن ۵».
- **Reminders:** events and notifications are understood separately («… صبح یادم بنداز»).
  Without a notification time, Vira notifies at the start and offers buttons for 15 min / 1 hour
  before, the night before or the morning of the day. Repeats: every day / week / month.
  Notifications have **Done**, **+10 min** and **+1 hour**. 📋 **Reminders** lists them.
- **Expenses:** several items at once, quantities («۱۰ لیتر»), past days («دیروز»). Categories are
  chosen by the AI; corrections are remembered (🏷 on a saved expense, or just say it).
  ⚙️ Settings → 🏷 Categories adds or removes categories.
- **Reports:** 📊 **Today Report**, 📅 **Month Report** (Jalali or Gregorian month), or just ask:
  total, comparison with the previous period, daily average, per-category bars, largest expense.
- **Morning briefing:** every day at 08:00, today's reminders, important ones (⭐) first.
- 💬 **New Chat** starts a fresh conversation; 🗂 **Chats** continues an older one.

### Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | Bot token from @BotFather (**required**) |
| `OWNER_ID` | — | Your Telegram user ID. All other users are ignored (**required**) |
| `TELEGRAM_PROXY` | empty | Optional proxy, e.g. `socks5://host:port` |
| `TZ` | `Asia/Tehran` | Timezone used for display and scheduling |
| `DEFAULT_CALENDAR` | `jalali` | `jalali` or `gregorian` (can be changed in Settings) |
| `CURRENCY` | `toman` | `toman` or `rial` |
| `PROFILE` | `standard` | Hardware profile: `lite`, `standard`, `full`, `remote` |
| `COMPOSE_PROFILES` | `ollama` | Starts the local Ollama containers; empty for `remote` |
| `LLM_PROVIDERS` | `gemini,groq,github,local` | Order in which AI providers are tried; ones without a key are skipped |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | empty / `gemini-flash-latest` | Free Google Gemini API |
| `GROQ_API_KEY` / `GROQ_MODEL` | empty / `openai/gpt-oss-120b` | Free Groq API |
| `GITHUB_TOKEN` / `GITHUB_MODEL` | empty / `openai/gpt-4.1-mini` | Free GitHub Models API |
| `LLM_BASE_URL` | `http://ollama:11434/v1` | The `local` provider: Ollama, or any OpenAI-compatible API (e.g. OpenRouter) |
| `LLM_MODEL` | profile default | Model of the `local` provider |
| `LLM_API_KEY` | `ollama` | API key of the `local` provider |
| `LOCAL_TOOLS` | `auto` | Agent tools with the local model: `auto` (by model family), `on`, `off` |
| `LLM_TIMEOUT` | `180` | Seconds to wait for the local model |
| `CHAT_MEMORY` | `10` | How many previous messages the assistant sees (0–50) |
| `CHAT_KEEP` | `20` | How many previous chats are kept in 🗂 Chats |
| `OLLAMA_KEEP_ALIVE` | `30m` | How long the local model stays in RAM after use (`-1` = forever) |
| `STT_ENABLED` / `STT_MODEL` | `true` / profile default | Voice transcription (v0.6) |
| `MORNING_TIME` … `NIGHT_TIME` | `09:00` `12:00` `16:00` `19:00` `22:00` | Clock times for morning, noon, afternoon, evening, night |
| `MORNING_BRIEFING_TIME` | `08:00` | Daily list of today's reminders |
| `DAILY_REPORT_TIME` | `22:00` | Time of the nightly report (v0.5) |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` … |

**Hardware profiles** (the free APIs come first in every profile when a key is set)

| Profile | RAM | Local model | Without an API key |
|---|---|---|---|
| `lite` | 2 GB | `gemma3:1b` (chat only) | rule-based understanding + local chat |
| `standard` | 4 GB | `qwen3:4b` (agent) | local agent, slower on CPU |
| `full` | 8 GB+ | `qwen3:8b` (agent) | local agent |
| `remote` | — | none | needs an API key or `LLM_MODEL` |

Measure accuracy and speed of your models on your own server:
`docker compose exec bot python scripts/eval_agent.py`.

### Source code map

```
app/
├── main.py            # Entry point: logging → migrations → scheduler → bot polling
├── config.py          # All settings from .env (pydantic-settings) + hardware profiles
├── texts.py           # Every user-facing string (edit wording here only)
├── agent/             # The brain: an AI agent with typed tools
│   ├── core.py        #   the loop: model → tool calls → results → short answer
│   ├── tools/         #   expenses, reminders, general (reports, dates, settings); validation
│   ├── actions.py     #   undo log for everything the agent changed
│   ├── context.py     #   per-message context: now + dates table (Gregorian = Jalali)
│   └── prompt.py      #   the system prompt
├── llm/               # client.py = one OpenAI-compatible endpoint, providers.py = failover
│                      #   chain (Gemini → Groq → GitHub → local), prompts/, schemas.py
├── bot/               # Telegram layer, no business logic
│   ├── handlers/      #   assistant (free text → agent), chats, settings, categories, reminders,
│   │                  #   expenses, reports (buttons + rule-based fallback), menu, fallback
│   ├── agent_ui.py    #   result cards with ↩️ Undo / ✏️ Edit
│   ├── keyboards/     #   reply.py = main menu, inline.py = buttons under messages
│   ├── middlewares/   #   owner_only, logging, db (session + services), menu_reset
│   ├── views.py       #   reminder cards, notifications, briefing, expense cards, reports
│   ├── streaming.py   #   shows a streamed answer by editing the Telegram message
│   └── states.py      #   FSM states
├── core/              # Deterministic language tools (no AI)
│   ├── normalizer.py  #   fa/en digits, number words, Arabic letters, ZWNJ
│   ├── textmatch.py   #   fuzzy references («تایم دکتر» → the doctor reminder)
│   └── parsers/       #   dates & times, reminder sentences, amounts, expense sentences
├── services/          # Business logic, independent of Telegram: reminders, expenses,
│                      #   reports, chat history, settings, calculator
├── scheduler/         # due reminders + morning briefing (APScheduler)
├── db/                # models.py = tables, session.py = engine + migrations
└── utils/             # Jalali / Gregorian formatting, Markdown → HTML, money
scripts/eval_agent.py  # accuracy / latency of each configured model on real Persian cases
migrations/            # Alembic migrations (one file per schema change)
tests/                 # pytest suite (no network or real model needed)
docker/                # Dockerfile, entrypoint, ollama-init.sh (pulls the profile model)
docs/                  # Roadmap, agent design
```

How a message flows: **Telegram → middlewares → `handlers/assistant.py` → `agent/core.py` ↔
`llm/providers.py` → `agent/tools/*` → `services/*` → database**, and the results come back as
cards from `bot/agent_ui.py`.

### Development

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env               # set BOT_TOKEN, OWNER_ID (and an API key)
python -m app.main                 # run the bot locally (DB in ./data)

pytest                             # tests
ruff check . && ruff format .      # lint + format
python scripts/eval_agent.py       # how well the configured models understand real messages
alembic revision -m "describe"     # new migration
```

Branches: `main` (stable) and `dev` (development). Commits follow
[Conventional Commits](https://www.conventionalcommits.org/). Each version is tagged and published as
a GitHub Release. See [CHANGELOG.md](CHANGELOG.md).

### License

[MIT](LICENSE)

---

<a id="فارسی"></a>

<div dir="rtl">

## 🇮🇷 فارسی

### ویرا چیست؟

ویرا یک دستیار شخصی **تک‌کاربره** است که روی سرور خودتان (حتی یک سرور ضعیف) اجرا می‌شود و از طریق
تلگرام با آن حرف می‌زنید. همان‌طور که حرف می‌زنید بنویسید، **فارسی یا انگلیسی**، حتی با غلط تایپی؛ ویرا
منظورتان را می‌فهمد و انجام می‌دهد:

- «امروز ۳ خرید کردم: سیگار ۱۵۰ هزار، ماست ۲۰۰ هزار، آب ۵۰ هزار» ← سه هزینه ثبت می‌شود
- «فردا ساعت ۲ دکتر دارم، صبح یادم بنداز» ← یادآور ساعت ۱۴ و اعلان ساعت ۹ صبح
- «تایم دکتر رو کنسل کن» ← همان یادآور کنسل می‌شود
- «نه، ماست ۲۵۰ هزار بود» ← هزینه اصلاح می‌شود
- «این ماه چقدر خرج کردم؟» ← گزارش ماه
- و سوال‌های معمولی که به زبان خودتان جواب داده می‌شوند

نتیجه هر کار با دکمه‌های **↩️ برگشت** و **✏️ ویرایش** نشان داده می‌شود. ویرا فقط وقتی چیزی واقعاً مبهم
باشد سوال می‌پرسد، مثلاً این‌که «۳ تومن» یعنی ۳ هزار یا ۳ میلیون.

در پشت صحنه یک **Agent هوش مصنوعی** هر پیام را می‌خواند و ابزارهای مشخصی را صدا می‌زند (ثبت هزینه،
ساخت یا کنسل یادآور، گزارش و …). برنامه هر کدام را قبل از اجرا با پارسرهای دقیق فارسی و انگلیسی
(تاریخ شمسی، مبلغ‌های «هزار / میلیون») بررسی می‌کند. یادآورها و خلاصه صبحگاهی هیچ وقت به هوش مصنوعی
وابسته نیستند. طراحی: [docs/AGENT_DESIGN.md](docs/AGENT_DESIGN.md).

### وضعیت پروژه

| نسخه | محتوا | وضعیت |
|---|---|---|
| **v0.1.0** | اسکلت پروژه، داکر، منو، دسترسی فقط برای مالک، SQLite و Alembic، تنظیم تقویم، CI | ✅ انجام شد |
| **v0.2.0** | Ollama و پروفایل‌های سخت‌افزاری، چت استریمی با حافظه کوتاه، ماشین‌حساب، تاریخ امروز | ✅ انجام شد |
| **v0.3.0** | یادآورها (پارسر تاریخ فارسی/انگلیسی، هر دو تقویم، تکرار، تعویق)، خلاصه صبحگاهی، چت‌های قبلی | ✅ انجام شد |
| **v0.4.0** | **Agent هوش مصنوعی** (فهم هر جمله، پیگیری حرف‌های قبلی، برگشت / ویرایش)، سرویس‌های رایگان هوش مصنوعی با جایگزینی خودکار، هزینه‌ها، ۱۳ دسته با یادگیری، گزارش‌ها | ✅ انجام شد |
| v0.5.0 | خروجی اکسل/CSV، گزارش شبانه | ⏳ بعدی |
| v0.6.0 | تبدیل صوت به متن (faster-whisper) | |
| v0.7.0 | یادداشت‌ها، کارهای روزانه، پشتیبان‌گیری | |
| v1.0.0 | تست کامل، بهینه‌سازی، راهنمای نصب | |

نقشه کامل پروژه در [docs/ROADMAP.md](docs/ROADMAP.md) است.

### راه‌اندازی سریع

**پیش‌نیازها:** داکر و Docker Compose، توکن ربات تلگرام و شناسه عددی تلگرام شما.

۱. با [@BotFather](https://t.me/BotFather) یک ربات بسازید و توکن آن را کپی کنید.

۲. شناسه عددی خود را از [@userinfobot](https://t.me/userinfobot) بگیرید.

۳. **پیشنهادی:** یک کلید رایگان هوش مصنوعی بگیرید تا ویرا حتی روی سرور کوچک هم باهوش و سریع باشد:
[Google AI Studio](https://aistudio.google.com/apikey) (Gemini) و/یا [Groq](https://console.groq.com/keys).
چند کلید یعنی جایگزینی خودکار وقتی یکی در دسترس نیست.

۴. پروژه را کلون و تنظیم کنید:

</div>

```bash
git clone https://github.com/Rushqp/vira-assistant.git
cd vira-assistant
cp .env.example .env      # BOT_TOKEN، OWNER_ID و GEMINI_API_KEY / GROQ_API_KEY را تنظیم کنید
```

<div dir="rtl">

۵. اجرا کنید:

</div>

```bash
docker compose up -d --build
docker compose logs -f bot
```

<div dir="rtl">

۶. ربات را در تلگرام باز کنید و `/start` را بفرستید.

در اولین اجرا، کانتینر `ollama-init` مدل لوکال پروفایل شما (پشتیبان) را دانلود می‌کند. پیشرفتش را با
`docker compose logs -f ollama-init` ببینید. با `PROFILE=remote` و `COMPOSE_PROFILES` خالی، هیچ مدل
لوکالی استفاده نمی‌شود.

### ویرا چطور فکر می‌کند

| مرحله | چه اتفاقی می‌افتد |
|---|---|
| ۱ | ماشین‌حساب و «امروز چندمه؟» فوراً و بدون هوش مصنوعی جواب داده می‌شوند |
| ۲ | **Agent** پیام را همراه با گفتگوی اخیر (و تاریخ روزهای پیش رو در هر دو تقویم) می‌خواند و تصمیم می‌گیرد کدام ابزارها را صدا بزند |
| ۳ | هر درخواست ابزار بررسی می‌شود: مبلغ و تاریخ با پارسرهای دقیق دوباره چک می‌شوند و اشتباه‌ها برای اصلاح به هوش مصنوعی برمی‌گردند |
| ۴ | برای هر نتیجه واقعی یک کارت با ↩️ برگشت / ✏️ ویرایش می‌گیرید |
| — | سرویس‌های هوش مصنوعی به ترتیب امتحان می‌شوند (`LLM_PROVIDERS`): سرویسی که قطع است یا سهمیه رایگانش تمام شده موقتاً کنار گذاشته می‌شود و بعدی جواب می‌دهد |
| — | اگر هیچ هوش مصنوعی در دسترس نباشد، فهم قانون‌محور نسخه ۰٫۳ همچنان یادآور، هزینه و گزارش را انجام می‌دهد |

حریم خصوصی: با سرویس API، متن پیام‌ها به همان سرویس فرستاده می‌شود (دیتابیس روی سرور خودتان می‌ماند).
برای کار کاملاً لوکال از `standard` یا `full` بدون کلید API استفاده کنید.

### نحوه استفاده

- **فقط حرف بزنید.** چند درخواست در یک پیام هم مشکلی ندارد. ادامه حرف قبلی هم کار می‌کند: «کنسلش کن»،
  «پاکش کن»، «ساعتش رو بکن ۵».
- **یادآور:** زمان رویداد و زمان اعلان جدا فهمیده می‌شوند («… صبح یادم بنداز»). اگر زمان اعلان را نگویید،
  ویرا سر وقت اعلان می‌دهد و دکمه‌هایی برای ۱۵ دقیقه / ۱ ساعت قبل، شب قبل یا صبح همان روز پیشنهاد می‌دهد.
  تکرار روزانه، هفتگی و ماهانه. پیام یادآوری دکمه‌های **Done**، **+10 min** و **+1 hour** دارد.
  📋 **Reminders** فهرست یادآورهاست.
- **هزینه‌ها:** چند مورد با هم، مقدار («۱۰ لیتر») و روزهای گذشته («دیروز»). دسته را هوش مصنوعی انتخاب
  می‌کند و اصلاح‌های شما یادش می‌ماند (دکمه 🏷 روی هزینه ثبت‌شده، یا فقط بگویید). دسته‌ها از
  ⚙️ Settings ← 🏷 Categories اضافه و حذف می‌شوند.
- **گزارش‌ها:** 📊 **Today Report**، 📅 **Month Report** (ماه شمسی یا میلادی) یا فقط بپرسید: جمع کل،
  مقایسه با دوره قبل، میانگین روزانه، نمودار متنی دسته‌ها و بزرگ‌ترین هزینه.
- **خلاصه صبحگاهی:** هر روز ساعت ۸ صبح، یادآورهای امروز با موارد مهم (⭐) در بالا.
- 💬 **New Chat** گفتگوی تازه شروع می‌کند و 🗂 **Chats** گفتگوهای قبلی را ادامه می‌دهد.

### تنظیمات (`.env`)

| متغیر | پیش‌فرض | توضیح |
|---|---|---|
| `BOT_TOKEN` | — | توکن ربات از BotFather (**الزامی**) |
| `OWNER_ID` | — | شناسه تلگرام شما. پیام بقیه کاربران نادیده گرفته می‌شود (**الزامی**) |
| `TELEGRAM_PROXY` | خالی | پراکسی اختیاری، مثل `socks5://host:port` |
| `TZ` | `Asia/Tehran` | منطقه زمانی |
| `DEFAULT_CALENDAR` | `jalali` | `jalali` یا `gregorian` (در تنظیمات ربات هم قابل تغییر است) |
| `CURRENCY` | `toman` | `toman` یا `rial` |
| `PROFILE` | `standard` | پروفایل سخت‌افزار: `lite`، `standard`، `full`، `remote` |
| `COMPOSE_PROFILES` | `ollama` | اجرای کانتینرهای Ollama؛ برای `remote` خالی بگذارید |
| `LLM_PROVIDERS` | `gemini,groq,github,local` | ترتیب امتحان سرویس‌های هوش مصنوعی؛ سرویس‌های بدون کلید رد می‌شوند |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | خالی / `gemini-flash-latest` | API رایگان Gemini گوگل |
| `GROQ_API_KEY` / `GROQ_MODEL` | خالی / `openai/gpt-oss-120b` | API رایگان Groq |
| `GITHUB_TOKEN` / `GITHUB_MODEL` | خالی / `openai/gpt-4.1-mini` | API رایگان GitHub Models |
| `LLM_BASE_URL` | `http://ollama:11434/v1` | سرویس `local`: Ollama یا هر API سازگار با OpenAI (مثل OpenRouter) |
| `LLM_MODEL` | پیش‌فرض پروفایل | مدل سرویس `local` |
| `LLM_API_KEY` | `ollama` | کلید API سرویس `local` |
| `LOCAL_TOOLS` | `auto` | ابزارهای Agent با مدل لوکال: `auto` (بر اساس نوع مدل)، `on`، `off` |
| `LLM_TIMEOUT` | `180` | حداکثر زمان انتظار برای مدل لوکال (ثانیه) |
| `CHAT_MEMORY` | `10` | تعداد پیام‌های قبلی که دستیار می‌بیند (۰ تا ۵۰) |
| `CHAT_KEEP` | `20` | تعداد گفتگوهای قبلی که در 🗂 Chats نگه داشته می‌شود |
| `OLLAMA_KEEP_ALIVE` | `30m` | مدت ماندن مدل لوکال در رم بعد از آخرین پیام (`-1` یعنی همیشه) |
| `STT_ENABLED` / `STT_MODEL` | `true` / پیش‌فرض پروفایل | تبدیل صوت به متن (نسخه ۰٫۶) |
| `MORNING_TIME` … `NIGHT_TIME` | `09:00` `12:00` `16:00` `19:00` `22:00` | ساعت پیش‌فرض صبح، ظهر، بعدازظهر، عصر و شب |
| `MORNING_BRIEFING_TIME` | `08:00` | ساعت ارسال خلاصه صبحگاهی |
| `DAILY_REPORT_TIME` | `22:00` | ساعت گزارش شبانه (نسخه ۰٫۵) |
| `LOG_LEVEL` | `INFO` | سطح لاگ |

**پروفایل‌های سخت‌افزاری** (در همه پروفایل‌ها، اگر کلید API باشد، سرویس‌های رایگان اول امتحان می‌شوند)

| پروفایل | رم | مدل لوکال | بدون کلید API |
|---|---|---|---|
| `lite` | ۲ گیگ | `gemma3:1b` (فقط چت) | فهم قانون‌محور + چت لوکال |
| `standard` | ۴ گیگ | `qwen3:4b` (Agent) | Agent لوکال، کندتر روی CPU |
| `full` | ۸ گیگ و بیشتر | `qwen3:8b` (Agent) | Agent لوکال |
| `remote` | — | ندارد | کلید API یا `LLM_MODEL` لازم است |

دقت و سرعت مدل‌ها را روی سرور خودتان بسنجید: `docker compose exec bot python scripts/eval_agent.py`

### نقشه سورس کد

- `app/main.py`: نقطه شروع برنامه (لاگ، مایگریشن، زمان‌بند، اجرای ربات)
- `app/config.py`: همه تنظیمات `.env` و پروفایل‌های سخت‌افزاری
- `app/texts.py`: همه متن‌هایی که کاربر می‌بیند (برای تغییر متن‌ها فقط همین فایل را ویرایش کنید)
- `app/agent/`: مغز برنامه، یک Agent هوش مصنوعی با ابزارهای مشخص
  - `core.py`: حلقه اصلی (مدل ← درخواست ابزار ← نتیجه ← جواب کوتاه)
  - `tools/`: ابزارهای هزینه، یادآور و عمومی (گزارش، تاریخ، تنظیمات) همراه با بررسی ورودی‌ها
  - `actions.py`: ثبت کارهای انجام‌شده برای ↩️ برگشت
  - `context.py`: اطلاعات هر پیام (زمان فعلی و جدول تاریخ‌ها به شمسی و میلادی)
  - `prompt.py`: پرامپت سیستمی
- `app/llm/`: اتصال به مدل‌ها؛ `client.py` یک سرویس سازگار با OpenAI و `providers.py` زنجیره جایگزینی
  خودکار (Gemini ← Groq ← GitHub ← لوکال)
- `app/bot/`: لایه تلگرام، بدون منطق اصلی برنامه
  - `handlers/`: `assistant.py` (پیام آزاد ← Agent)، چت‌های قبلی، تنظیمات، دسته‌ها، یادآورها، هزینه‌ها و
    گزارش‌ها (دکمه‌ها و روش قانون‌محور پشتیبان)، منو و پیام‌های ناشناخته
  - `agent_ui.py`: کارت نتیجه‌ها با ↩️ برگشت / ✏️ ویرایش
  - `keyboards/`، `middlewares/`، `views.py`، `streaming.py`، `states.py`
- `app/core/`: ابزارهای دقیق زبانی بدون هوش مصنوعی: نرمال‌سازی متن، پیدا کردن ارجاع‌ها
  («تایم دکتر» ← یادآور دکتر) و پارسرهای تاریخ، مبلغ، یادآور و هزینه
- `app/services/`: منطق اصلی برنامه، مستقل از تلگرام (یادآورها، هزینه‌ها، گزارش‌ها، تاریخچه چت، تنظیمات)
- `app/scheduler/`: ارسال یادآورها و خلاصه صبحگاهی
- `app/db/`، `app/utils/`، `migrations/`، `tests/`، `docker/`
- `scripts/eval_agent.py`: سنجش دقت و سرعت هر مدل روی پیام‌های واقعی فارسی و انگلیسی

مسیر هر پیام: **تلگرام ← میدل‌ورها ← `handlers/assistant.py` ← `agent/core.py` ↔ `llm/providers.py` ←
`agent/tools/*` ← `services/*` ← دیتابیس** و نتیجه‌ها به صورت کارت از `bot/agent_ui.py` برمی‌گردند.

### توسعه

دستورات بخش [Development](#development) در بالا را ببینید. شاخه `main` نسخه پایدار و شاخه `dev` برای
توسعه است. برای هر نسخه یک تگ و یک GitHub Release ساخته می‌شود.

### مجوز

[MIT](LICENSE)

</div>
