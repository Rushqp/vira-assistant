"""README screenshots: real bot messages, drawn like a Telegram chat and captured with a headless
Chromium browser (Edge or Chrome).

    python scripts/screenshots.py [--browser PATH]      # writes docs/screenshots/*.png

The conversations go through the real dispatcher with a scripted model and sample data (like
the tests), so every text and button is exactly what the bot sends.
"""

import argparse
import asyncio
import html
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aiogram import Bot  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.methods import EditMessageText, SendDocument, SendMessage  # noqa: E402
from aiogram.types import InlineKeyboardMarkup, Update  # noqa: E402

from app import texts  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db.models import Expense  # noqa: E402
from app.db.session import create_engine, create_sessionmaker, run_migrations  # noqa: E402
from app.main import build_dispatcher  # noqa: E402
from app.services.expenses import ExpenseService  # noqa: E402
from app.services.reminders import to_utc  # noqa: E402
from app.services.todos import TodoService  # noqa: E402
from tests.fakes import (  # noqa: E402
    OWNER_ID,
    FakeLLM,
    FakeSTT,
    RecordingSession,
    _message,
    calls,
    reply,
    tool,
    voice_message,
)

OUT = ROOT / "docs" / "screenshots"
WIDTH, HEIGHT = 430, 880
BROWSERS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google-chrome",
    "chromium",
    "microsoft-edge",
)


@dataclass
class Item:
    side: str  # user | bot
    text: str = ""  # HTML
    buttons: list[list[str]] = field(default_factory=list)
    voice: int = 0  # seconds, for a voice message
    file: str = ""  # file name, for a document


class Capture(RecordingSession):
    """Records every message the bot sends or edits, with its buttons."""

    def __init__(self) -> None:
        super().__init__()
        self.items: list[Item] = []

    async def make_request(self, bot, method, timeout=None):  # noqa: ASYNC109
        if isinstance(method, SendMessage):
            self.items.append(Item("bot", method.text, _buttons(method.reply_markup)))
        elif isinstance(method, EditMessageText) and self.items:
            self.items[-1] = Item("bot", method.text, _buttons(method.reply_markup))
        elif isinstance(method, SendDocument):
            name = method.document.filename  # type: ignore[union-attr]
            self.items.append(Item("bot", method.caption or "", file=name or "file"))
        return await super().make_request(bot, method, timeout)


def _buttons(markup) -> list[list[str]]:
    if not isinstance(markup, InlineKeyboardMarkup):
        return []
    return [[button.text for button in row] for row in markup.inline_keyboard]


