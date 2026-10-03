"""User settings stored in the `settings` key/value table."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Calendar
from app.db.models import Setting

KEY_CALENDAR = "calendar"


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
