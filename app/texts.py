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
BTN_SETTINGS = "⚙️ Settings"

INPUT_PLACEHOLDER = "Type or send a voice message…"

# --- Bot commands (shown in Telegram's command menu) ---
COMMANDS: dict[str, str] = {
    "start": "Start the assistant",
    "help": "How to use Vira",
    "menu": "Show the main menu",
    "new": "Start a new chat",
    "model": "Choose the AI model",
    "chats": "Continue a previous chat",
    "status": "Bot status: models, memory, last backup",
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
    "• Ask me anything in English or Persian: write it or send a voice message 🎙\n"
    "• I can calculate (<i>12*350000</i>) and tell you today's date (<i>what's the date?</i>).\n"
    "• 💬 <b>New Chat</b> starts a fresh conversation, 🗂 <b>Chats</b> continues an old one.\n"
    "• Reminders, just write them:\n"
    "  — <i>Doctor tomorrow at 2, remind me in the morning</i>\n"
    "  — <i>فردا ساعت ۸ یادم بنداز به مامان زنگ بزنم</i>\n"
    "  — <i>remind me every Saturday at 8am to go to the gym</i>\n"
    "• Expenses, several in one message:\n"
    "  — <i>۳ میلیون خرید خونه دادم، ۱۰ لیتر بنزین هم ۱۰۰ هزار</i>\n"
    "  — <i>Paid 3 million for groceries and 100k for fuel</i>\n"
    "• Reports: 📊 Today / 📅 Month, or write <i>گزارش این هفته</i> · <i>report last month</i>\n"
    "• Excel files, just ask:\n"
    "  — <i>اکسل هزینه‌های این ماه رو بده</i>\n"
    "  — <i>Excel of last month's food expenses, totals per week</i>\n"
    "  — <i>یه جدول برنامه ورزشی هفتگی به صورت اکسل بده</i>\n"
    "• Every night at 22:00: today's expenses and tomorrow's reminders (⚙️ Settings)\n"
    "• To-dos and notes, just say them:\n"
    "  — <i>فردا باید نون بخرم و قبض برق رو بدم</i>\n"
    "  — <i>یادداشت کن رمز وای‌فای مهمون 12345678 هست</i>\n\n"
    "<b>Commands</b>\n"
    "/menu — show the main menu\n"
    "/new — start a new chat\n"
    "/chats — continue a previous chat\n"
    "/model — choose the AI model\n"
    "/status — bot status (models, memory, last backup)\n"
    "/cancel — cancel the current action\n"
    "/backup — get a database backup\n"
    "/help — this message"
)

MENU = "📋 Main menu"
CANCELLED = "❌ Cancelled."
NOTHING_TO_CANCEL = "There's nothing to cancel."

UNKNOWN_COMMAND = "I don't know that command. See /help."
UNSUPPORTED_MESSAGE = "I can read text, voice messages and audio files."

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
    "rate_limited": "⚠️ The free AI quota is used up for now. Please try again in a minute.",
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
BRIEFING_TODOS = "✅ <b>To-dos</b>"
BRIEFING_TODO = "☐ {text}{origin}"

# --- Expenses ---
CURRENCY_LABELS = {"toman": "toman", "rial": "rial"}
EXPENSE_ASK_DESCRIBE = (
    "💰 What did you spend? You can write several at once.\n"
    "<i>e.g. ۳ میلیون خرید خونه، ۱۰ لیتر بنزین ۱۰۰ هزار · lunch 450k</i>"
)
EXPENSE_RETRY = "🤔 I couldn't find an amount in that. " + EXPENSE_ASK_DESCRIBE
EXPENSE_ASK_AMOUNT = "💰 How much was <b>{description}</b>?"
EXPENSE_AMOUNT_RETRY = "🤔 I couldn't find an amount. How much was <b>{description}</b>?"
EXPENSE_ASK_SCALE = "💰 <b>{description}</b>: {raw} thousand or {raw} million?"
EXPENSE_CARD_TITLE = "💰 <b>New expense</b>"
EXPENSE_CARD_TITLE_MANY = "💰 <b>New expenses</b> ({count})"
EXPENSE_CARD_ITEM = "{n}. {emoji} {description}{quantity} — <b>{amount}</b>"
EXPENSE_CARD_DATE = "🗓 {date}"
EXPENSE_CARD_TOTAL = "Σ Total: <b>{amount}</b>"
EXPENSE_NO_DESCRIPTION = "(no description)"
EXPENSE_SAVED = "✅ <b>Saved</b>\n\n{card}"
EXPENSE_CANCELLED = "❌ Expense cancelled."
EXPENSE_UNDONE = "↩️ Undone: the expenses were deleted."
EXPENSE_UNDO_EXPIRED = "This can no longer be undone. Delete it from 📊 Today Report."
EXPENSE_EXPIRED = "This expense draft has expired. Please send it again."
EXPENSE_EDIT_PROMPT = "✏️ Send the expense again with your changes.\n<i>Current: {raw}</i>"
EXPENSE_PICK_ITEM = "🏷 Which item?"
EXPENSE_PICK_CATEGORY = "🏷 Category for <b>{description}</b>:"
BTN_SCALE_K = "{amount}"
BTN_SCALE_M = "{amount}"
BTN_CATEGORY = "🏷 Category"
BTN_UNDO = "↩️ Undo"

