"""One-at-a-time background jobs with an in-memory event log for SSE."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dossier import ui as ui_mod

log = logging.getLogger("dossier.jobs")


class LockerBusy(RuntimeError):
    """Raised when a second job tries to start while one is running."""


class JobCancelled(RuntimeError):
    """Cooperative cancel: a progress callback saw the cancel event."""


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
    seed: dict[str, Any] = field(default_factory=dict)
    events: list[JobEvent] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    _cond: threading.Condition = field(default_factory=threading.Condition, repr=False)

    def push(self, kind: str, **payload: Any) -> JobEvent:
        with self._cond:
            ev = JobEvent(index=len(self.events), kind=kind, payload=payload)
            self.events.append(ev)
            self._cond.notify_all()
            self._persist(ev)
            return ev

    def _persist(self, ev: JobEvent) -> None:
        raw = os.environ.get("DOSSIER_DATA", "").strip()
        if not raw:
            return
        folder = Path(raw) / "jobs"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{self.id}.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(ev.as_dict(), ensure_ascii=False) + "\n")
        except OSError:
            return

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

    def start(
        self,
        kind: str,
        fn: Callable[[Job], Any],
        *,
        seed: dict[str, Any] | None = None,
    ) -> Job:
        with self._lock:
            if self._job is not None and self._job.status in {"queued", "running"}:
                raise LockerBusy("locker busy")
            job = Job(id=uuid.uuid4().hex[:12], kind=kind, seed=dict(seed or {}))
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

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None or job.status not in {"queued", "running"}:
            return False
        job.cancel.set()
        job.push("status", status="cancelling")
        return True

    def _run(self, job: Job, fn: Callable[[Job], Any]) -> None:
        job.status = "running"
        job.push("status", status="running")

        def sink(event: dict[str, Any]) -> None:
            if job.cancel.is_set():
                raise JobCancelled("cancelled")
            kind = str(event.pop("kind", "progress"))
            job.push(kind, **event)

        token = ui_mod.set_progress_sink(sink)
        try:
            if job.cancel.is_set():
                raise JobCancelled("cancelled")
            job.result = fn(job)
            if job.cancel.is_set():
                raise JobCancelled("cancelled")
            job.status = "done"
            job.push("status", status="done")
        except JobCancelled:
            job.status = "error"
            job.error = "cancelled"
            job.push("status", status="error", error="cancelled")
        except Exception as extra:
            job.status = "error"
            job.error = _scrub(str(extra))
            log.exception("job %s failed", job.kind)
            job.push("status", status="error", error=job.error)
        finally:
            ui_mod.set_progress_sink(token)
            job.finished_at = time.time()
            with self._lock:
                self._history = ([job] + self._history)[:8]


def _scrub(message: str) -> str:
    """Drop home-directory prefixes from errors shown in the UI."""
    home = str(Path.home())
    return message.replace(home, "~")


# Process-wide runner for the workbench.
RUNNER = JobRunner()
