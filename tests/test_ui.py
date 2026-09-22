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
    with Progress(4, label="extract", stream=bar_buf) as bar:
        bar.tick(drafted=1, cards=2)
        bar.tick(drafted=2, cards=3)
        bar.finish(drafted=2, cards=3)
    text = bar_buf.getvalue()
    assert "extract" in text
    assert "2/4" in text or "4/4" in text
    assert "cards=3" in text


def test_unknown_total_prints_periodically(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    buf = io.StringIO()
    with Progress(0, label="employer REN21", stream=buf) as bar:
        for n in range(50):
            bar.tick(stored=n)
    text = buf.getvalue()
    assert "employer REN21" in text
    assert text.count("employer REN21") >= 2
    assert "50" in text


def test_log_scrolls_above_pinned_bar(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("FORCE_COLOR", "1")
    buf = io.StringIO()
    buf.isatty = lambda: True  # type: ignore[method-assign]
    monkeypatch.setattr("sys.stderr", buf)
    with Progress(2, label="ingest", stream=buf):
        from dossier.ui import note

        note("ingest chatgpt from /tmp/x")
        note("ingest linkedin from /tmp/y")
    out = buf.getvalue()
    assert "ingest chatgpt" in out
    assert "ingest linkedin" in out
    assert "ingest" in out