# --- Reports ---
REPORT_DAY_TITLE = "📊 <b>{date}</b>"
REPORT_WEEK_TITLE = "📊 <b>Week</b> · {start} – {end}"
REPORT_MONTH_TITLE = "📅 <b>{month} {year}</b>"
REPORT_EMPTY = "No expenses recorded."
REPORT_TOTAL = "Total: <b>{amount}</b>"
REPORT_VS_PREVIOUS = " ({arrow} {percent}% vs {previous})"
REPORT_VS_ZERO = " (nothing in the previous period)"
REPORT_AVERAGE = "Daily average: {amount}"
REPORT_CATEGORY = "{emoji} {name} {bar} {percent}% · {amount}"
REPORT_LARGEST = "🔝 Largest: {amount} — {description}"  # amount first: Persian text would split it
REPORT_ITEMS = "<b>Expenses</b>"
REPORT_ITEM = "{n}. {emoji} {description}{quantity} — {amount}"
REPORT_MORE = "… and {count} more"
REPORT_PREVIOUS = {"day": "the day before", "week": "the week before", "month": "last month"}
REPORT_DELETE_CONFIRM = "🗑 Delete <b>{description}</b> ({amount})?"
REPORT_DELETED = "🗑 Expense deleted."
REPORT_NOT_FOUND = "This expense no longer exists."
BTN_REPORT_DAY = "📊 Day"
BTN_REPORT_WEEK = "🗓 Week"
BTN_REPORT_MONTH = "📅 Month"
BTN_DELETE_ITEM = "🗑 {n}"

# --- Categories (Settings) ---
CATEGORIES_TITLE = "🏷 <b>Categories</b>\nTap one to delete it. Its expenses move to Other."
CATEGORY_ASK_NEW = "➕ Send the new category as <i>emoji name</i>, e.g. <i>🐶 Pets</i>"
CATEGORY_ADDED = "✅ Category {emoji} {name} added."
CATEGORY_EXISTS = "A category named {name} already exists."
CATEGORY_INVALID = "Please send a short name (up to 32 characters), e.g. <i>🐶 Pets</i>"
CATEGORY_DELETE_CONFIRM = "🗑 Delete {emoji} <b>{name}</b>? Its expenses move to Other."
CATEGORY_DELETED = "🗑 Category deleted."
CATEGORY_PROTECTED = "Other can't be deleted."
BTN_CATEGORIES = "🏷 Categories"
BTN_ADD_CATEGORY = "➕ Add category"

