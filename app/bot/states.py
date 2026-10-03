"""FSM states for multi-step forms. Groups are added as features land."""

from aiogram.fsm.state import State, StatesGroup


class ChatState(StatesGroup):
    active = State()