class Chat:
    def __init__(self, config: Settings, sessionmaker, llm, stt=None) -> None:
        self.session = Capture()
        self.bot = Bot(
            "123456:TEST",
            session=self.session,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self.dp = build_dispatcher(config, sessionmaker, llm, stt)
        self.counter = 0

    async def say(self, text: str) -> None:
        self.session.items.append(Item("user", html.escape(text)))
        self.counter += 1
        update = Update(update_id=self.counter, message=_message(text, user_id=OWNER_ID))
        await self.dp.feed_update(self.bot, update)

    async def voice(self, seconds: int) -> None:
        self.session.items.append(Item("user", voice=seconds))
        self.counter += 1
        await self.dp.feed_update(
            self.bot, Update(update_id=self.counter, message=voice_message(duration=seconds))
        )


# --- Drawing ---

CSS = """
* { box-sizing: border-box; }
body { margin: 0; width: %(w)spx; height: %(h)spx; overflow: hidden; position: relative;
  font: 15px/1.38 "Segoe UI", Tahoma, "Noto Sans", sans-serif; color: #000;
  background: linear-gradient(160deg, #cfe3b8 0%%, #a9cc93 55%%, #8fbf83 100%%); }
header { position: absolute; top: 0; left: 0; right: 0; height: 56px; background: #fff;
  display: flex; align-items: center; gap: 12px; padding: 0 14px;
  box-shadow: 0 1px 2px rgba(0,0,0,.15); z-index: 2; }
.avatar { width: 40px; height: 40px; border-radius: 50%%; background: #5b8def; color: #fff;
  display: grid; place-items: center; font-weight: 600; font-size: 18px; }
.name { font-weight: 600; } .sub { color: #8a8a8a; font-size: 13px; }
main { position: absolute; top: 56px; bottom: 0; left: 0; right: 0; padding: 10px 10px 14px;
  display: flex; flex-direction: column; justify-content: flex-end; gap: 6px; }
.msg { max-width: 86%%; padding: 7px 10px 4px; border-radius: 14px;
  box-shadow: 0 1px 1px rgba(0,0,0,.12); overflow-wrap: anywhere; }
.bot { margin-right: auto; background: #fff; border-bottom-left-radius: 4px; }
.user { margin-left: auto; background: #effdde; border-bottom-right-radius: 4px; }
.line { min-height: 1em; }
.time { text-align: right; margin-top: 2px; font-size: 11px; color: #9aa59a; }
.user .time { color: #5fa85a; }
code { font-family: Consolas, monospace; font-size: 13px; }
.kb { margin-right: auto; width: 86%%; display: flex; flex-direction: column; gap: 4px;
  margin-top: -2px; }
.row { display: flex; gap: 4px; }
.btn { flex: 1; text-align: center; padding: 8px 6px; border-radius: 8px; font-size: 13.5px;
  color: #fff; background: rgba(32, 72, 32, .38); white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
.voice { display: flex; align-items: center; gap: 10px; min-width: 200px; }
.play { width: 38px; height: 38px; border-radius: 50%%; background: #5fb55a; position: relative; }
.play:after { content: ""; position: absolute; left: 15px; top: 11px; border-style: solid;
  border-width: 8px 0 8px 12px; border-color: transparent transparent transparent #fff; }
.wave { display: flex; align-items: center; gap: 2px; height: 26px; }
.wave i { width: 3px; background: #5fb55a; border-radius: 2px; }
.file { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.file .icon { width: 42px; height: 42px; border-radius: 50%%; background: #5b8def; color: #fff;
  display: grid; place-items: center; font-weight: 700; font-size: 12px; }
.file .fname { font-weight: 600; color: #2b6cb0; }
.file .fsize { color: #8a8a8a; font-size: 12.5px; }
"""


def _lines(text: str) -> str:
    return "".join(
        f'<div class="line" dir="auto">{line or "&nbsp;"}</div>' for line in text.split("\n")
    )


def render(items: list[Item], clock: datetime) -> str:
    blocks = []
    for n, item in enumerate(items):
        stamp = f'<div class="time">{(clock + timedelta(minutes=n // 2)):%H:%M}</div>'
        if item.voice:
            bars = "".join(f'<i style="height:{6 + (i * 37) % 20}px"></i>' for i in range(34))
            body = (
                f'<div class="voice"><div class="play"></div><div><div class="wave">{bars}</div>'
                f'<div class="sub">0:{item.voice:02d}</div></div></div>'
            )
        elif item.file:
            body = (
                f'<div class="file"><div class="icon">XLSX</div><div><div class="fname">'
                f'{html.escape(item.file)}</div><div class="fsize">9.6 KB</div></div></div>'
                + _lines(item.text)
            )
        else:
            body = _lines(item.text)
        blocks.append(f'<div class="msg {item.side}">{body}{stamp}</div>')
        if item.buttons:
            rows = "".join(
                '<div class="row">'
                + "".join(f'<div class="btn">{html.escape(b)}</div>' for b in row)
                + "</div>"
                for row in item.buttons
            )
            blocks.append(f'<div class="kb">{rows}</div>')
    head = (
        '<header><div class="avatar">V</div><div><div class="name">Vira</div>'
        '<div class="sub">bot</div></div></header>'
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        + CSS % {"w": WIDTH, "h": HEIGHT}
        + f"</style></head><body>{head}<main>{''.join(blocks)}</main></body></html>"
    )


def _written(png: Path, wait: float = 20) -> bool:
    """On Windows the browser's launcher returns at once and the file comes a moment later."""
    last = -1
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        size = png.stat().st_size if png.exists() else 0
        if size and size == last:
            return True
        last = size
        time.sleep(0.5)
    return False


def capture(browser: str, page: Path, png: Path, attempts: int = 3) -> None:
    png.unlink(missing_ok=True)
    for attempt in range(attempts):
        # A fresh profile each time: a browser that is already open would take the command.
        profile = page.parent / f"browser-{png.stem}-{attempt}"
        subprocess.run(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--no-first-run",
                f"--user-data-dir={profile}",
                "--force-device-scale-factor=2",
                f"--window-size={WIDTH},{HEIGHT}",
                f"--screenshot={png}",
                page.as_uri(),
            ],
            capture_output=True,
            timeout=60,
        )
        if _written(png):
            return
    raise RuntimeError(f"the browser didn't write {png}")


# --- Conversations (sample data) ---


async def seed_month(sessionmaker, now: datetime) -> None:
    samples = [
        ("خرید هفتگی", 2_400_000, "Groceries", 1), ("بنزین", 600_000, "Fuel", 2),
        ("رستوران", 1_850_000, "Restaurant", 3), ("قبض برق", 450_000, "Bills", 4),
        ("دارو", 320_000, "Health", 5), ("میوه", 700_000, "Groceries", 6),
        ("اسنپ", 280_000, "Transport", 7),
    ]  # fmt: skip
    async with sessionmaker() as session:
        expenses = ExpenseService(session, now.tzinfo, "toman")  # type: ignore[arg-type]
        for description, amount, category, days_ago in samples:
            found = await expenses.category_by_name(category)
            when = now - timedelta(days=min(days_ago, now.day - 1 if now.day > 1 else 0))
            session.add(
                Expense(
                    amount=amount,
                    category_id=found.id,
                    description=description,
                    spent_at=to_utc(when),
                )
            )
        await session.commit()