# --- Agent results ---
AGENT_EXPENSES_SAVED = "✅ <b>Saved</b>"
AGENT_EXPENSES_DELETED = "🗑 <b>Deleted</b>"
AGENT_EXPENSE_UPDATED = "✏️ <b>Updated</b>"
AGENT_REMINDER_SAVED = "⏰ <b>Reminder saved</b>\n\n{card}"
AGENT_REMINDER_UPDATED = "✏️ <b>Reminder updated</b>\n\n{card}"
AGENT_REMINDERS_CANCELLED = "🗑 <b>Cancelled</b>"
AGENT_LIST_ITEM = "• {text}"
AGENT_SETTINGS_CHANGED = "⚙️ <b>Settings changed</b>"
AGENT_SETTING_CALENDAR = "📅 Calendar: {value}"
AGENT_SETTING_BRIEFING = "☀️ Morning briefing: {value}"
AGENT_SETTING_BRIEFING_TIME = "☀️ Morning briefing at {value}"
AGENT_SETTING_NIGHTLY = "🌙 Nightly report: {value}"
AGENT_SETTING_NIGHTLY_TIME = "🌙 Nightly report at {value}"
AGENT_ASK_ALERTS = "\n\n🔔 <i>Notifies at the start. Want an earlier reminder too?</i>"
AGENT_UNDONE_LINE = "\n\n↩️ <i>Undone</i>"
AGENT_ALREADY_UNDONE = "This was already undone."
AGENT_EDIT_PROMPT = (
    "✏️ What should I change?\n<i>e.g. «مبلغش ۲۵۰ هزار بود» · «بذارش برای ساعت ۵» · "
    "change it to Friday</i>"
)
AGENT_EDIT_HINT = "[The user is correcting this earlier action: {summary}]"
AGENT_HINT_REMINDER = "[The user tapped ⏰ New Reminder: this message describes a reminder]"
AGENT_HINT_EXPENSE = "[The user tapped 💰 Add Expense: this message describes expenses]"
AGENT_THINKING = "💭"
BTN_ALERT_ADD = "＋ {label}"

# --- AI model (⚙️ Settings → 🤖 AI model, /model) ---
AI_TITLE = "🤖 <b>AI model</b>"
AI_MODE_AUTO = "Mode: <b>Auto</b>: the best available model answers"
AI_MODE_PREFERRED = "Mode: <b>{model}</b> first, the others are backups"
AI_ANSWERING = "Answering now: <b>{model}</b>"
AI_ORDER = "<b>Order</b>"
AI_STATUS_READY = "{n}. ✅ {model}"
AI_STATUS_PAUSED = "{n}. ⏸ {model} — {reason}, retry at {time}"
AI_STATUS_CHAT_ONLY = " <i>(chat only)</i>"
AI_NO_KEY = "<i>More free models: add {keys} in .env</i>"
AI_NONE = (
    "🤖 No AI model is configured, so Vira works in basic (rule-based) mode.\n"
    "Add a free key (e.g. GEMINI_API_KEY) in .env — see the README."
)
AI_HELP = (
    "<i>Pick a model to use it first. If it isn't available, the next one answers and you "
    "get a notice.</i>"
)
AI_CHOSEN = "✅ {model} answers first now"
AI_AUTO_CHOSEN = "✅ Auto: the best available model answers"
AI_PICK_FAILED = "This model can't be used (missing key?)."
AI_MENU_EXPIRED = "This menu is out of date; here is a fresh one."
BTN_AI_MODEL = "🤖 AI model"
BTN_AI_AUTO = "✨ Auto"
AI_REASONS = {
    "rate_limited": "free quota used up",
    "unreachable": "not reachable",
    "model_missing": "model not found",
    "auth": "API key rejected",
    "failed": "error",
    "paused": "paused",
    "unavailable": "unavailable",
}
AI_SWITCHED = "🔁 <b>{previous}</b> isn't available ({reason}), so <b>{model}</b> answered."
AI_SWITCHED_RETRY = " I'll try it again at {time}."
AI_RESTORED = "✅ <b>{model}</b> is available again and answering."
AI_DOWN = (
    "⚠️ No AI model can handle requests right now ({reasons}). Vira works in basic mode "
    "until one is back."
)

# --- Nightly report (scheduler) ---
NIGHTLY_TITLE = "🌙 <b>Your day</b> · {today}"
NIGHTLY_SPENT = "💰 Spent today: <b>{amount}</b> · {count}"
NIGHTLY_NOTHING = "💰 No expenses recorded today. Spent anything? Just tell me what you bought."
NIGHTLY_MONTH = "📅 This month so far: <b>{amount}</b> · daily average {average}"
NIGHTLY_TOMORROW = "⏰ <b>Tomorrow</b>"
NIGHTLY_TOMORROW_EMPTY = "⏰ Nothing scheduled for tomorrow."
NIGHTLY_ITEM = "• {star}{time} — {subject}"
NIGHTLY_TODOS_DONE = "✅ All {total} to-dos done 🎉"
NIGHTLY_TODOS_OPEN = (
    "✅ To-dos: {done} of {total} done · still open: {items} (they stay on the list)"
)

