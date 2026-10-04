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


class ExpenseForm(StatesGroup):
    """Recording expenses. The draft lives in the FSM data under "expense"."""

    describe = State()  # 💰 Add Expense: waiting for "what and how much"
    amount = State()  # waiting for the amount of one item
    buttons = State()  # waiting for a button press (thousand/million, category, confirm)


class SettingsForm(StatesGroup):
    digest_time = State()  # ⚙️ Settings → ☀️ / 🌙 → 🕐 Other time: waiting for "HH:MM"


class CategoryForm(StatesGroup):
    name = State()  # ⚙️ Settings → 🏷 Categories → ➕ Add: waiting for "emoji name"


class AgentForm(StatesGroup):
    """Context for the next free-text message sent to the agent (data: "hint" / "edit_action")."""

    hint = State()  # ⏰ New Reminder / 💰 Add Expense was tapped
    edit = State()  # ✏️ Edit was tapped on a result card
    pending = State()  # waiting for "thousand or million?" (data: "agent_pending" draft)
