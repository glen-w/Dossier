"""One-at-a-time background jobs with an in-memory event log for SSE."""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from dossier import ui as ui_mod


class LockerBusy(RuntimeError):
    """Raised when a second job tries to start while one is running."""


@dataclass
class JobEvent:
    index: int
    kind: str
    payload: dict[str, Any]
    ts: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "ts": self.ts,
            **self.payload,
        }


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"  # queued | running | done | error
    error: str = ""
    result: Any = None
    events: list[JobEvent] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    _cond: threading.Condition = field(default_factory=threading.Condition, repr=False)

    def push(self, kind: str, **payload: Any) -> JobEvent:
        with self._cond:
            ev = JobEvent(index=len(self.events), kind=kind, payload=payload)
            self.events.append(ev)
            self._cond.notify_all()
            return ev

    def events_after(self, index: int) -> list[JobEvent]:
        with self._cond:
            return list(self.events[max(0, index) :])

    def wait_events(self, after: int, timeout: float = 1.0) -> list[JobEvent]:
        with self._cond:
            if after < len(self.events):
                return list(self.events[after:])
            if self.status in {"done", "error"}:
                return []
            self._cond.wait(timeout=timeout)
            return list(self.events[after:])

    def snapshot(self) -> dict[str, Any]:
        with self._cond:
            return {
                "id": self.id,
                "kind": self.kind,
                "status": self.status,
                "error": self.error,
                "created_at": self.created_at,
                "finished_at": self.finished_at,
                "event_count": len(self.events),
                "latest": self.events[-1].as_dict() if self.events else None,
            }


class JobRunner:
    """Single-slot job runner. SQLite has one writer; keep one job at a time."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._job: Job | None = None
        self._thread: threading.Thread | None = None
        self._history: list[Job] = []

    @property
    def current(self) -> Job | None:
        with self._lock:
            return self._job

    def busy(self) -> bool:
        job = self.current
        return job is not None and job.status in {"queued", "running"}

    def start(self, kind: str, fn: Callable[[Job], Any]) -> Job:
        with self._lock:
            if self._job is not None and self._job.status in {"queued", "running"}:
                raise LockerBusy("locker busy")
            job = Job(id=uuid.uuid4().hex[:12], kind=kind)
            self._job = job
            self._thread = threading.Thread(
                target=self._run,
                args=(job, fn),
                name=f"dossier-job-{kind}",
                daemon=True,
            )
            self._thread.start()
            return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            if self._job is not None and self._job.id == job_id:
                return self._job
            for item in self._history:
                if item.id == job_id:
                    return item
        return None

    def _run(self, job: Job, fn: Callable[[Job], Any]) -> None:
        job.status = "running"
        job.push("status", status="running")

        def sink(event: dict[str, Any]) -> None:
            kind = str(event.pop("kind", "progress"))
            job.push(kind, **event)

        token = ui_mod.set_progress_sink(sink)
        try:
            job.result = fn(job)
            job.status = "done"
            job.push("status", status="done")
        except Exception as exc:  # noqa: BLE001 — surface to the workbench
            job.status = "error"
            job.error = str(exc)
            job.push("status", status="error", error=str(exc), detail=traceback.format_exc())
        finally:
            ui_mod.set_progress_sink(token)
            job.finished_at = time.time()
            with self._lock:
                self._history = ([job] + self._history)[:8]


# Process-wide runner for the workbench.
RUNNER = JobRunner()
