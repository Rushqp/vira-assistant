"""Background jobs (APScheduler).

The database is the source of truth: a short interval job sends every alert that is due, so
nothing is lost across restarts (alerts missed while offline are sent late, marked as such).
- `jobs`  — what runs: due reminders, the morning briefing and the nightly report (at the times
            chosen in ⚙️ Settings)
- `setup` — when it runs
"""
