"""Prompts used while creating reminders."""

EXTRACT_SYSTEM_PROMPT = """\
You extract a reminder from a message written in Persian or English.
Today is {today} ({weekday}); the time is {time}. Dates may be Jalali (Persian calendar) in the
message, but always answer with a Gregorian date.

Return JSON with:
- subject: what to remind about, short, in the message's language, without date/time words
- date: YYYY-MM-DD, or null if no day is mentioned
- time: HH:MM in 24-hour format, or null if no time is mentioned
- important: true for health, money, travel, official, work-critical or family events
"""

IMPORTANCE_SYSTEM_PROMPT = """\
Decide whether a personal reminder is important: missing it would have real consequences.
The reminder may be in Persian or English. Return JSON: {"important": true|false}.

Important (true): doctor or dentist appointment, taking medicine, paying bills / rent / loan,
bank, flight or train, visa / passport / official papers, exam, job interview, work deadline,
important meeting, birthday or anniversary of family.
Not important (false): eating, drinking tea or coffee, reading, watching a show, shopping,
cleaning, cooking, calling a friend, exercise, routine chores, short breaks.

Examples:
"چای بخورم" → false · "کتاب بخونم" → false · "نوبت دکتر" → true · "قسط وام" → true
"water the plants" → false · "pay the electricity bill" → true
"""
