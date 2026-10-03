"""All user-facing English UI strings live here so wording can be changed in one place.

Messages are sent with HTML parse mode.
"""

# --- Main menu buttons (reply keyboard) ---
BTN_NEW_CHAT = "💬 New Chat"
BTN_NEW_REMINDER = "⏰ New Reminder"
BTN_ADD_EXPENSE = "💰 Add Expense"
BTN_TODAY_REPORT = "📊 Today Report"
BTN_MONTH_REPORT = "📅 Month Report"
BTN_REMINDERS = "📋 Reminders"
BTN_TODOS = "✅ Today To-Dos"
BTN_NOTES = "📝 Notes"
BTN_EXPORT = "📤 Export Excel"
BTN_SETTINGS = "⚙️ Settings"

INPUT_PLACEHOLDER = "Type or send a voice message…"

# --- Bot commands (shown in Telegram's command menu) ---
COMMANDS: dict[str, str] = {
    "start": "Start the assistant",
    "help": "How to use Vira",
    "menu": "Show the main menu",
    "new": "Start a new chat",
    "cancel": "Cancel the current action",
    "backup": "Get a database backup",
}

# --- General messages ---
WELCOME = (
    "👋 Hi {name}, I'm <b>Vira</b>, your personal assistant.\n\n"
    "I can help with reminders, expenses, reports, notes and to-dos. "
    "You can write to me in <b>English or Persian</b> — or just use the menu below."
)

HELP = (
    "<b>How to use Vira</b>\n\n"
    "• Use the menu buttons below, or just write (or speak) what you need.\n"
    "• Examples:\n"
    "  — <i>Doctor tomorrow at 2, remind me in the morning</i>\n"
    "  — <i>Paid 3 million for groceries and 100k for fuel</i>\n"
    "  — <i>فردا ساعت ۲ دکتر دارم، صبح یادم بنداز</i>\n\n"
    "<b>Commands</b>\n"
    "/menu — show the main menu\n"
    "/new — start a new chat\n"
    "/cancel — cancel the current action\n"
    "/backup — get a database backup\n"
    "/help — this message"
)

MENU = "📋 Main menu"
CANCELLED = "❌ Cancelled."
NOTHING_TO_CANCEL = "There's nothing to cancel."

COMING_SOON = "🚧 <b>{feature}</b> is coming in <b>{version}</b>. Stay tuned!"
FREE_TEXT_NOT_READY = (
    "🚧 I can't understand free text yet — that arrives in <b>v0.2</b>.\n"
    "For now, please use the menu below."
)

# --- Settings ---
SETTINGS = (
    "⚙️ <b>Settings</b>\n\n"
    "📅 Calendar: <b>{calendar}</b>\n"
    "🕒 Timezone: <b>{timezone}</b>\n"
    "🗓 Today: <b>{today}</b>\n"
    "🤖 Model: <b>{model}</b> <i>({profile} profile)</i>\n"
    "🎙 Voice: <b>{stt}</b>"
)
CALENDAR_NAMES = {"jalali": "Jalali (Shamsi)", "gregorian": "Gregorian"}
BTN_SWITCH_CALENDAR = "📅 Switch to {calendar}"
CALENDAR_CHANGED = "✅ Calendar set to {calendar}"
STT_ON = "on ({model})"
STT_OFF = "off"
MODEL_NOT_SET = "not set"
