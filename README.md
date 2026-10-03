<div align="center">

# 🤖 Vira Assistant

**A personal AI assistant on Telegram: reminders, expenses, reports, notes and voice.**
**Runs locally with Docker, understands Persian and English.**

[English](#english) · [فارسی](#فارسی)

![version](https://img.shields.io/badge/version-0.1.0-blue)
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
| v0.2.0 | Ollama + hardware profiles, chat with short memory | ⏳ Next |
| v0.3.0 | Date/time parser (fa/en, both calendars), reminders, scheduler | |
| v0.4.0 | Amount parser, expenses, categories, reports | |
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
| `LLM_BASE_URL` | `http://ollama:11434/v1` | Any OpenAI-compatible endpoint |
| `LLM_MODEL` | profile default | Override the LLM model |
| `LLM_API_KEY` | `ollama` | API key (used by `remote`) |
| `STT_ENABLED` | `true` | Enable voice transcription |
| `STT_MODEL` | profile default | Override the Whisper model |
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
├── main.py            # Entry point: logging → migrations → bot polling
├── config.py          # All settings from .env (pydantic-settings) + hardware profiles
├── texts.py           # Every user-facing string (edit wording here only)
├── bot/               # Telegram layer, no business logic
│   ├── handlers/      #   one file per feature: start, settings, menu (placeholders + fallback)
│   ├── keyboards/     #   reply.py = main menu, inline.py = buttons under messages
│   ├── middlewares/   #   owner_only (single-user guard), logging, db (session per update)
│   └── states.py      #   FSM states for multi-step forms
├── services/          # Business logic, independent of Telegram (settings, …)
├── db/                # models.py = tables, session.py = engine + migrations
└── utils/             # calendar.py = Jalali / Gregorian formatting
migrations/            # Alembic migrations (one file per schema change)
tests/                 # pytest suite
docker/                # Dockerfile + entrypoint
docs/                  # Roadmap and documentation
```

How an update flows: **Telegram → middlewares** (owner check, logging, DB session) **→ handler**
(`bot/handlers`) **→ service** (`services`) **→ database** (`db`).

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
| v0.2.0 | Ollama و پروفایل‌های سخت‌افزاری، چت با حافظه کوتاه | ⏳ بعدی |
| v0.3.0 | پارسر تاریخ و ساعت (فارسی/انگلیسی، هر دو تقویم)، یادآورها، زمان‌بند | |
| v0.4.0 | پارسر مبلغ، هزینه‌ها، دسته‌بندی‌ها، گزارش‌ها | |
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
| `LLM_BASE_URL` | `http://ollama:11434/v1` | هر API سازگار با OpenAI |
| `LLM_MODEL` | پیش‌فرض پروفایل | تعیین دستی مدل زبانی |
| `LLM_API_KEY` | `ollama` | کلید API (برای `remote`) |
| `STT_ENABLED` | `true` | فعال بودن تبدیل صوت به متن |
| `STT_MODEL` | پیش‌فرض پروفایل | تعیین دستی مدل Whisper |
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

- `app/main.py`: نقطه شروع برنامه (لاگ، مایگریشن، اجرای ربات)
- `app/config.py`: همه تنظیمات `.env` و پروفایل‌های سخت‌افزاری
- `app/texts.py`: همه متن‌هایی که کاربر می‌بیند (برای تغییر متن‌ها فقط همین فایل را ویرایش کنید)
- `app/bot/`: لایه تلگرام، بدون منطق اصلی برنامه
  - `handlers/`: برای هر قابلیت یک فایل جدا
  - `keyboards/`: منوی اصلی (`reply.py`) و دکمه‌های زیر پیام (`inline.py`)
  - `middlewares/`: محدودیت دسترسی به مالک، لاگ و باز کردن سشن دیتابیس
  - `states.py`: وضعیت‌های فرم‌های چندمرحله‌ای (FSM)
- `app/services/`: منطق اصلی برنامه، مستقل از تلگرام
- `app/db/`: جدول‌ها (`models.py`) و اتصال دیتابیس و مایگریشن (`session.py`)
- `app/utils/`: ابزارهای کمکی مثل تبدیل تاریخ شمسی و میلادی
- `migrations/`: مایگریشن‌های Alembic
- `tests/`: تست‌ها
- `docker/`: فایل Dockerfile و اسکریپت شروع کانتینر

مسیر هر پیام: **تلگرام ← میدل‌ورها ← هندلر ← سرویس ← دیتابیس**

### توسعه

دستورات بخش [Development](#development) در بالا را ببینید. شاخه `main` نسخه پایدار و شاخه `dev` برای
توسعه است. برای هر نسخه یک تگ و یک GitHub Release ساخته می‌شود.

### مجوز

[MIT](LICENSE)

</div>