# --- To-dos (✅ Today To-Dos, agent cards) ---
TODOS_TITLE = "✅ <b>To-dos</b> · {day}"
TODOS_CARRIED = "⏳ <b>From earlier days</b>"
TODOS_PLANNED = "📋 <b>Planned</b>"
TODO_OPEN = "☐ {text}{origin}"
TODO_DONE = "☑ <s>{text}</s>{origin}"
TODO_ORIGIN = " <i>({day})</i>"
TODOS_PROGRESS = "<i>{done} of {total} done</i>"
TODOS_EMPTY = "Nothing on the list. Just tell me what you need to do, e.g. «فردا باید نون بخرم»."
TODOS_ADD_PROMPT = "✍️ Send the tasks for {day}: one per line, or in a sentence."
BTN_TODO_ADD = "➕ Add"
BTN_PREV_DAY = "◀️"
BTN_NEXT_DAY = "▶️"
BTN_TODAY = "📅 Today"
TODO_NOT_FOUND = "This to-do no longer exists."
AGENT_HINT_TODO = "[The user tapped ➕ Add on the to-do list of {day}: this message lists tasks]"
AGENT_TODOS_ADDED = "✅ <b>Added to the to-dos</b> · {day}"
AGENT_TODOS_UPDATED = "✅ <b>To-dos updated</b>"
AGENT_TODOS_DELETED = "🗑 <b>To-dos deleted</b>"

# --- Notes (📝 Notes, agent cards) ---
NOTES_TITLE = "📝 <b>Notes</b> ({count})"
NOTES_FOUND = "🔎 <b>Notes</b> · «{query}»"
NOTES_EMPTY = "No notes yet. Say «یادداشت کن …» or send a voice note."
NOTES_ITEM = "{n}. {pin}<b>{title}</b>{tags} · <i>{date}</i>"
NOTES_SEARCH_HINT = "<i>To search, just ask, e.g. «یادداشت‌های مربوط به ماشین»</i>"
NOTE_PIN = "📌 "
NOTE_CARD = "📝 <b>{title}</b>{pin}\n{meta}\n\n{body}"
NOTE_META = "{tags}<i>{date}</i>"
NOTE_SUMMARY = "<b>Summary:</b> {summary}\n\n"
NOTE_VOICE = " · 🎙"
NOTE_MORE = "\n\n<i>… ({count} more characters)</i>"
BTN_NOTE_PIN = "📌 Pin"
BTN_NOTE_UNPIN = "📌 Unpin"
NOTE_PINNED = "📌 Pinned"
NOTE_UNPINNED = "Unpinned"
NOTE_DELETE_CONFIRM = "🗑 Delete the note <b>{title}</b>?"
NOTE_DELETED = "🗑 Note deleted."
NOTE_NOT_FOUND = "This note no longer exists."
NOTE_EDIT_PROMPT = (
    "✏️ What should change in this note? E.g. «شیر رو هم اضافه کن» or «اسمش رو بکن …»."
)
AGENT_EDIT_NOTE_HINT = (
    "[The user wants to change note #{id} «{title}»: use update_note with id {id}]"
)
AGENT_NOTE_SAVED = "📝 <b>Note saved</b>"
AGENT_NOTE_UPDATED = "📝 <b>Note updated</b>"
AGENT_NOTES_DELETED = "🗑 <b>Notes deleted</b>"

