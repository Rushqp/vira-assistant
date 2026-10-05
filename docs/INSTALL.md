<div align="center">

# 📦 Installing Vira

[English](#english) · [فارسی](#فارسی)

</div>

---

<a id="english"></a>

## 🇬🇧 English

Everything you need to run Vira on your own server, from a fresh Linux server to the first
message. It takes about 15 minutes, most of it waiting for downloads.

### 1. The server and the profile

You need a **Linux server** (Ubuntu 22.04 / 24.04 or Debian 12 / 13, x86-64 or ARM64). Any small
VPS works. Check what it has:

```bash
free -h     # RAM: the "total" column of the "Mem" row
nproc       # CPU cores
df -h /     # free disk: the "Avail" column
```

Then pick a **profile** (the installer suggests one from your RAM):

| RAM | Profile | What runs on the server | Free disk |
|---|---|---|---|
| 1 GB or more | `remote` | only the bot (≈ 210 MB of RAM); the AI and voice come from free APIs | 3 GB |
| 2 GB | `lite` | + a small local chat model (`gemma3:1b`) as a backup | 15 GB |
| 4 GB | `standard` | + a local agent model (`qwen3:4b`) and a voice model (Whisper `small`) as backups | 20 GB |
| 8 GB or more | `full` | + bigger local models (`qwen3:8b`, Whisper `large-v3-turbo`) | 25 GB |

- **Not sure? Choose `remote` with a free API key.** It is the smartest and fastest option, runs on
  the smallest servers, and needs no big downloads. The other profiles add a local "backup
  brain" for when the APIs can't be reached, and can run with no API key at all (slower, on
  the CPU).
- The local profiles download the Ollama image (about 3.6 GB) and a model on the first start.
- On servers with 4 GB of RAM or less, a swap file avoids out-of-memory crashes when a local
  model is loaded:

  ```bash
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  ```

### 2. Three things to prepare

