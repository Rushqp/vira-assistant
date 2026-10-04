"""Voice → text (v0.6). Voice messages and audio files are transcribed before routing
(`app/bot/middlewares/voice.py`), so they go through the same handlers as typed text.

- `engines` — Groq Whisper and Gemini (free APIs) and faster-whisper on the CPU
- `chain`   — the engines in order (`STT_PROVIDERS`) with failover and notices
"""
