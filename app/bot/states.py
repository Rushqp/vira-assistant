"""FSM states for multi-step forms. Groups are added as features land."""

from aiogram.fsm.state import State, StatesGroup


class ReminderForm(StatesGroup):
    """Creating a reminder. The draft itself lives in the FSM data under "draft"."""

    describe = State()  # ⏰ New Reminder: waiting for "what and when"
    subject = State()  # waiting for what to remind about
    when = State()  # waiting for a date / time
    time = State()  # waiting for a clock time
    alert_time = State()  # waiting for a custom notification time
    buttons = State()  # waiting for a button press (am/pm, alerts, confirm)
