"""Job runner and progress sink."""

from __future__ import annotations

import time

import pytest

from dossier import ui
from dossier.jobs import LockerBusy, JobRunner


def test_progress_sink_receives_stage_and_bar(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    events: list[dict] = []
    previous = ui.set_progress_sink(lambda ev: events.append(dict(ev)))
    try:
        ui.stage("extract", "llm=off · 2 to draft")
        with ui.Progress(2, label="extract") as bar:
            bar.tick(drafted=1)
            bar.finish(drafted=2)
    finally:
        ui.set_progress_sink(previous)
    kinds = [ev["kind"] for ev in events]
    assert "stage" in kinds
    assert "progress" in kinds
    assert any(ev.get("title") == "extract" for ev in events)


def test_job_runner_one_at_a_time() -> None:
    runner = JobRunner()
    gate = {"go": False}

    def slow(job):  # noqa: ANN001
        while not gate["go"]:
            time.sleep(0.01)
            job.push("note", text="waiting")
        return {"ok": True}

    first = runner.start("demo", slow)
    with pytest.raises(LockerBusy):
        runner.start("demo2", lambda job: None)
    gate["go"] = True
    deadline = time.time() + 2
    while first.status not in {"done", "error"} and time.time() < deadline:
        time.sleep(0.02)
    assert first.status == "done"
    assert first.result == {"ok": True}
    events = first.events_after(0)
    assert any(ev.kind == "note" for ev in events)
    assert any(ev.kind == "status" and ev.payload.get("status") == "done" for ev in events)
