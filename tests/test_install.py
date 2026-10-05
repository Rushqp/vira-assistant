"""install.sh, in dry-run mode (no Docker): the questions end up in a correct .env.

Runs on Linux only (CI); the installer is for Linux servers.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or not shutil.which("git"), reason="the installer is for Linux"
)


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def source(tmp_path) -> Path:
    """A small repository with the project's .env.example, to install from."""
    repo = tmp_path / "source"
    repo.mkdir()
    shutil.copy(ROOT / ".env.example", repo / ".env.example")
    git("init", "-q", "-b", "main", cwd=repo)
    git("-c", "user.name=t", "-c", "user.email=t@t", "add", ".", cwd=repo)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x", cwd=repo)
    return repo


def install(source: Path, target: Path, **answers: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "VIRA_REPO": str(source),
        "VIRA_DIR": str(target),
        "VIRA_DRY_RUN": "1",
        **answers,
    }
    return subprocess.run(
        ["bash", str(ROOT / "install.sh")],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )


def read_env(path: Path) -> dict[str, str]:
    pairs = (line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
    return {k: v for k, v in pairs if not k.startswith("#")}


def test_installer_writes_the_settings(source, tmp_path):
    target = tmp_path / "vira"
    result = install(
        source,
        target,
        BOT_TOKEN="123456:AbC-dEf",
        OWNER_ID="42",
        GROQ_API_KEY="q",
        PROFILE="standard",
        API_PROXY="socks5://user:p&ss|w0rd@host:1080",
    )
    assert result.returncode == 0, result.stderr
    env = read_env(target / ".env")
    assert env["BOT_TOKEN"] == "123456:AbC-dEf" and env["OWNER_ID"] == "42"
    assert env["PROFILE"] == "standard" and env["COMPOSE_PROFILES"] == "ollama"
    assert env["API_PROXY"] == "socks5://user:p&ss|w0rd@host:1080"
    assert oct((target / ".env").stat().st_mode)[-3:] == "600"

    again = install(source, target)  # an update keeps the settings
    assert again.returncode == 0 and "Keeping your existing settings" in again.stdout


def test_installer_checks_the_answers(source, tmp_path):
    bad_id = install(source, tmp_path / "a", BOT_TOKEN="1:x", OWNER_ID="me", PROFILE="lite")
    assert bad_id.returncode != 0 and "must be a number" in bad_id.stderr
    no_key = install(source, tmp_path / "b", BOT_TOKEN="1:x", OWNER_ID="1", PROFILE="remote")
    assert no_key.returncode != 0 and "needs at least one API key" in no_key.stderr
