"""Health and change notices for interchangeable backends: AI models and speech engines.

Backends are tried in order. One that fails is paused with a cooldown that grows with repeated
failures, and every change of the backend that answers is recorded as a `Notice`:
- switched: the first choice failed and another backend answered,
- restored: a better one answers again,
- down: none answered (reported once, until one answers again).

Each kind of work ("mode", e.g. agent turns vs plain chat) keeps its own "who answered last".
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from loguru import logger

from app.llm.client import LLMError

COOLDOWN_BASE = 30.0  # connection errors, timeouts, 5xx: 30 s, 60 s, 120 s … up to COOLDOWN_MAX
COOLDOWN_MAX = 600.0
COOLDOWN_RATE_LIMIT = 60.0  # quota / 429: 1 min, 2 min, 4 min … up to COOLDOWN_RATE_MAX
COOLDOWN_RATE_MAX = 1800.0
COOLDOWN_BROKEN = 3600.0  # invalid key or unknown model: won't fix itself quickly


class Backend(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def label(self) -> str: ...


@dataclass
class Notice:
    """A change of the answering backend, to tell the user about."""

    kind: Literal["switched", "restored", "down"]
    model: str = ""  # label of the backend that answers now (switched / restored)
    previous: str = ""  # label of the backend that stopped answering (switched)
    reason: str = ""  # error kind of `previous`
    retry_in: float | None = None  # seconds until `previous` is tried again
    reasons: dict[str, str] = field(default_factory=dict)  # down: label → error kind
    task: Literal["chat", "voice"] = "chat"  # what the backends do


@dataclass
class ModelStatus:
    client: Any
    ready: bool
    reason: str = ""
    retry_in: float = 0.0
    answering: bool = False


@dataclass
class _Health:
    failures: int = 0
    until: float = 0.0  # monotonic time when the backend may be tried again
    last_error: str = ""  # error kind of the last failure


@dataclass
class _Mode:
    last: str | None = None  # id of the backend that answered last
    down: bool = False  # a "down" notice was given and nothing answered since


class Failover:
    def __init__(
        self, clock: Callable[[], float] = time.monotonic, task: Literal["chat", "voice"] = "chat"
    ) -> None:
        self.clock = clock
        self.task = task
        self.notices: list[Notice] = []
        self._health: dict[str, _Health] = {}
        self._modes: dict[str, _Mode] = {}

    def reset(self) -> None:
        """Forget who answered (e.g. the user chose another model: not an outage)."""
        self._modes = {}

    def _mode(self, mode: str) -> _Mode:
        return self._modes.setdefault(mode, _Mode())

    def last(self, mode: str) -> str | None:
        return self._modes[mode].last if mode in self._modes else None

    # --- Health ---

    def health(self, backend: Backend) -> _Health:
        return self._health.setdefault(backend.id, _Health())

    def ready[T: Backend](self, backends: Sequence[T]) -> list[T]:
        now = self.clock()
        return [b for b in backends if self.health(b).until <= now]

    def failed(self, backend: Backend, error: LLMError) -> None:
        health = self.health(backend)
        health.failures += 1
        health.last_error = error.kind
        if error.kind == "rate_limited":
            backoff = COOLDOWN_RATE_LIMIT * 2 ** (health.failures - 1)
            pause = error.retry_after or min(backoff, COOLDOWN_RATE_MAX)
        elif error.kind in ("auth", "model_missing"):
            pause = COOLDOWN_BROKEN
        else:
            pause = min(COOLDOWN_BASE * 2 ** (health.failures - 1), COOLDOWN_MAX)
        health.until = self.clock() + pause
        logger.warning("{} failed ({}); paused for {:.0f}s", backend.label, error, pause)

    def status(self, backends: Sequence[Backend], answering: str | None) -> list[ModelStatus]:
        now = self.clock()
        result = []
        for backend in backends:
            health = self.health(backend)
            paused = health.until > now
            result.append(
                ModelStatus(
                    client=backend,
                    ready=not paused,
                    reason=health.last_error if paused else "",
                    retry_in=max(health.until - now, 0.0),
                    answering=backend.id == answering,
                )
            )
        return result

    # --- Notices ---

    def answered(
        self, backend: Backend, order: Sequence[Backend], mode: str = "default", report: bool = True
    ) -> None:
        """`backend` answered; `order` is the preference order for this kind of work."""
        self._health[backend.id] = _Health()
        state = self._mode(mode)
        previous, state.last = state.last, backend.id
        if not report:
            return
        if state.down:
            state.down = False
            self.notices.append(Notice("restored", model=backend.label, task=self.task))
            return
        if previous == backend.id:
            return
        rank = {b.id: i for i, b in enumerate(order)}
        if previous is None or previous not in rank:
            if order and backend.id != order[0].id:  # the first choice didn't answer
                self.notices.append(self._switched(order[0], backend))
            return
        if rank.get(backend.id, 0) > rank[previous]:
            stopped = next(b for b in order if b.id == previous)
            self.notices.append(self._switched(stopped, backend))
        else:
            self.notices.append(Notice("restored", model=backend.label, task=self.task))

    def _switched(self, stopped: Backend, now_answering: Backend) -> Notice:
        health = self.health(stopped)
        retry_in = health.until - self.clock()
        return Notice(
            "switched",
            model=now_answering.label,
            previous=stopped.label,
            reason=health.last_error or "unavailable",
            retry_in=retry_in if retry_in > 0 else None,
            task=self.task,
        )

    def nothing_answered(
        self, order: Sequence[Backend], mode: str = "default", report: bool = True
    ) -> None:
        state = self._mode(mode)
        if state.down or not report:
            return
        state.down, state.last = True, None
        reasons = {b.label: self.health(b).last_error or "paused" for b in order}
        self.notices.append(Notice("down", reasons=reasons, task=self.task))

    def drain(self) -> list[Notice]:
        """Notices since the last call, at most one per kind (the first)."""
        seen: dict[str, Notice] = {}
        for notice in self.notices:
            seen.setdefault(notice.kind, notice)
        self.notices = []
        return list(seen.values())