1. **A bot token:** in Telegram, open [@BotFather](https://t.me/BotFather), send `/newbot`, choose a
   name and a username that ends in `bot`, and copy the token (`123456789:AA…`).
2. **Your numeric Telegram ID:** open [@userinfobot](https://t.me/userinfobot) and copy the `Id`.
   Only this account can use the bot.
3. **A free AI key** (recommended; `remote` needs at least one):
   - [Google AI Studio](https://aistudio.google.com/apikey) → *Create API key* (Gemini)
   - [Groq](https://console.groq.com/keys) → *Create API Key* (also transcribes voice messages)
   - more free providers: [README → AI models](../README.md#ai-models)

Keys go only into the `.env` file on your server. Don't paste them into chats.

### 3. Install

#### Option A: one command (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/Rushqp/vira-assistant/main/install.sh | bash
```

The installer:

1. installs `git` and Docker if they are missing (it uses `sudo` when you aren't root);
2. downloads Vira into `~/vira-assistant`;
3. asks for the token, your ID, the API keys, the profile (suggested from your RAM) and, only if
   something is blocked on your server, the proxies and mirrors (see [section 5](#iran));
4. writes your answers to `~/vira-assistant/.env` (readable only by you);
5. builds and starts Vira.

Running it again **updates** Vira and keeps your settings and data. Options, set before `bash`:
`VIRA_DIR=/opt/vira` (another folder), `VIRA_BRANCH=dev` (the development version), and any
answer in advance, e.g. `curl -fsSL … | PROFILE=remote bash`.

#### Option B: by hand

```bash
curl -fsSL https://get.docker.com | sudo sh     # Docker (or: sudo apt install docker.io docker-compose-v2)
git clone https://github.com/Rushqp/vira-assistant.git ~/vira-assistant
cd ~/vira-assistant
cp .env.example .env && chmod 600 .env
nano .env                                       # BOT_TOKEN, OWNER_ID, API keys, PROFILE (see below)
sudo docker compose up -d --build
```

In `.env`, set at least `BOT_TOKEN`, `OWNER_ID`, `PROFILE` and one API key. For `remote`, also
make `COMPOSE_PROFILES=` empty (no local Ollama). Every setting is explained in the file itself.

### 4. Check that it works

```bash
cd ~/vira-assistant
docker compose ps             # vira-bot should be "Up … (healthy)" within about 2 minutes
docker compose logs -f bot    # look for "Vira v1.0.0 started as @your_bot" (Ctrl+C to leave)
```

(If Docker answers *permission denied*, put `sudo` in front of the `docker` commands.)

Then, in Telegram, send `/start` to your bot and `/status` to see the version, uptime, AI
models, voice engine, memory use, your data and the last backup.

- With a local profile, the first start waits for the model download:
  `docker compose logs -f ollama-init`. If the download fails, the bot starts anyway and uses
  the APIs; `docker compose up -d` tries the download again.
- If something goes wrong while Vira runs, it sends you a short ⚠️ error report in Telegram
  (at most one every 10 minutes); the details are in the log.
- Docker checks the bot every minute (the health check). A bot that hangs restarts by itself.

<a id="iran"></a>

### 5. A server in Iran

Several services refuse Iranian servers. Vira works anyway, with these settings (the installer
asks for them; or edit `.env` and run `docker compose up -d`):

| Blocked | Setting |
|---|---|
| raw.githubusercontent.com (the one-command install) | clone first, then run the installer from the clone: `git clone https://github.com/Rushqp/vira-assistant.git ~/vira-assistant && bash ~/vira-assistant/install.sh` |
| Telegram | `TELEGRAM_PROXY` |
| The AI services (Gemini, Groq, Mistral, GitHub, OpenRouter) | `API_PROXY`. It is also used for voice transcription and for downloading the local models (Ollama, Whisper) |
| Docker's installer (download.docker.com) | nothing: the installer falls back to Ubuntu / Debian's own `docker.io` package |
| Docker Hub (the `python` and `ollama` images) | `REGISTRY_MIRROR`: the address of a Docker Hub mirror (Iranian cloud providers run public ones) |
| PyPI (Python packages, while building) | `PIP_INDEX_URL`: a PyPI mirror, e.g. `https://<mirror>/simple` |
| Hugging Face (local Whisper model) | `API_PROXY`, or `HF_ENDPOINT=<mirror>` in `.env` |

**Proxy format:** `socks5://host:port`, `socks5://user:password@host:port` or `http://host:port`.
Names are resolved by the proxy, so DNS filtering doesn't matter (`socks5h://` isn't needed). The
same proxy can be used for both settings.

- **A proxy on another server:** use its address.
- **A proxy program on this server** (e.g. a v2ray / xray client): Vira runs inside Docker, where
  `127.0.0.1` is the container itself. Use `socks5://host.docker.internal:PORT`, and make the
  program listen on `0.0.0.0` instead of `127.0.0.1`. Keep that port closed to the internet; with
  `ufw` that is the default, and Docker's networks need one rule:
  `sudo ufw allow from 172.16.0.0/12 to any port PORT proto tcp`.
- **Test a proxy** on the server: `curl -x socks5h://HOST:PORT -sI https://api.telegram.org`
  should print an HTTP status line.
- **Recommended profile in Iran: `remote`.** It needs no big downloads (the Ollama image and the
  models are several GB through the mirror and the proxy), and the free APIs are far smarter
  than a CPU model. If a model download fails behind a SOCKS proxy, an HTTP proxy is the most
  compatible choice for `API_PROXY`.

### 6. Daily care

| Task | How |
|---|---|
| Update | run the installer again, or `cd ~/vira-assistant && git pull && docker compose up -d --build` |
| Change a setting | edit `.env`, then `docker compose up -d` |
| Logs | `docker compose logs -f bot` |
| Restart / stop | `docker compose restart bot` / `docker compose down` |
| Back up | `/backup` in the bot (a copy also comes every Friday night) |
| Move to a new server | install there, then send the backup file to the bot and confirm |
| Free disk space | `docker image prune -f` (old images) |

Your data lives in `./data` (the database and the voice models) and `./models` (Ollama); updates
never touch them, and database changes are applied automatically at startup.

### 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `Invalid or missing settings in .env: BOT_TOKEN` (or another name) | that setting is empty or wrong in `.env` |
| `Telegram rejected BOT_TOKEN` | copy the token again from @BotFather (`/mybots` → API Token) |
| The log shows connection errors to Telegram | Telegram is blocked: set `TELEGRAM_PROXY` |
| The bot doesn't answer you | `OWNER_ID` must be your ID from @userinfobot; messages from anyone else are ignored |
| "isn't available" notices for every model | the API keys are wrong, the free quota is used up, or the services are blocked (`API_PROXY`) |
| `docker compose` isn't found | install Docker Compose v2: `sudo apt install docker-compose-v2` (or Docker's installer) |
| The build fails while installing packages | PyPI is blocked or slow: set `PIP_INDEX_URL`, then `docker compose up -d --build` |
| `pull access denied` / `403` for an image | Docker Hub is blocked: set a registry mirror (section 5) |
| The server freezes or the bot is killed | too little RAM: add swap (section 1) or use a smaller profile |
| `vira-bot` is "unhealthy" | `docker compose logs --tail 100 bot`; a stuck bot restarts by itself |

---

<a id="فارسی"></a>

<div dir="rtl">

## 🇮🇷 فارسی

هر چیزی که برای اجرای ویرا روی سرور خودتان لازم است، از یک سرور لینوکسی تازه تا اولین پیام. حدود ۱۵ دقیقه
طول می‌کشد که بیشترش منتظر دانلود ماندن است.

### ۱. سرور و پروفایل

یک **سرور لینوکسی** لازم دارید (Ubuntu 22.04 / 24.04 یا Debian 12 / 13، با پردازنده x86-64 یا ARM64). هر
VPS کوچکی کافی است. مشخصات سرور را این‌طور ببینید:

</div>

```bash
free -h     # رم: ستون total در ردیف Mem
nproc       # تعداد هسته‌های پردازنده
df -h /     # فضای خالی دیسک: ستون Avail
```

<div dir="rtl">

بعد یک **پروفایل** انتخاب کنید (نصب‌کننده بر اساس رم سرور یکی را پیشنهاد می‌دهد):

| رم | پروفایل | چه چیزی روی سرور اجرا می‌شود | فضای خالی دیسک |
|---|---|---|---|
| ۱ گیگ یا بیشتر | `remote` | فقط خود ربات (حدود ۲۱۰ مگابایت رم)؛ هوش مصنوعی و تبدیل صدا از APIهای رایگان | ۳ گیگ |
| ۲ گیگ | `lite` | به‌علاوه یک مدل چت کوچک لوکال (`gemma3:1b`) به‌عنوان پشتیبان | ۱۵ گیگ |
| ۴ گیگ | `standard` | به‌علاوه مدل Agent لوکال (`qwen3:4b`) و مدل صدا (Whisper `small`) به‌عنوان پشتیبان | ۲۰ گیگ |
| ۸ گیگ یا بیشتر | `full` | به‌علاوه مدل‌های لوکال بزرگ‌تر (`qwen3:8b` و Whisper `large-v3-turbo`) | ۲۵ گیگ |

- **مطمئن نیستید؟ `remote` را با یک کلید API رایگان انتخاب کنید.** باهوش‌ترین و سریع‌ترین حالت است، روی
  کوچک‌ترین سرورها هم اجرا می‌شود و دانلود حجیمی ندارد. پروفایل‌های دیگر یک «مغز پشتیبان» لوکال اضافه
  می‌کنند برای وقتی که APIها در دسترس نیستند، و بدون هیچ کلید API هم کار می‌کنند (کندتر، روی CPU).
- پروفایل‌های لوکال در اولین اجرا ایمیج Ollama (حدود ۳٫۶ گیگ) و یک مدل را دانلود می‌کنند.
- روی سرورهای با رم ۴ گیگ یا کمتر، یک فایل swap جلوی کرش شدن به خاطر کمبود رم را وقتی مدل لوکال
  بارگذاری می‌شود می‌گیرد:

</div>

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

<div dir="rtl">

### ۲. سه چیزی که باید آماده کنید

۱. **توکن ربات:** در تلگرام [@BotFather](https://t.me/BotFather) را باز کنید، `/newbot` را بفرستید، یک اسم و
یک نام کاربری که به `bot` ختم شود انتخاب کنید و توکن را کپی کنید (`123456789:AA…`).

۲. **شناسه عددی تلگرام شما:** [@userinfobot](https://t.me/userinfobot) را باز کنید و `Id` را کپی کنید. فقط
همین حساب می‌تواند از ربات استفاده کند.

۳. **یک کلید رایگان هوش مصنوعی** (پیشنهادی؛ برای `remote` حداقل یکی لازم است):
- [Google AI Studio](https://aistudio.google.com/apikey) ← *Create API key* (برای Gemini)
- [Groq](https://console.groq.com/keys) ← *Create API Key* (پیام‌های صوتی را هم به متن تبدیل می‌کند)
- سرویس‌های رایگان دیگر: [README ← مدل‌های هوش مصنوعی](../README.md#ai-models)

کلیدها فقط داخل فایل `.env` روی سرور خودتان قرار می‌گیرند؛ آن‌ها را در هیچ چتی نفرستید.

### ۳. نصب

#### روش اول: با یک دستور (پیشنهادی)

</div>

```bash
curl -fsSL https://raw.githubusercontent.com/Rushqp/vira-assistant/main/install.sh | bash
```

<div dir="rtl">

نصب‌کننده این کارها را انجام می‌دهد:

۱. اگر `git` و داکر نصب نباشند، نصبشان می‌کند (اگر کاربر root نباشید از `sudo` استفاده می‌کند)؛

۲. ویرا را در `~/vira-assistant` دانلود می‌کند؛

۳. توکن، شناسه شما، کلیدهای API، پروفایل (با پیشنهاد بر اساس رم) و فقط اگر چیزی روی سرورتان مسدود باشد،
پراکسی‌ها و میرورها را می‌پرسد ([بخش ۵](#iran-fa) را ببینید)؛

۴. جواب‌ها را در `~/vira-assistant/.env` می‌نویسد (فقط خودتان می‌توانید آن را بخوانید)؛

۵. ویرا را می‌سازد و اجرا می‌کند.

اجرای دوباره نصب‌کننده ویرا را **به‌روز** می‌کند و تنظیمات و اطلاعات شما را نگه می‌دارد. گزینه‌ها (قبل از
`bash` بنویسید): `VIRA_DIR=/opt/vira` (پوشه دیگر)، `VIRA_BRANCH=dev` (نسخه در حال توسعه) و جواب هر سوال از
قبل، مثلاً `curl -fsSL … | PROFILE=remote bash`.

#### روش دوم: دستی

</div>

```bash
curl -fsSL https://get.docker.com | sudo sh     # داکر (یا: sudo apt install docker.io docker-compose-v2)
git clone https://github.com/Rushqp/vira-assistant.git ~/vira-assistant
cd ~/vira-assistant
cp .env.example .env && chmod 600 .env
nano .env                                       # BOT_TOKEN، OWNER_ID، کلیدهای API و PROFILE
sudo docker compose up -d --build
```

<div dir="rtl">

در `.env` حداقل `BOT_TOKEN`، `OWNER_ID`، `PROFILE` و یک کلید API را تنظیم کنید. برای `remote` مقدار
`COMPOSE_PROFILES=` را هم خالی بگذارید (بدون Ollama لوکال). توضیح همه تنظیمات داخل خود فایل آمده است.

### ۴. بررسی درست کار کردن

</div>

```bash
cd ~/vira-assistant
docker compose ps             # تا حدود ۲ دقیقه وضعیت vira-bot باید Up … (healthy) شود
docker compose logs -f bot    # دنبال Vira v1.0.0 started as @your_bot بگردید (خروج با Ctrl+C)
```

<div dir="rtl">

(اگر داکر خطای *permission denied* داد، `sudo` را اول دستورهای `docker` بنویسید.)

بعد در تلگرام `/start` را به ربات بفرستید و با `/status` نسخه، مدت روشن بودن، مدل‌های هوش مصنوعی، موتور
تبدیل صدا، مصرف رم، اطلاعات ذخیره‌شده و آخرین پشتیبان را ببینید.

- با پروفایل لوکال، اولین اجرا منتظر دانلود مدل می‌ماند: `docker compose logs -f ollama-init`. اگر دانلود
  ناموفق باشد، ربات به هر حال اجرا می‌شود و از APIها استفاده می‌کند؛ `docker compose up -d` دوباره دانلود را
  امتحان می‌کند.
- اگر هنگام کار ویرا خطایی پیش بیاید، یک گزارش کوتاه ⚠️ در تلگرام برایتان می‌فرستد (حداکثر یکی در هر ۱۰
  دقیقه)؛ جزئیات در لاگ است.
- داکر هر دقیقه سلامت ربات را بررسی می‌کند و رباتی که گیر کرده باشد خودش ری‌استارت می‌شود.

<a id="iran-fa"></a>

### ۵. سرور داخل ایران

چند سرویس به سرورهای ایرانی سرویس نمی‌دهند. ویرا با این تنظیمات به هر حال کار می‌کند (نصب‌کننده آن‌ها را
می‌پرسد؛ یا `.env` را ویرایش کنید و `docker compose up -d` را اجرا کنید):

| مسدود | تنظیم |
|---|---|
| raw.githubusercontent.com (نصب با یک دستور) | اول کلون کنید و بعد نصب‌کننده را از همان‌جا اجرا کنید: `git clone https://github.com/Rushqp/vira-assistant.git ~/vira-assistant && bash ~/vira-assistant/install.sh` |
| تلگرام | `TELEGRAM_PROXY` |
| سرویس‌های هوش مصنوعی (Gemini، Groq، Mistral، GitHub، OpenRouter) | `API_PROXY`؛ برای تبدیل صدا و دانلود مدل‌های لوکال (Ollama و Whisper) هم استفاده می‌شود |
| نصب‌کننده داکر (download.docker.com) | لازم نیست کاری کنید: نصب‌کننده خودکار از بسته `docker.io` خود Ubuntu / Debian استفاده می‌کند |
| Docker Hub (ایمیج‌های `python` و `ollama`) | `REGISTRY_MIRROR`: آدرس یک میرور Docker Hub (سرویس‌دهنده‌های ابری ایرانی میرور عمومی دارند) |
| PyPI (بسته‌های پایتون هنگام ساخت) | `PIP_INDEX_URL`: یک میرور PyPI، مثل `https://<mirror>/simple` |
| Hugging Face (مدل Whisper لوکال) | `API_PROXY` یا `HF_ENDPOINT=<mirror>` در `.env` |

**فرمت پراکسی:** `socks5://host:port`، `socks5://user:password@host:port` یا `http://host:port`. نام دامنه‌ها
را خود پراکسی پیدا می‌کند، پس فیلترینگ DNS مشکلی ایجاد نمی‌کند (`socks5h://` لازم نیست). برای هر دو تنظیم
می‌شود از یک پراکسی استفاده کرد.

- **پراکسی روی یک سرور دیگر:** همان آدرس را بنویسید.
- **برنامه پراکسی روی همین سرور** (مثلاً کلاینت v2ray / xray): ویرا داخل داکر اجرا می‌شود و آن‌جا `127.0.0.1`
  خود کانتینر است. آدرس `socks5://host.docker.internal:PORT` را بنویسید و برنامه را طوری تنظیم کنید که به‌جای
  `127.0.0.1` روی `0.0.0.0` گوش بدهد. آن پورت را به روی اینترنت بسته نگه دارید؛ با `ufw` این حالت پیش‌فرض
  است و شبکه‌های داکر یک قانون لازم دارند:
  `sudo ufw allow from 172.16.0.0/12 to any port PORT proto tcp`
- **امتحان پراکسی** روی سرور: `curl -x socks5h://HOST:PORT -sI https://api.telegram.org` باید یک خط وضعیت
  HTTP چاپ کند.
- **پروفایل پیشنهادی در ایران: `remote`.** دانلود حجیمی ندارد (ایمیج Ollama و مدل‌ها از طریق میرور و
  پراکسی چند گیگابایت می‌شوند) و APIهای رایگان خیلی باهوش‌تر از مدلی هستند که روی CPU اجرا می‌شود. اگر
  دانلود مدل پشت پراکسی SOCKS ناموفق بود، پراکسی HTTP سازگارترین گزینه برای `API_PROXY` است.

### ۶. نگهداری روزمره

| کار | روش |
|---|---|
| به‌روزرسانی | اجرای دوباره نصب‌کننده، یا `cd ~/vira-assistant && git pull && docker compose up -d --build` |
| تغییر یک تنظیم | ویرایش `.env` و بعد `docker compose up -d` |
| لاگ | `docker compose logs -f bot` |
| ری‌استارت / توقف | `docker compose restart bot` / `docker compose down` |
| پشتیبان‌گیری | `/backup` در ربات (هر جمعه شب هم یک نسخه خودکار می‌آید) |
| انتقال به سرور جدید | آن‌جا نصب کنید، بعد فایل پشتیبان را به ربات بفرستید و تأیید کنید |
| آزاد کردن فضای دیسک | `docker image prune -f` (ایمیج‌های قدیمی) |

اطلاعات شما در `./data` (دیتابیس و مدل‌های صوتی) و `./models` (Ollama) است؛ به‌روزرسانی‌ها به آن‌ها دست
نمی‌زنند و تغییرات دیتابیس هنگام اجرا خودکار اعمال می‌شوند.

### ۷. رفع مشکل

| مشکل | راه‌حل |
|---|---|
| `Invalid or missing settings in .env: BOT_TOKEN` (یا نام دیگری) | آن تنظیم در `.env` خالی یا اشتباه است |
| `Telegram rejected BOT_TOKEN` | توکن را دوباره از BotFather کپی کنید (`/mybots` ← API Token) |
| خطای اتصال به تلگرام در لاگ | تلگرام مسدود است: `TELEGRAM_PROXY` را تنظیم کنید |
| ربات به شما جواب نمی‌دهد | `OWNER_ID` باید شناسه شما از @userinfobot باشد؛ پیام بقیه نادیده گرفته می‌شود |
| اعلان «isn't available» برای همه مدل‌ها | کلیدهای API اشتباه‌اند، سهمیه رایگان تمام شده یا سرویس‌ها مسدودند (`API_PROXY`) |
| دستور `docker compose` پیدا نمی‌شود | Docker Compose v2 را نصب کنید: `sudo apt install docker-compose-v2` (یا نصب‌کننده داکر) |
| ساخت ایمیج هنگام نصب بسته‌ها خطا می‌دهد | PyPI مسدود یا کند است: `PIP_INDEX_URL` را تنظیم کنید و `docker compose up -d --build` |
| خطای `pull access denied` یا `403` برای ایمیج | Docker Hub مسدود است: میرور تنظیم کنید (بخش ۵) |
| سرور هنگ می‌کند یا ربات بسته می‌شود | رم کم است: swap اضافه کنید (بخش ۱) یا پروفایل کوچک‌تری انتخاب کنید |
| وضعیت `vira-bot` برابر unhealthy است | `docker compose logs --tail 100 bot`؛ رباتی که گیر کرده خودش ری‌استارت می‌شود |

</div>
