"""Keeps the Docker setup consistent with the Python config."""

import re
from pathlib import Path

from app.config import PROFILE_DEFAULTS, Profile

ROOT = Path(__file__).resolve().parents[1]


def test_ollama_init_models_match_profile_defaults():
    script = (ROOT / "docker" / "ollama-init.sh").read_text(encoding="utf-8")
    pulled = dict(re.findall(r'^\s*(\w+)\) MODEL="([^"]+)"', script, re.MULTILINE))
    expected = {p.value: llm for p, (llm, _) in PROFILE_DEFAULTS.items() if p != Profile.REMOTE}
    assert pulled == expected


def test_env_example_lists_every_setting():
    from app.config import Settings

    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    keys = set(re.findall(r"^#?\s*([A-Z_]+)=", example, re.MULTILINE))
    assert {name.upper() for name in Settings.model_fields} <= keys
