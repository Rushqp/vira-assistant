"""v0.5 through the real dispatcher: Excel files from the chat (agent and basic mode) and the
☀️ morning briefing / 🌙 nightly report settings screens."""

from datetime import datetime, time
from io import BytesIO
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from app import texts
from app.config import Calendar
from app.db.models import Expense
from app.services.expenses import ExpenseService
from app.services.reminders import to_utc
from app.services.settings import SettingsService
from tests.fakes import calls, reply, tool

TZ = ZoneInfo("Asia/Tehran")  # the default TZ of the test settings


async def add_expense(env, description: str, amount: int) -> None:
    async with env.db() as session:
        service = ExpenseService(session, TZ, "toman")
        groceries = await service.category_by_name("Groceries")
        session.add(
            Expense(
                amount=amount,
                category_id=groceries.id,
                description=description,
                spent_at=to_utc(datetime.now(TZ)),
            )
        )
        await session.commit()


async def nightly(env) -> tuple[bool, time]:
    async with env.db() as session:
        service = SettingsService(session, Calendar.JALALI)
        return await service.nightly_enabled(), await service.nightly_time(time(22, 0))


# --- Excel files ---


async def test_agent_sends_an_excel_file(env):
    await add_expense(env, "نان", 50_000)
    env.llm.script = [calls(tool("export_expenses", period="this_month")), reply("بفرمایید.")]
    await env.send("اکسل هزینه‌های این ماه رو بده")

    [(name, content, caption)] = env.session.documents
    assert name.startswith("vira-expenses-") and name.endswith(".xlsx")
    assert "1 expense" in caption and "50,000 toman" in caption
    sheet = load_workbook(BytesIO(content))["Expenses"]
    assert [c.value for c in sheet[2]][3] == "نان"
    assert env.session.sent[-1] == "بفرمایید."


async def test_basic_mode_still_sends_excel(env):
    # Empty script: no model can use tools, so the rule-based fallback answers.
    await env.send("اکسل هزینه‌های این ماه")
    assert env.session.sent[-1] == texts.EXPORT_EMPTY
    await add_expense(env, "شیر", 80_000)
    await env.send("یه اکسل از خرج های این ماه بده")
    assert len(env.session.documents) == 1
    await env.send("📤 Export Excel")  # the button of keyboards from before v0.5
    assert len(env.session.documents) == 2


async def test_any_table_as_excel(env):
    env.llm.script = [
        calls(
            tool(
                "make_spreadsheet",
                title="Weekly plan",
                sheets=[{"columns": ["Day", "Workout"], "rows": [["Saturday", "Running"]]}],
            )
        ),
        reply(""),
    ]
    await env.send("یه برنامه ورزشی هفتگی به صورت اکسل بده")
    [(name, _, caption)] = env.session.documents
    assert name == "Weekly-plan.xlsx" and "Weekly plan" in caption


# --- ⚙️ Settings → 🌙 Nightly report / ☀️ Morning briefing ---


async def test_nightly_report_screen(env):
    await env.send(texts.BTN_SETTINGS)
    assert "Nightly report: <b>on (22:00)</b>" in env.session.sent[-1]
    await env.press(env.button(texts.BTN_NIGHTLY_SETTINGS))
    assert texts.DIGEST_TITLES["nightly"] in env.session.edits[-1]
    assert env.button(texts.BTN_SELECTED + "22:00")

    await env.press(env.button("23:00"))
    assert await nightly(env) == (True, time(23, 0))
    assert env.session.alerts[-1] == "✅ Nightly report: on (23:00)"
    await env.press(env.button(texts.BTN_DIGEST_OFF))
    assert await nightly(env) == (False, time(23, 0))
    assert "<b>Off</b>" in env.session.edits[-1]

    await env.press(env.button(texts.BTN_DIGEST_OTHER))
    assert env.session.sent[-1] == texts.DIGEST_ASK_TIME
    await env.send("abc")
    assert env.session.sent[-1] == texts.DIGEST_TIME_RETRY
    await env.send("8 am")
    assert env.session.sent[-1] == texts.DIGEST_NIGHTLY_RANGE
    await env.send("۹:۳۰")  # in the evening
    assert await nightly(env) == (True, time(21, 30))
    assert "Every day at <b>21:30</b>" in env.session.sent[-1]

    await env.press(env.button(texts.BTN_BACK))
    assert "Nightly report: <b>on (21:30)</b>" in env.session.edits[-1]


async def test_morning_briefing_screen(env):
    await env.send(texts.BTN_SETTINGS)
    await env.press(env.button(texts.BTN_BRIEFING_SETTINGS))
    await env.press(env.button("07:00"))
    async with env.db() as session:
        service = SettingsService(session, Calendar.JALALI)
        assert await service.briefing_time(time(8, 0)) == time(7, 0)
        assert await service.briefing_enabled()
    assert env.session.alerts[-1] == "✅ Morning briefing: on (07:00)"


async def test_nightly_report_time_from_the_chat(env):
    env.llm.script = [calls(tool("update_settings", nightly_report_time="23:00")), reply("")]
    await env.send("گزارش شبانه رو ساعت ۱۱ شب بفرست")
    card = env.session.sent[-1]
    assert "🌙 Nightly report at 23:00" in card and "🌙 Nightly report: on" in card
    assert await nightly(env) == (True, time(23, 0))
    await env.press(env.button("Undo"))
    assert await nightly(env) == (True, time(22, 0))  # back to the default
