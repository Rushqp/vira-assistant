"""User settings stored in the `settings` key/value table."""

from datetime import date, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Calendar
from app.db.models import Setting

KEY_CALENDAR = "calendar"
KEY_BRIEFING = "morning_briefing"  # "on" | "off"
KEY_BRIEFING_TIME = "morning_briefing_time"  # "HH:MM" (default MORNING_BRIEFING_TIME)
KEY_BRIEFING_LAST = "morning_briefing_last"  # ISO date of the last briefing sent
KEY_NIGHTLY = "nightly_report"  # "on" | "off"
KEY_NIGHTLY_TIME = "nightly_report_time"  # "HH:MM" (default DAILY_REPORT_TIME)
KEY_NIGHTLY_LAST = "nightly_report_last"  # ISO date of the last nightly report sent
NIGHTLY_EARLIEST = time(12, 0)  # the nightly report sums up the day: 12:00–23:59
KEY_AI_MODEL = "ai_model"  # "auto" or "provider|model"


class SettingsService:
    def __init__(self, session: AsyncSession, default_calendar: Calendar) -> None:
        self.session = session
        self.default_calendar = default_calendar

    async def get(self, key: str) -> str | None:
        return await self.session.scalar(select(Setting.value).where(Setting.key == key))

    async def set(self, key: str, value: str) -> None:
        row = await self.session.get(Setting, key)
        if row is None:
            self.session.add(Setting(key=key, value=value))
        else:
            row.value = value
        await self.session.commit()

    async def unset(self, key: str) -> None:
        row = await self.session.get(Setting, key)
        if row is not None:
            await self.session.delete(row)
            await self.session.commit()

    async def get_calendar(self) -> Calendar:
        value = await self.get(KEY_CALENDAR)
        try:
            return Calendar(value) if value else self.default_calendar
        except ValueError:
            return self.default_calendar

    async def set_calendar(self, calendar: Calendar) -> None:
        await self.set(KEY_CALENDAR, calendar.value)

    async def toggle_calendar(self) -> Calendar:
        current = await self.get_calendar()
        new = Calendar.GREGORIAN if current == Calendar.JALALI else Calendar.JALALI
        await self.set_calendar(new)
        return new

    # --- AI model ---

    async def get_ai_model(self) -> tuple[str, str] | None:
        """The model the user chose in 🤖 AI model, or None for Auto."""
        value = await self.get(KEY_AI_MODEL)
        if not value or "|" not in value:
            return None
        provider, model = value.split("|", 1)
        return provider, model

    async def set_ai_model(self, provider: str | None, model: str | None = None) -> None:
        await self.set(KEY_AI_MODEL, f"{provider}|{model}" if provider and model else "auto")

    # --- Morning briefing ---

    async def briefing_enabled(self) -> bool:
        return (await self.get(KEY_BRIEFING)) != "off"

    async def toggle_briefing(self) -> bool:
        enabled = not await self.briefing_enabled()
        await self.set_briefing(enabled)
        return enabled

    async def set_briefing(self, enabled: bool) -> None:
        await self.set(KEY_BRIEFING, "on" if enabled else "off")

    async def briefing_sent_on(self) -> date | None:
        value = await self.get(KEY_BRIEFING_LAST)
        return date.fromisoformat(value) if value else None

    async def mark_briefing_sent(self, day: date) -> None:
        await self.set(KEY_BRIEFING_LAST, day.isoformat())

    async def briefing_time(self, default: time) -> time:
        return await self._time(KEY_BRIEFING_TIME, default)

    async def set_briefing_time(self, value: time) -> None:
        await self.set(KEY_BRIEFING_TIME, f"{value:%H:%M}")

    # --- Nightly report ---

    async def nightly_enabled(self) -> bool:
        return (await self.get(KEY_NIGHTLY)) != "off"

    async def set_nightly(self, enabled: bool) -> None:
        await self.set(KEY_NIGHTLY, "on" if enabled else "off")

    async def nightly_time(self, default: time) -> time:
        return await self._time(KEY_NIGHTLY_TIME, default)

    async def set_nightly_time(self, value: time) -> None:
        await self.set(KEY_NIGHTLY_TIME, f"{value:%H:%M}")

    async def nightly_sent_on(self) -> date | None:
        value = await self.get(KEY_NIGHTLY_LAST)
        return date.fromisoformat(value) if value else None

    async def mark_nightly_sent(self, day: date) -> None:
        await self.set(KEY_NIGHTLY_LAST, day.isoformat())

    async def _time(self, key: str, default: time) -> time:
        value = await self.get(key)
        try:
            return time.fromisoformat(value) if value else default
        except ValueError:
            return default