# --- Backup (/backup, ⚙️ Settings → 💾 Backup) ---
BACKUP_CAPTION = (
    "💾 <b>Backup</b> · {date}\n{counts}\n<i>To restore it (e.g. on a new server), send this file "
    "back to me.</i>"
)
BACKUP_BEFORE_RESTORE = "💾 Your data before the restore, just in case."
BACKUP_COUNTS = "{expenses} expenses · {reminders} reminders · {todos} to-dos · {notes} notes"
BACKUP_TITLE = "💾 <b>Backup</b>"
BACKUP_ABOUT = (
    "A copy of all your data as one file. To restore it, e.g. on a new server, send the file to me."
)
BACKUP_WEEKLY_ON = "Weekly copy: <b>on</b> (Fridays at {time})"
BACKUP_WEEKLY_OFF = "Weekly copy: <b>off</b>"
BTN_BACKUP = "💾 Backup"
BTN_BACKUP_NOW = "📤 Send a backup now"
BTN_BACKUP_WEEKLY_ON = "✅ Turn the weekly copy on"
BTN_BACKUP_WEEKLY_OFF = "⏸ Turn the weekly copy off"
BACKUP_WEEKLY_CHANGED = "✅ Weekly copy: {state}"
BACKUP_FAILED = "💾 The backup could not be made. Please try again."
RESTORE_CHECK = (
    "💾 <b>Restore this backup?</b>\nMade on {date}\n{counts}\n\n⚠️ It replaces all current data. "
    "A copy of the current data is sent to you first."
)
BTN_RESTORE = "✅ Restore"
RESTORE_INVALID = "This file isn't a Vira backup ({reason})."
RESTORE_NEWER = "This backup comes from a newer version of Vira: update the bot first."
RESTORE_TOO_BIG = "This file is larger than 20 MB, which bots can't download."
RESTORE_DONE = "✅ Restored. {counts}"
RESTORE_CANCELLED = "Restore cancelled; nothing changed."
RESTORE_EXPIRED = "This restore request is out of date. Please send the file again."

# --- Excel files (English; dates in the selected calendar) ---
GREGORIAN_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December",
)  # fmt: skip
XLSX_EXPENSES_TITLE = "Expenses"
XLSX_REMINDERS_TITLE = "Reminders"
XLSX_SHEET_EXPENSES = "Expenses"
XLSX_SHEET_CATEGORIES = "By category"
XLSX_SHEET_DAYS = "By day"
XLSX_SHEET_WEEKS = "By week"
XLSX_SHEET_MONTHS = "By month"
XLSX_SHEET_REMINDERS = "Reminders"
XLSX_SHEET_DEFAULT = "Sheet"
XLSX_TOTAL = "Total"
XLSX_YES = "Yes"
XLSX_NO = "No"
XLSX_ALL = "All"
XLSX_UPCOMING = "Upcoming"
XLSX_FROM = "From {date}"
XLSX_EXPENSE_HEADERS = {
    "date": "Date",
    "weekday": "Weekday",
    "time": "Time",
    "description": "Description",
    "category": "Category",
    "quantity": "Quantity",
    "amount": "Amount ({currency})",
}
XLSX_CATEGORY_HEADERS = ("Category", "Amount ({currency})", "Share", "Count")
XLSX_DAY_HEADERS = ("Date", "Weekday", "Amount ({currency})", "Count")
XLSX_WEEK_HEADERS = ("Week", "Amount ({currency})", "Count")
XLSX_MONTH_HEADERS = ("Month", "Amount ({currency})", "Count")
XLSX_REMINDER_HEADERS = (
    "Date", "Weekday", "Time", "Subject", "Repeat", "Alerts", "Important", "Status",
)  # fmt: skip
XLSX_STATUS = {"active": "Active", "done": "Done", "cancelled": "Cancelled"}
EXPORT_CAPTION_EXPENSES = "📊 <b>{title}</b>\n{count} · total {total}"
EXPORT_CAPTION_REMINDERS = "⏰ <b>{title}</b>\n{count} reminders"
EXPORT_CAPTION_TABLE = "📄 <b>{title}</b>"
EXPORT_EMPTY = "No expenses in that period, so there is no file to send."
EXPENSE_COUNT = {"one": "1 expense", "many": "{count} expenses"}

# --- /status ---
STATUS_TITLE = "📊 <b>Vira {version}</b> · running for {uptime}"
STATUS_AI = "🤖 AI: <b>{model}</b>{paused}"
STATUS_AI_PAUSED = " · {count} paused"
STATUS_AI_NONE = "🤖 AI: none (basic mode)"
STATUS_VOICE = "🎙 Voice: {engines}"
STATUS_MEMORY = "💾 Memory: <b>{memory}</b>{whisper}"
STATUS_WHISPER = " · local Whisper loaded"
STATUS_STORAGE = "🗄 Database: <b>{db}</b> · free disk: <b>{free}</b>"
STATUS_DATA = "📦 {expenses} expenses · {reminders} reminders · {todos} open to-dos · {notes} notes"
STATUS_BACKUP = "💾 Last backup: {when}"
STATUS_BACKUP_NEVER = "never (send /backup)"
STATUS_ERRORS = "⚠️ Errors since the start: {count}"
STATUS_UNKNOWN = "—"

