from sqlalchemy import inspect

from app.config import Calendar
from app.services.settings import KEY_CALENDAR, SettingsService


async def test_migrations_create_settings_table(sessionmaker):
    async with sessionmaker() as session:
        conn = await session.connection()
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert "settings" in tables


async def test_calendar_defaults_to_config(sessionmaker):
    async with sessionmaker() as session:
        service = SettingsService(session, Calendar.GREGORIAN)
        assert await service.get_calendar() == Calendar.GREGORIAN


async def test_toggle_calendar_persists(sessionmaker):
    async with sessionmaker() as session:
        service = SettingsService(session, Calendar.JALALI)
        assert await service.toggle_calendar() == Calendar.GREGORIAN

    async with sessionmaker() as session:
        service = SettingsService(session, Calendar.JALALI)
        assert await service.get_calendar() == Calendar.GREGORIAN
        assert await service.toggle_calendar() == Calendar.JALALI
        assert await service.get(KEY_CALENDAR) == "jalali"


async def test_invalid_stored_value_falls_back_to_default(sessionmaker):
    async with sessionmaker() as session:
        service = SettingsService(session, Calendar.JALALI)
        await service.set(KEY_CALENDAR, "lunar")
        assert await service.get_calendar() == Calendar.JALALI


async def test_migrations_are_idempotent(config, sessionmaker):
    from app.db.session import run_migrations

    run_migrations(config.database_url)  # second run must be a no-op
