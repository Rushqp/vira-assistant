# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-03

### Added
- Ollama service in Docker Compose plus an `ollama-init` service that pulls the model for the selected
  `PROFILE` on first start. The Ollama port is never exposed.
- `COMPOSE_PROFILES=ollama` switch: leave it empty with `PROFILE=remote` to use any OpenAI-compatible API
- OpenAI-compatible LLM client (`app/llm/client.py`) with clear errors for unreachable / missing models
- 💬 Chat: free text is answered by the LLM in the user's language (Persian or English), streamed
  into the message as it is generated
- Short-term memory: the last `CHAT_MEMORY` messages (default 10) are sent as context
- 💬 New Chat button and `/new` start a fresh conversation
- Built-in tools without the LLM: calculator (Persian digits, `×`, `÷`, `^`) and "what's today's
  date?" in both calendars
- Persian month and weekday names; Persian replies use Persian digits
- New settings: `LLM_TIMEOUT`, `CHAT_MEMORY`, `OLLAMA_KEEP_ALIVE`
- Database tables `chat_sessions` and `chat_history` (migration `0002`)
- Unknown commands, voice messages and media get a clear reply

### Changed
- `PROFILE=remote` now requires `LLM_MODEL`
- CI actions updated to their current major versions

## [0.1.0] - 2026-10-03

### Added
- Project skeleton (Python 3.12, aiogram 3) with a readable layout: `bot` / `services` / `db` / `utils`
- Configuration via `.env` (pydantic-settings) with hardware profiles `lite` / `standard` / `full` / `remote`
- `/start`, `/help`, `/menu`, `/cancel` commands and the English main menu (reply keyboard)
- Owner-only middleware: updates from anyone other than `OWNER_ID` are ignored
- SQLite + SQLAlchemy 2 (async) with Alembic migrations applied automatically on startup
- Settings screen with a Jalali / Gregorian calendar toggle (persisted) and read-only system info
- "Coming in vX.Y" placeholders for features planned in later versions
- Docker image (non-root) and Docker Compose setup
- GitHub Actions CI: ruff lint + format check, pytest, Docker image build
- Bilingual (English / Persian) README

[0.2.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.2.0
[0.1.0]: https://github.com/Rushqp/vira-assistant/releases/tag/v0.1.0
