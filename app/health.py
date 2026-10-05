"""Liveness: a heartbeat for Docker's healthcheck, and a watchdog that restarts a stuck bot.

- While the event loop runs, `Watchdog.run` touches the heartbeat file every `BEAT_EVERY` s.
- `python -m app.health` (the healthcheck in docker-compose.yml) fails when that file is older
  than `STALE_AFTER` s, so `docker ps` shows the bot as unhealthy.
- A watchdog thread exits the process when the loop hasn't beaten for `STUCK_AFTER` s; Docker's
  restart policy then starts a fresh bot (a healthcheck alone only marks it unhealthy).

Kept free of heavy imports: the healthcheck runs this module every minute.
"""

import asyncio
import contextlib
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

HEARTBEAT = Path(os.environ.get("VIRA_HEARTBEAT", "/tmp/vira-heartbeat"))
BEAT_EVERY = 30
STALE_AFTER = 180
STUCK_AFTER = 300


class Watchdog:
    def __init__(
        self,
        path: Path = HEARTBEAT,
        stuck_after: float = STUCK_AFTER,
        exit_process: Callable[[int], object] = os._exit,
    ) -> None:
        self.path = path
        self.stuck_after = stuck_after
        self.exit_process = exit_process
        self.last = time.monotonic()

    def beat(self) -> None:
        self.last = time.monotonic()
        with contextlib.suppress(OSError):  # no writable /tmp: the watchdog thread still works
            self.path.write_text(f"{time.time():.0f}")

    async def run(self) -> None:
        """The heartbeat, as a task on the bot's event loop."""
        while True:
            self.beat()
            await asyncio.sleep(BEAT_EVERY)

    def stuck(self) -> bool:
        return time.monotonic() - self.last > self.stuck_after

    def watch_once(self) -> bool:
        """Exit the process when the loop is stuck. True if it did (or tried to)."""
        if not self.stuck():
            return False
        print(
            f"Vira: no heartbeat for {self.stuck_after:.0f} s, exiting so Docker restarts it",
            file=sys.stderr,
            flush=True,
        )
        self.exit_process(1)
        return True

    def start_thread(self) -> None:
        def watch() -> None:
            while True:
                time.sleep(BEAT_EVERY)
                self.watch_once()

        threading.Thread(target=watch, name="vira-watchdog", daemon=True).start()


def check(path: Path = HEARTBEAT, stale_after: float = STALE_AFTER) -> int:
    """0 (healthy) when the heartbeat is recent, 1 otherwise."""
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return 1
    return 0 if age < stale_after else 1


if __name__ == "__main__":
    sys.exit(check())
