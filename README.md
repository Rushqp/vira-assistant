<div align="center">

# 🤖 Vira Assistant

**A personal AI assistant on Telegram: reminders, expenses, reports, notes and voice.**
**Runs locally with Docker, understands Persian and English.**

[English](#english) · [فارسی](#فارسی)

![version](https://img.shields.io/badge/version-0.3.0-blue)
![python](https://img.shields.io/badge/python-3.12-3776AB)
![license](https://img.shields.io/badge/license-MIT-green)
[![CI](https://github.com/Rushqp/vira-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/Rushqp/vira-assistant/actions/workflows/ci.yml)

</div>

---

<a id="english"></a>

## 🇬🇧 English

### What is Vira?

Vira is a **single-user** assistant you run on your own server (even a weak one) and talk to through a
Telegram bot with a button menu. You can write or speak in **Persian or English**:

- ⏰ **Reminders**: *"Doctor tomorrow at 2, remind me in the morning"*
- 💰 **Expenses**: *"Paid 3 million for groceries and 100k for 10 liters of fuel"*
- 📊 **Reports**: daily / weekly / monthly, exported to **Excel / CSV**
- 📝 **Notes & to-dos**
- 🎙 **Voice messages**, transcribed locally
- 💬 **Simple Q&A** with a local LLM (Ollama)
- 📅 Dates in **Jalali (Shamsi)** or **Gregorian**, switchable in Settings

Common actions are handled by a fast rule-based parser. The LLM is used only when needed, so the bot
stays responsive on low-spec hardware.

### Status

| Version | Scope | State |
|---|---|---|
| **v0.1.0** | Skeleton, Docker, menu, owner-only access, SQLite + Alembic, calendar setting, CI | ✅ Done |
| **v0.2.0** | Ollama + hardware profiles, streaming chat with short memory, calculator, today's date | ✅ Done |
| **v0.3.0** | Reminders (fa/en date parser, both calendars, repeats, snooze), morning briefing, previous chats | ✅ Done |
| v0.4.0 | Amount parser, expenses, categories, reports | ⏳ Next |
| v0.5.0 | Excel/CSV export, nightly report, morning briefing | |
| v0.6.0 | Voice → text (faster-whisper) | |
| v0.7.0 | Notes, to-dos, backup | |
| v1.0.0 | Full tests, optimization, install guide | |

The full plan is in [docs/ROADMAP.md](docs/ROADMAP.md).

### Quick start

**Requirements:** Docker with Docker Compose, a Telegram bot token, and your numeric Telegram ID.

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Get your numeric user ID from [@userinfobot](https://t.me/userinfobot).
3. Clone and configure:

   ```bash
   git clone https://github.com/Rushqp/vira-assistant.git
   cd vira-assistant
   cp .env.example .env      # then set BOT_TOKEN and OWNER_ID
   ```

4. Start it:

   ```bash
   docker compose up -d --build
   docker compose logs -f bot
   ```

5. Open your bot in Telegram and send `/start`.

On the first start, the `ollama-init` container downloads the model for your profile (about 2 GB for
`standard`). Until it finishes, the bot waits. Follow the progress with `docker compose logs -f ollama-init`.

**Using an external API instead of Ollama** (`PROFILE=remote`): set `COMPOSE_PROFILES=` (empty) so the
Ollama containers are not started, and set `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY` for any
OpenAI-compatible provider (OpenRouter, Gemini, OpenAI, …).

### Using it

- **Chat:** just write. 💬 **New Chat** starts a fresh conversation; 🗂 **Chats** lists previous ones
  so you can continue any of them.
- **Reminders:** write them naturally, in Persian or English:
  - *Doctor tomorrow at 2, remind me in the morning*
  - *فردا ساعت ۸ یادم بنداز به مامان زنگ بزنم*
  - *تولد مامان ۱۵ مهر، شب قبلش یادم بنداز*
  - *remind me every Saturday at 8am to go to the gym* · *۱۰ دقیقه دیگه یادم بنداز*

  If something is missing, Vira asks: am or pm for "at 2", the time, and when to notify you (you can
  pick several, e.g. *1 hour before* + *at the time*). Important reminders (doctor, bills, flights, …)
  are detected by the model and marked ⭐. Notifications have **Done**, **+10 min** and **+1 hour**
  buttons. 📋 **Reminders** lists, edits and deletes them.
- **Morning briefing:** every day at 08:00 you get today's reminders, important ones first
  (can be turned off in ⚙️ Settings).

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
| `LLM_BASE_URL` | `http://ollama:11434/v1` | Any OpenAI-compatible endpoint |
| `LLM_MODEL` | profile default | Override the LLM model (**required** for `remote`) |
| `LLM_API_KEY` | `ollama` | API key (used by `remote`) |
| `LLM_TIMEOUT` | `180` | Seconds to wait for an answer |
| `CHAT_MEMORY` | `10` | How many previous messages the chat remembers (0–50) |
| `CHAT_KEEP` | `20` | How many previous chats are kept in 🗂 Chats |
| `OLLAMA_KEEP_ALIVE` | `30m` | How long the model stays in RAM after use (`-1` = forever) |
| `STT_ENABLED` | `true` | Enable voice transcription |
| `STT_MODEL` | profile default | Override the Whisper model |
| `MORNING_TIME` … `NIGHT_TIME` | `09:00` `12:00` `16:00` `19:00` `22:00` | Clock times for morning, noon, afternoon, evening, night (`MORNING_TIME`, `NOON_TIME`, `AFTERNOON_TIME`, `EVENING_TIME`, `NIGHT_TIME`) |
| `MORNING_BRIEFING_TIME` | `08:00` | Daily list of today's reminders |
| `DAILY_REPORT_TIME` | `22:00` | Time of the nightly report |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` … |

**Hardware profiles**

| Profile | RAM | LLM | Whisper |
|---|---|---|---|
| `lite` | 2 GB | `gemma3:1b` | `tiny` |
| `standard` | 4 GB | `qwen2.5:3b` | `base` |
| `full` | 8 GB+ | `qwen2.5:7b` | `small` |
| `remote` | — | external API | `base` |

### Source code map

```
app/
├── main.py            # Entry point: logging → migrations → scheduler → bot polling
├── config.py          # All settings from .env (pydantic-settings) + hardware profiles
├── texts.py           # Every user-facing string (edit wording here only)
├── bot/               # Telegram layer, no business logic
│   ├── handlers/      #   one file per feature: start, settings, chat, chats, reminders,
│   │                  #   menu (placeholders), fallback
│   ├── keyboards/     #   reply.py = main menu, inline.py = buttons under messages
│   ├── middlewares/   #   owner_only, logging, db (session + services), menu_reset (leave forms)
│   ├── views.py       #   message rendering: reminder cards, notifications, morning briefing
│   ├── streaming.py   #   shows a streamed answer by editing the Telegram message
│   └── states.py      #   FSM states for multi-step forms
├── core/              # Language processing (no LLM)
│   ├── normalizer.py  #   fa/en digits, number words, Arabic letters, ZWNJ
│   └── parsers/       #   datetime_parser.py (dates, times, repeats), rules.py (reminder sentences)
├── llm/               # client.py = OpenAI-compatible client, prompts/, schemas.py (JSON output)
├── services/          # Business logic, independent of Telegram: settings, chat, tools,
│                      #   reminders (drafts, time maths, storage), reminder_ai (LLM help)
├── scheduler/         # jobs.py = due reminders + morning briefing, setup.py = APScheduler
├── db/                # models.py = tables, session.py = engine + migrations
└── utils/             # calendar.py = Jalali / Gregorian, formatting.py = Markdown → Telegram HTML
migrations/            # Alembic migrations (one file per schema change)
tests/                 # pytest suite (no network or real model needed)
docker/                # Dockerfile, entrypoint, ollama-init.sh (pulls the profile model)
docs/                  # Roadmap and documentation
```

How an update flows: **Telegram → middlewares** (owner check, logging, DB session) **→ handler**
(`bot/handlers`) **→ service** (`services`) **→ database** (`db`) / **LLM** (`llm`).

A free-text message with "remind me" / «یادم بنداز» goes to `handlers/reminders.py`:
`core/parsers` extract the event time, notification time and subject, `services/reminders.py`
decides what still needs asking, and `scheduler/jobs.py` sends the notifications. Any other text
goes to `handlers/chat.py`: calculator and date questions get an instant answer from
`services/tools.py`, everything else is answered by the model via `services/chat.py`.

### Development

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env               # set BOT_TOKEN and OWNER_ID
python -m app.main                 # run the bot locally (DB in ./data)

pytest                             # tests
ruff check . && ruff format .      # lint + format
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

ویرا یک دستیار شخصی **تک‌کاربره** است که روی سرور خودتان (حتی یک سرور ضعیف) اجرا می‌شود و از طریق یک
ربات تلگرام با منوی دکمه‌ای با آن کار می‌کنید. می‌توانید به **فارسی یا انگلیسی** بنویسید یا پیام صوتی بفرستید:

- ⏰ **یادآور**: «فردا ساعت ۲ دکتر دارم، صبح یادم بنداز»
- 💰 **ثبت هزینه**: «۳ میلیون خرید خونه دادم، ۱۰ لیتر بنزین هم ۱۰۰ تومن»
- 📊 **گزارش**: روزانه، هفتگی و ماهانه، با خروجی **اکسل و CSV**
- 📝 **یادداشت و کارهای روزانه**
- 🎙 **پیام صوتی** که روی همان سرور به متن تبدیل می‌شود
- 💬 **پرسش و پاسخ ساده** با مدل زبانی لوکال (Ollama)
- 📅 نمایش تاریخ به **شمسی** یا **میلادی** (قابل تغییر در تنظیمات)

کارهای پرتکرار با یک پارسر قانون‌محور و سریع انجام می‌شوند و مدل زبانی فقط وقتی لازم باشد صدا زده
می‌شود. به همین دلیل ربات روی سخت‌افزار ضعیف هم سریع می‌ماند.

### وضعیت پروژه

| نسخه | محتوا | وضعیت |
|---|---|---|
| **v0.1.0** | اسکلت پروژه، داکر، منو، دسترسی فقط برای مالک، SQLite و Alembic، تنظیم تقویم، CI | ✅ انجام شد |
| **v0.2.0** | Ollama و پروفایل‌های سخت‌افزاری، چت استریمی با حافظه کوتاه، ماشین‌حساب، تاریخ امروز | ✅ انجام شد |
| **v0.3.0** | یادآورها (پارسر تاریخ فارسی/انگلیسی، هر دو تقویم، تکرار، تعویق)، خلاصه صبحگاهی، چت‌های قبلی | ✅ انجام شد |
| v0.4.0 | پارسر مبلغ، هزینه‌ها، دسته‌بندی‌ها، گزارش‌ها | ⏳ بعدی |
| v0.5.0 | خروجی اکسل/CSV، گزارش شبانه، خلاصه صبحگاهی | |
| v0.6.0 | تبدیل صوت به متن (faster-whisper) | |
| v0.7.0 | یادداشت‌ها، کارهای روزانه، پشتیبان‌گیری | |
| v1.0.0 | تست کامل، بهینه‌سازی، راهنمای نصب | |

نقشه کامل پروژه در [docs/ROADMAP.md](docs/ROADMAP.md) است.

### راه‌اندازی سریع

**پیش‌نیازها:** داکر و Docker Compose، توکن ربات تلگرام و شناسه عددی تلگرام شما.

۱. با [@BotFather](https://t.me/BotFather) یک ربات بسازید و توکن آن را کپی کنید.

۲. شناسه عددی خود را از [@userinfobot](https://t.me/userinfobot) بگیرید.

۳. پروژه را کلون و تنظیم کنید:

</div>

```bash
git clone https://github.com/Rushqp/vira-assistant.git
cd vira-assistant
cp .env.example .env      # BOT_TOKEN و OWNER_ID را تنظیم کنید
```

<div dir="rtl">

۴. اجرا کنید:

</div>

```bash
docker compose up -d --build
docker compose logs -f bot
```

<div dir="rtl">

۵. ربات را در تلگرام باز کنید و `/start` را بفرستید.

در اولین اجرا، کانتینر `ollama-init` مدل مربوط به پروفایل شما را دانلود می‌کند (برای `standard` حدود ۲
گیگ). تا دانلود تمام نشود ربات منتظر می‌ماند. پیشرفت دانلود را با `docker compose logs -f ollama-init`
ببینید.

**استفاده از API خارجی به جای Ollama** (`PROFILE=remote`): مقدار `COMPOSE_PROFILES` را خالی بگذارید تا
کانتینرهای Ollama اجرا نشوند، و `LLM_BASE_URL`، `LLM_MODEL` و `LLM_API_KEY` را برای هر سرویس سازگار با
OpenAI (مثل OpenRouter، Gemini یا OpenAI) تنظیم کنید.

### نحوه استفاده

- **چت:** فقط بنویسید. 💬 **New Chat** گفتگوی تازه شروع می‌کند و 🗂 **Chats** فهرست گفتگوهای قبلی را
  نشان می‌دهد تا هر کدام را ادامه دهید.
- **یادآور:** به زبان طبیعی و به فارسی یا انگلیسی بنویسید:
  - «فردا ساعت ۲ دکتر دارم، صبح یادم بنداز»
  - «فردا ساعت ۸ یادم بنداز به مامان زنگ بزنم»
  - «تولد مامان ۱۵ مهر، شب قبلش یادم بنداز»
  - «هر شنبه ساعت ۸ صبح باشگاه یادم بنداز» · «۱۰ دقیقه دیگه یادم بنداز»

  اگر چیزی ناقص باشد ویرا می‌پرسد: صبح یا عصر بودن ساعت (مثلاً «ساعت ۲»)، ساعت دقیق، و این‌که کی
  یادآوری شود (می‌شود چند گزینه را با هم انتخاب کرد، مثلاً «۱ ساعت قبل» و «سر وقت»). یادآورهای مهم
  (دکتر، قبض، پرواز و …) را مدل زبانی تشخیص می‌دهد و با ⭐ علامت می‌زند. پیام یادآوری دکمه‌های
  **Done**، **+10 min** و **+1 hour** دارد. از 📋 **Reminders** می‌توانید یادآورها را ببینید، ویرایش یا
  حذف کنید.
- **خلاصه صبحگاهی:** هر روز ساعت ۸ صبح فهرست یادآورهای امروز ارسال می‌شود و موارد مهم بالای فهرست
  هستند (در ⚙️ Settings قابل خاموش کردن است).

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
| `LLM_BASE_URL` | `http://ollama:11434/v1` | هر API سازگار با OpenAI |
| `LLM_MODEL` | پیش‌فرض پروفایل | تعیین دستی مدل زبانی (برای `remote` **الزامی**) |
| `LLM_API_KEY` | `ollama` | کلید API (برای `remote`) |
| `LLM_TIMEOUT` | `180` | حداکثر زمان انتظار برای جواب (ثانیه) |
| `CHAT_MEMORY` | `10` | تعداد پیام‌های قبلی که چت به خاطر می‌سپارد (۰ تا ۵۰) |
| `CHAT_KEEP` | `20` | تعداد گفتگوهای قبلی که در 🗂 Chats نگه داشته می‌شود |
| `OLLAMA_KEEP_ALIVE` | `30m` | مدت ماندن مدل در رم بعد از آخرین پیام (`-1` یعنی همیشه) |
| `STT_ENABLED` | `true` | فعال بودن تبدیل صوت به متن |
| `STT_MODEL` | پیش‌فرض پروفایل | تعیین دستی مدل Whisper |
| `MORNING_TIME` … `NIGHT_TIME` | `09:00` `12:00` `16:00` `19:00` `22:00` | ساعت پیش‌فرض صبح، ظهر، بعدازظهر، عصر و شب (`MORNING_TIME`، `NOON_TIME`، `AFTERNOON_TIME`، `EVENING_TIME`، `NIGHT_TIME`) |
| `MORNING_BRIEFING_TIME` | `08:00` | ساعت ارسال خلاصه صبحگاهی |
| `DAILY_REPORT_TIME` | `22:00` | ساعت گزارش شبانه |
| `LOG_LEVEL` | `INFO` | سطح لاگ |

**پروفایل‌های سخت‌افزاری**

| پروفایل | رم | مدل زبانی | Whisper |
|---|---|---|---|
| `lite` | ۲ گیگ | `gemma3:1b` | `tiny` |
| `standard` | ۴ گیگ | `qwen2.5:3b` | `base` |
| `full` | ۸ گیگ و بیشتر | `qwen2.5:7b` | `small` |
| `remote` | — | API خارجی | `base` |

### نقشه سورس کد

- `app/main.py`: نقطه شروع برنامه (لاگ، مایگریشن، زمان‌بند، اجرای ربات)
- `app/config.py`: همه تنظیمات `.env` و پروفایل‌های سخت‌افزاری
- `app/texts.py`: همه متن‌هایی که کاربر می‌بیند (برای تغییر متن‌ها فقط همین فایل را ویرایش کنید)
- `app/bot/`: لایه تلگرام، بدون منطق اصلی برنامه
  - `handlers/`: برای هر قابلیت یک فایل جدا (`chat.py` چت، `chats.py` چت‌های قبلی، `reminders.py`
    یادآورها، `fallback.py` پیام‌های ناشناخته)
  - `keyboards/`: منوی اصلی (`reply.py`) و دکمه‌های زیر پیام (`inline.py`)
  - `middlewares/`: محدودیت دسترسی به مالک، لاگ، باز کردن سشن دیتابیس و خروج از فرم با دکمه‌های منو
  - `views.py`: ساخت متن پیام‌ها (کارت یادآور، اعلان، خلاصه صبحگاهی)
  - `streaming.py`: نمایش تدریجی جواب مدل با ویرایش پیام تلگرام
  - `states.py`: وضعیت‌های فرم‌های چندمرحله‌ای (FSM)
- `app/core/`: پردازش متن بدون مدل زبانی
  - `normalizer.py`: اعداد فارسی، اعداد حروفی («صد و پنجاه»)، حروف عربی و نیم‌فاصله
  - `parsers/`: پیدا کردن تاریخ، ساعت و تکرار (`datetime_parser.py`) و تحلیل جمله یادآور (`rules.py`)
- `app/llm/`: اتصال به مدل زبانی (`client.py`)، پرامپت‌ها (`prompts/`) و قالب خروجی JSON (`schemas.py`)
- `app/services/`: منطق اصلی برنامه، مستقل از تلگرام (تنظیمات، چت، ماشین‌حساب، یادآورها و کمک مدل
  زبانی برای یادآورها)
- `app/scheduler/`: کارهای زمان‌بندی‌شده: ارسال یادآورها و خلاصه صبحگاهی
- `app/db/`: جدول‌ها (`models.py`) و اتصال دیتابیس و مایگریشن (`session.py`)
- `app/utils/`: ابزارهای کمکی مثل تاریخ شمسی/میلادی و تبدیل Markdown به HTML تلگرام
- `migrations/`: مایگریشن‌های Alembic
- `tests/`: تست‌ها (بدون نیاز به اینترنت یا مدل واقعی)
- `docker/`: فایل Dockerfile، اسکریپت شروع کانتینر و `ollama-init.sh` برای دانلود مدل

مسیر هر پیام: **تلگرام ← میدل‌ورها ← هندلر ← سرویس ← دیتابیس / مدل زبانی**

پیامی که «یادم بنداز» یا "remind me" دارد به `handlers/reminders.py` می‌رسد: `core/parsers` زمان رویداد،
زمان اعلان و موضوع را استخراج می‌کند، `services/reminders.py` تعیین می‌کند چه چیزی هنوز باید پرسیده
شود، و `scheduler/jobs.py` اعلان‌ها را ارسال می‌کند. بقیه پیام‌ها به `handlers/chat.py` می‌رسند: محاسبه و
سوال تاریخ فوراً از `services/tools.py` جواب می‌گیرند و بقیه را مدل زبانی از طریق `services/chat.py`
جواب می‌دهد.

### توسعه

دستورات بخش [Development](#development) در بالا را ببینید. شاخه `main` نسخه پایدار و شاخه `dev` برای
توسعه است. برای هر نسخه یک تگ و یک GitHub Release ساخته می‌شود.

### مجوز

[MIT](LICENSE)

</div>