# --- Unexpected errors (app/bot/errors.py) ---
ERROR_REPORT = (
    "⚠️ <b>Something went wrong</b> ({where}):\n<code>{error}</code>\n"
    "<i>The details are in the log. Please try again; if it keeps happening, report it.</i>"
)
ERROR_ALERT = "⚠️ Something went wrong; the details were sent to the chat."

# --- Settings ---
SETTINGS = (
    "⚙️ <b>Settings</b>\n\n"
    "📅 Calendar: <b>{calendar}</b>\n"
    "🕒 Timezone: <b>{timezone}</b>\n"
    "🗓 Today: <b>{today}</b>\n"
    "☀️ Morning briefing: <b>{briefing}</b>\n"
    "🌙 Nightly report: <b>{nightly}</b>\n"
    "🤖 AI: <b>{model}</b> <i>({profile} profile)</i>\n"
    "🎙 Voice: <b>{stt}</b>"
)
BRIEFING_ON = "on ({time})"
BRIEFING_OFF = "off"
BTN_BRIEFING_SETTINGS = "☀️ Morning briefing"
BTN_NIGHTLY_SETTINGS = "🌙 Nightly report"

# --- ⚙️ Settings → ☀️ Morning briefing / 🌙 Nightly report ---
DIGEST_NAMES = {"briefing": "Morning briefing", "nightly": "Nightly report"}
DIGEST_TITLES = {"briefing": "☀️ <b>Morning briefing</b>", "nightly": "🌙 <b>Nightly report</b>"}
DIGEST_ABOUT = {
    "briefing": "Today's reminders, important ones first (skipped on days without reminders).",
    "nightly": "Today's expenses, this month so far and tomorrow's reminders.",
}
DIGEST_STATE_ON = "Every day at <b>{time}</b>"
DIGEST_STATE_OFF = "<b>Off</b> (time: {time})"
DIGEST_HELP = "<i>Pick a time, or tell me in the chat, e.g. «گزارش شبانه رو ساعت ۱۱ بفرست».</i>"
BTN_DIGEST_ON = "✅ Turn on"
BTN_DIGEST_OFF = "⏸ Turn off"
BTN_DIGEST_OTHER = "🕐 Other time"
DIGEST_ASK_TIME = "🕐 Send the time, e.g. <i>21:30</i> or <i>۹ شب</i>."
DIGEST_TIME_RETRY = "I couldn't read that time. Send it like <i>21:30</i>, or /cancel."
DIGEST_NIGHTLY_RANGE = (
    "The nightly report sums up the day, so its time must be between 12:00 and 23:59."
)
DIGEST_CHANGED = "✅ {name}: {state}"
CALENDAR_NAMES = {"jalali": "Jalali (Shamsi)", "gregorian": "Gregorian"}
BTN_SWITCH_CALENDAR = "📅 Switch to {calendar}"
CALENDAR_CHANGED = "✅ Calendar set to {calendar}"
STT_ON = "on ({model})"
STT_OFF = "off"
STT_NO_ENGINE = "no engine: add GROQ_API_KEY"

# --- Voice messages (app/bot/middlewares/voice.py) ---
VOICE_HEARD = "🎙 «{text}»"
VOICE_OFF = "🎙 Voice messages are turned off (STT_ENABLED in .env). Please type your message."
VOICE_NO_ENGINE = (
    "🎙 I can't understand voice messages yet: add a free GROQ_API_KEY (or GEMINI_API_KEY) in "
    ".env. Please type your message for now."
)
VOICE_TOO_LONG = "🎙 This recording is about {minutes} min long; I can transcribe up to {limit} min."
VOICE_TOO_BIG = "🎙 This file is larger than 20 MB, which bots can't download."
VOICE_FAILED = "🎙 I couldn't transcribe this voice message. Please try again, or type it."
VOICE_EMPTY = "🎙 I couldn't hear any words in it."
VOICE_SWITCHED = (
    "🔁 <b>{previous}</b> isn't available ({reason}), so <b>{model}</b> transcribed your voice "
    "message."
)
VOICE_RESTORED = "✅ <b>{model}</b> is transcribing voice messages again."
VOICE_DOWN = (
    "⚠️ Voice messages can't be transcribed right now ({reasons}). Please type, or try again later."
)
