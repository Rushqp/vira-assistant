from aiogram.types import User

from app.bot.middlewares.owner_only import OwnerOnlyMiddleware

OWNER = 1001


async def _handler(event, data):
    return "handled"


def _user(user_id: int) -> User:
    return User(id=user_id, is_bot=False, first_name="Test")


async def test_owner_is_allowed():
    mw = OwnerOnlyMiddleware(OWNER)
    assert await mw(_handler, object(), {"event_from_user": _user(OWNER)}) == "handled"


async def test_stranger_is_ignored():
    mw = OwnerOnlyMiddleware(OWNER)
    assert await mw(_handler, object(), {"event_from_user": _user(42)}) is None


async def test_update_without_user_is_ignored():
    mw = OwnerOnlyMiddleware(OWNER)
    assert await mw(_handler, object(), {}) is None
