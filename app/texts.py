"""All user-facing English UI strings live here so wording can be changed in one place.

Messages are sent with HTML parse mode.
"""

# --- Main menu buttons (reply keyboard) ---
BTN_NEW_CHAT = "💬 New Chat"
BTN_CHATS = "🗂 Chats"
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
    "chats": "Continue a previous chat",
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
    "• Ask me anything in English or Persian, just write it.\n"
    "• I can calculate (<i>12*350000</i>) and tell you today's date (<i>what's the date?</i>).\n"
    "• 💬 <b>New Chat</b> starts a fresh conversation, 🗂 <b>Chats</b> continues an old one.\n"
    "• Coming soon:\n"
    "  — <i>Doctor tomorrow at 2, remind me in the morning</i>\n"
    "  — <i>Paid 3 million for groceries and 100k for fuel</i>\n\n"
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
UNKNOWN_COMMAND = "I don't know that command. See /help."
UNSUPPORTED_MESSAGE = "I can only read text messages for now."

# --- Chat ---
NEW_CHAT = "🆕 New chat started. Ask me anything!"

# --- Previous chats ---
CHATS_TITLE = "🗂 <b>Your chats</b> ({total})\nPick one to continue it."
CHATS_EMPTY = "🗂 No previous chats yet. Just write a message to start one."
CHATS_CURRENT_MARK = "▶️ "
CHAT_RESUMED = "💬 Continuing: <b>{title}</b>"
CHAT_RESUMED_FOOTER = "<i>Write your message to continue this chat.</i>"
CHAT_RECAP_QUESTION = "🧑 {text}"
CHAT_RECAP_ANSWER = "🤖 {text}"
CHAT_NOT_FOUND = "This chat no longer exists."
CHAT_DELETE_CONFIRM = "🗑 Delete <b>{title}</b>? This can't be undone."
CHAT_DELETED = "🗑 Chat deleted."
BTN_PREV = "◀️"
BTN_NEXT = "▶️"
BTN_DELETE = "🗑 Delete"
BTN_YES_DELETE = "🗑 Yes, delete"
BTN_BACK_TO_CHATS = "🗂 All chats"
BTN_CANCEL = "❌ Cancel"
LLM_EMPTY = "🤔 The model returned an empty answer. Please try rephrasing."
# Plain text (no HTML): these may be appended to a partially streamed answer.
LLM_ERRORS = {
    "unreachable": "⚠️ The AI model isn't reachable right now. Please try again in a moment.",
    "model_missing": "⚠️ The model {model} isn't available. Has it finished downloading?",
    "failed": "⚠️ The AI model failed to answer. Please try again.",
}

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