async def conversations(config: Settings, sessionmaker, now: datetime) -> dict[str, list[Item]]:
    """One dispatcher (handler routers are module singletons); a new screenshot per topic."""
    llm = FakeLLM()
    stt = FakeSTT("یه یادداشت بذار: رمز وای‌فای مهمون 12345678 هست")
    chat = Chat(config, sessionmaker, llm, stt)
    shots: dict[str, list[Item]] = {}

    llm.script = [
        calls(
            tool(
                "add_expenses",
                items=[
                    {"description": "سیگار", "amount_text": "۱۵۰ هزار تومن", "category": "Other"},
                    {
                        "description": "ماست",
                        "amount_text": "۲۰۰ هزار تومن",
                        "category": "Groceries",
                    },
                    {"description": "آب", "amount_text": "۵۰ هزار تومن", "category": "Groceries"},
                ],
            )
        ),
        reply(""),
    ]
    await chat.say("امروز ۳ خرید کردم: سیگار ۱۵۰ هزار تومن، ماست ۲۰۰ هزار تومن، آب ۵۰ هزار تومن")
    tomorrow = (now + timedelta(days=1)).date().isoformat()
    llm.script = [
        calls(
            tool(
                "create_reminder",
                subject="دکتر",
                when_text="فردا ساعت ۲",
                start=f"{tomorrow}T14:00",
                alerts=[f"{tomorrow}T09:00"],
                important=True,
            )
        ),
        reply(""),
    ]
    await chat.say("فردا ساعت ۲ دکتر دارم، صبح یادم بنداز")
    shots["chat"], chat.session.items = chat.session.items, []

    await seed_month(sessionmaker, now)
    llm.script = [calls(tool("get_report", period="this_month")), reply("")]
    await chat.say("این ماه چقدر خرج کردم؟")
    llm.script = [calls(tool("export_expenses", period="this_month")), reply("بفرمایید 👇")]
    await chat.say("اکسلش رو هم بده")
    shots["reports"], chat.session.items = chat.session.items, []

    async with sessionmaker() as session:
        todos = TodoService(session)
        await todos.add(["تمدید بیمه ماشین"], now.date() - timedelta(days=1))
        await todos.add(["نون بخرم", "قبض گاز رو بدم", "به مامان زنگ بزنم"], now.date())
    await chat.say(texts.BTN_TODOS)
    llm.script = [calls(tool("update_todos", query="نون", done=True)), reply("")]
    await chat.say("نون رو خریدم")
    shots["todos"], chat.session.items = chat.session.items, []

    llm.script = [
        calls(
            tool(
                "save_note",
                text="رمز وای‌فای مهمون: 12345678",
                title="رمز وای‌فای مهمون",
                tags=["رمز", "خانه"],
            )
        ),
        reply(""),
    ]
    await chat.voice(6)
    llm.script = [
        calls(tool("find_notes", query="وای‌فای")),
        reply("رمز وای‌فای مهمون 12345678 هست 🔑"),
    ]
    await chat.say("رمز وای‌فای مهمون چی بود؟")
    shots["notes"] = chat.session.items
    return shots


def find_browser(given: str | None) -> str | None:
    return given or next((b for b in BROWSERS if shutil.which(b) or Path(b).exists()), None)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--browser", help="path of Edge / Chrome / Chromium")
    args = parser.parse_args()
    browser = find_browser(args.browser)
    if not browser:
        sys.exit("No Chromium browser found: pass --browser PATH")

    folder = Path(tempfile.mkdtemp(prefix="vira-shots-"))
    try:
        url = f"sqlite+aiosqlite:///{(folder / 'shots.db').as_posix()}"
        run_migrations(url)
        config = Settings(
            _env_file=None, bot_token="123456:TEST", owner_id=OWNER_ID, database_url=url
        )
        engine = create_engine(url)
        now = datetime.now(config.timezone).replace(hour=14, minute=5)
        shots = await conversations(config, create_sessionmaker(engine), now)
        await engine.dispose()

        OUT.mkdir(parents=True, exist_ok=True)
        for name, items in shots.items():
            page = folder / f"{name}.html"
            page.write_text(render(items, now), encoding="utf-8")
            png = OUT / f"{name}.png"
            capture(browser, page, png)
            print(f"{png.relative_to(ROOT)}  ({png.stat().st_size // 1024} KB)")
    finally:
        shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
