"""Progress UI helpers."""

from __future__ import annotations

import io

from dossier.ui import Progress, colour_enabled, paint, stage, trunc


def test_trunc() -> None:
    assert trunc("short") == "short"
    assert trunc("abcdefghij", 5) == "abcd…"


def test_paint_respects_no_color(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    assert paint("hi", "\033[36m") == "hi"
    assert colour_enabled() is False


def test_stage_and_progress_plain(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    buf = io.StringIO()
    stage("extract", "llm=off · 3 to draft", stream=buf)
    assert "extract" in buf.getvalue()
    assert "3 to draft" in buf.getvalue()

    bar_buf = io.StringIO()
    bar = Progress(4, label="extract", stream=bar_buf)
    bar.tick(drafted=1, cards=2)
    bar.tick(drafted=2, cards=3)
    bar.finish(drafted=2, cards=3)
    text = bar_buf.getvalue()
    assert "extract" in text
    assert "2/4" in text or "4/4" in text
    assert "cards=3" in text
