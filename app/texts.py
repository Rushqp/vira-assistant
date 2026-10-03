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
    "• Reminders, just write them:\n"
    "  — <i>Doctor tomorrow at 2, remind me in the morning</i>\n"
    "  — <i>فردا ساعت ۸ یادم بنداز به مامان زنگ بزنم</i>\n"
    "  — <i>remind me every Saturday at 8am to go to the gym</i>\n"
    "• Coming soon: <i>Paid 3 million for groceries and 100k for fuel</i>\n\n"
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

# --- Reminders: creating ---
REMINDER_ASK_DESCRIBE = (
    "⏰ What should I remind you about, and when?\n"
    "<i>e.g. Doctor tomorrow at 14:00 · تولد مامان ۱۵ مهر · call mom in 2 hours</i>"
)
REMINDER_ASK_SUBJECT = "📝 What should I remind you about?"
REMINDER_ASK_WHEN = (
    "🗓 When is it?\n<i>e.g. tomorrow at 8, Saturday evening, ۱۵ مهر ساعت ۱۰, in 2 hours</i>"
)
REMINDER_WHEN_RETRY = "🤔 I couldn't find a date or time in that. " + REMINDER_ASK_WHEN
REMINDER_ASK_AMPM = "🕑 <b>{subject}</b>: did you mean <b>{am}</b> or <b>{pm}</b>?"
REMINDER_ASK_TIME = "🕑 At what time? Pick one or type a time."
REMINDER_TIME_RETRY = "🤔 I couldn't find a time in that. Pick one or type e.g. <i>8:30</i>."
REMINDER_PAST = "⌛ That time has already passed. When should it be?"
REMINDER_ASK_ALERTS = (
    "🔔 When should I remind you? Pick one or more, then press <b>Done</b>.\n\n"
    "📝 {subject}\n🗓 {when}"
)
REMINDER_ALERTS_PAST = "⌛ Those reminder times have already passed. Please pick another one.\n\n"
REMINDER_ALERTS_NONE = "Pick at least one option."
REMINDER_ASK_ALERT_TIME = (
    "🕒 When should I remind you?\n<i>e.g. tomorrow 8:30, 2 hours before, شب قبلش ساعت ۲۱</i>"
)
REMINDER_ALERT_TIME_RETRY = "🤔 I couldn't understand that time. " + REMINDER_ASK_ALERT_TIME
REMINDER_CARD = "📝 {subject}\n🗓 {when}\n🔔 {alerts}{repeat}{important}"
REMINDER_CONFIRM = "⏰ <b>New reminder</b>\n\n{card}"
REMINDER_CONFIRM_EDIT = "✏️ <b>Edited reminder</b>\n\n{card}"
REMINDER_SAVED = "✅ <b>Reminder saved</b>\n\n{card}"
REMINDER_CANCELLED = "❌ Reminder cancelled."
REMINDER_EDIT_PROMPT = "✏️ Send the reminder again with your changes.\n<i>Current: {raw}</i>"
REMINDER_EXPIRED = "This reminder draft has expired. Please create it again."
REMINDER_ALL_DAY = "all day"
REMINDER_REPEAT_LINE = "\n🔁 {repeat}"
REMINDER_IMPORTANT_LINE = "\n⭐ Important"
REPEAT_DAILY = "Every day"
REPEAT_WEEKLY = "Every {weekday}"
REPEAT_MONTHLY = "Monthly on day {day} ({calendar})"
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

BTN_AM = "🌅 {time}"
BTN_PM = "🌇 {time}"
BTN_PART_TIMES = {
    "morning": "☀️ Morning {time}",
    "noon": "🕛 Noon {time}",
    "afternoon": "🌤 Afternoon {time}",
    "evening": "🌆 Evening {time}",
    "night": "🌙 Night {time}",
}
ALERT_LABELS = {
    "at": "🔔 At the time",
    "before:15": "15 min before",
    "before:60": "1 hour before",
    "day_before": "🌙 Night before ({time})",
    "same_day": "☀️ Morning of the day ({time})",
}
BTN_ALERTS_DONE = "✅ Done"
BTN_OTHER_TIME = "🕒 Other time…"
BTN_SAVE = "✅ Save"
BTN_IMPORTANT_ON = "⭐ Important"
BTN_IMPORTANT_OFF = "☆ Not important"
BTN_EDIT = "✏️ Edit"
BTN_SELECTED = "☑️ "

# --- Reminders: list ---
REMINDERS_TITLE = "📋 <b>Upcoming reminders</b> ({count})"
REMINDERS_EMPTY = (
    "📋 No upcoming reminders.\nTap ⏰ New Reminder or just write e.g. "
    "<i>remind me tomorrow at 9 to call mom</i>."
)
REMINDER_DETAIL = "⏰ <b>Reminder</b>\n\n{card}"
REMINDER_DELETE_CONFIRM = "🗑 Delete <b>{subject}</b>?"
REMINDER_DELETED = "🗑 Reminder deleted."
REMINDER_NOT_FOUND = "This reminder no longer exists."
BTN_BACK = "◀️ Back"

# --- Reminders: notifications ---
NOTIFY = "⏰ <b>{subject}</b>\n🗓 {when}{relative}"
NOTIFY_IN = "\n⏳ in {delta}"
NOTIFY_NOW = "\n⏳ now"
NOTIFY_LATE = "\n<i>(sent late: the bot was offline)</i>"
BTN_NOTIFY_DONE = "✅ Done"
BTN_SNOOZE_10 = "⏰ +10 min"
BTN_SNOOZE_60 = "⏰ +1 hour"
SNOOZED = "⏰ I'll remind you again at {time}"
MARKED_DONE = "✅ Done"
MARKED_DONE_LINE = "\n\n✅ <i>Done</i>"
SNOOZED_LINE = "\n\n⏰ <i>Snoozed until {time}</i>"
DURATION_MIN = "{n} min"
DURATION_HOURS = "{h} h"
DURATION_HOURS_MIN = "{h} h {m} min"
DURATION_DAYS = "{n} days"
DURATION_DAY = "1 day"

# --- Morning briefing ---
BRIEFING_TITLE = "☀️ <b>Good morning!</b> Today is {today}."
BRIEFING_IMPORTANT = "⭐ <b>Important</b>"
BRIEFING_TODAY = "📋 <b>Today</b>"
BRIEFING_ITEM = "• {time} — {subject}"

# --- Settings ---
SETTINGS = (
    "⚙️ <b>Settings</b>\n\n"
    "📅 Calendar: <b>{calendar}</b>\n"
    "🕒 Timezone: <b>{timezone}</b>\n"
    "🗓 Today: <b>{today}</b>\n"
    "☀️ Morning briefing: <b>{briefing}</b>\n"
    "🤖 Model: <b>{model}</b> <i>({profile} profile)</i>\n"
    "🎙 Voice: <b>{stt}</b>"
)
BRIEFING_ON = "on ({time})"
BRIEFING_OFF = "off"
BTN_BRIEFING_ON = "☀️ Turn morning briefing on"
BTN_BRIEFING_OFF = "☀️ Turn morning briefing off"
BRIEFING_CHANGED = "✅ Morning briefing {state}"
CALENDAR_NAMES = {"jalali": "Jalali (Shamsi)", "gregorian": "Gregorian"}
BTN_SWITCH_CALENDAR = "📅 Switch to {calendar}"
CALENDAR_CHANGED = "✅ Calendar set to {calendar}"
STT_ON = "on ({model})"
STT_OFF = "off"
