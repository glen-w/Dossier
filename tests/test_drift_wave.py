"""Provenance, drift, restore, and repeated posting gaps. Synthetic fixtures only."""

from __future__ import annotations

from pathlib import Path

from dossier.cards import STATUS_APPROVED, ClaimCard
from dossier.cli import main
from dossier.show import defend_cards
from dossier.store import Corpus, Record, text_hash

SPAN = "Quinn wrote a synthetic paper on coastal governance."
CLAIM = "synthetic paper on coastal governance"


def _card(corpus: Corpus, text: str = SPAN) -> None:
    corpus.upsert_record(Record(id="r1", source="slack", uri="slack://1", title="Note", text=text))
    corpus.put_card(
        ClaimCard(
            id="c1",
            claim=CLAIM,
            citations=["slack://1"],
            source="slack",
            status=STATUS_APPROVED,
            extras={"span": SPAN, "span_uri": "slack://1"},
        )
    )


def test_text_hash_is_stable_until_the_text_changes(corpus: Corpus) -> None:
    _card(corpus)
    row = corpus._conn.execute(
        "SELECT text_hash, text_changed_at FROM records WHERE uri = ?",
        ("slack://1",),
    ).fetchone()
    assert row["text_hash"] == text_hash(SPAN)
    corpus._conn.execute(
        "UPDATE records SET text_changed_at = ? WHERE uri = ?",
        ("2000-01-01T00:00:00+00:00", "slack://1"),
    )
    corpus._conn.commit()
    corpus.upsert_record(Record(id="r1", source="slack", uri="slack://1", title="Renamed", text=SPAN))
    again = corpus._conn.execute(
        "SELECT text_changed_at FROM records WHERE uri = ?",
        ("slack://1",),
    ).fetchone()
    assert again["text_changed_at"] == "2000-01-01T00:00:00+00:00"


def test_defend_refresh_keeps_one_previous_span(corpus: Corpus) -> None:
    _card(corpus)
    corpus.upsert_record(
        Record(
            id="r1",
            source="slack",
            uri="slack://1",
            title="Note",
            text="Quinn drafted a different synthetic paper on coastal governance.",
        )
    )
    defend_cards(corpus)
    card = corpus.get_card("c1")
    assert card is not None
    assert card.extras.get("span_prev") == SPAN
    assert "stale_reason" not in card.extras
    assert card.extras["span"] != SPAN


def test_drop_record_refuses_an_approved_citation(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    corpus = Corpus(tmp_path / "evidence.db")
    _card(corpus)
    corpus.close()
    assert main(["drop-record", "slack://1"]) == 1
    err = capsys.readouterr().err
    assert "c1" in err
    assert main(["drop-record", "slack://missing"]) == 2


def test_restore_checks_then_replaces(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    corpus = Corpus(tmp_path / "evidence.db")
    _card(corpus)
    corpus.close()
    assert main(["backup"]) == 0
    backup = Path(capsys.readouterr().out.strip())
    live = Corpus(tmp_path / "evidence.db")
    live.upsert_record(
        Record(id="r1", source="slack", uri="slack://1", title="Note", text="Replaced text.")
    )
    live.close()
    assert main(["restore", str(backup)]) == 0
    assert "check only" in capsys.readouterr().out
    checked = Corpus(tmp_path / "evidence.db")
    try:
        record = checked.get_record("slack://1")
        assert record is not None
        assert record.text == "Replaced text."
    finally:
        checked.close()
    assert main(["restore", str(backup), "--replace"]) == 0
    restored = Corpus(tmp_path / "evidence.db")
    try:
        assert restored.get_record("slack://1").text == SPAN
    finally:
        restored.close()
    assert (tmp_path / "evidence.pre-restore.db").is_file()


def test_notes_walk_lists_a_missed_file(tmp_path: Path, monkeypatch, capsys) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "a.md").write_text("Quinn wrote a synthetic paper on coastal governance in detail.")
    (notes / "b.md").write_text("Quinn convened a long workshop on kelp restoration for harbour towns.")
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    assert main(["ingest", "--adapter", "notes", str(notes)]) == 0
    (notes / "b.md").unlink()
    assert main(["ingest", "--adapter", "notes", str(notes)]) == 0
    assert main(["drift"]) == 0
    out = capsys.readouterr().out
    report = [line for line in out.splitlines() if line.endswith(".md") and "drift" in line]
    assert report
    body = Path(report[-1]).read_text(encoding="utf-8")
    assert "file://notes/b.md" in body


def test_match_postings_lists_a_repeated_gap(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    folder = tmp_path / "postings"
    folder.mkdir()
    line = "- Must have experience commanding a lunar base\n"
    (folder / "one.md").write_text(line, encoding="utf-8")
    (folder / "two.md").write_text(line, encoding="utf-8")
    Corpus(tmp_path / "evidence.db").close()
    assert main(["match", "--postings", str(folder)]) == 0
    out = capsys.readouterr().out
    path = Path(out.splitlines()[0])
    text = path.read_text(encoding="utf-8")
    assert "lunar base" in text
    assert "one.md" in text
    assert "two.md" in text


def test_title_change_does_not_mark_the_card_stale(corpus: Corpus) -> None:
    _card(corpus)
    corpus.upsert_record(Record(id="r1", source="slack", uri="slack://1", title="Renamed", text=SPAN))
    card = corpus.get_card("c1")
    assert card is not None
    assert "stale_reason" not in card.extras


def test_drift_lists_a_duplicate_sentence(corpus: Corpus, tmp_path: Path) -> None:
    from dossier.drift import collect_drift

    sentence = "Quinn wrote a synthetic paper on coastal governance last spring."
    corpus.upsert_record(Record(id="a", source="notes", uri="file://notes/a.md", title="A", text=sentence))
    corpus.upsert_record(Record(id="b", source="slack", uri="slack://b", title="B", text=sentence))
    report = collect_drift(corpus)
    assert any(sentence in text and len(uris) == 2 for text, uris in report.duplicates)


def test_packet_does_not_quote_the_previous_span(corpus: Corpus) -> None:
    from dossier.show import render_packet

    _card(corpus)
    corpus.upsert_record(
        Record(
            id="r1",
            source="slack",
            uri="slack://1",
            title="Note",
            text="Quinn drafted a different synthetic paper on coastal governance.",
        )
    )
    defend_cards(corpus)
    text = render_packet(corpus)
    assert f"> {SPAN}" not in text
    assert "Quinn drafted a different synthetic paper on coastal governance." in text


def test_import_skips_a_span_the_record_no_longer_holds(corpus: Corpus, tmp_path: Path) -> None:
    from dossier.portability import export_locker, import_locker

    _card(corpus)
    dest = tmp_path / "cards.json"
    export_locker(corpus, dest)
    other = Corpus(tmp_path / "other.db")
    try:
        other.upsert_record(
            Record(id="r1", source="slack", uri="slack://1", title="Note", text="A different sentence.")
        )
        result = import_locker(other, dest)
        assert result.imported == 0
        assert result.skipped == 1
        assert other.get_card("c1") is None
    finally:
        other.close()


def test_doctor_deep_counts_stale_marks(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    corpus = Corpus(tmp_path / "evidence.db")
    _card(corpus)
    corpus.upsert_record(
        Record(id="r1", source="slack", uri="slack://1", title="Note", text="Something else entirely now.")
    )
    corpus.close()
    assert main(["doctor", "--deep"]) == 0
    assert "stale_marked: 1" in capsys.readouterr().out


def test_drop_record_removes_an_uncited_record(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(Record(id="r1", source="notes", uri="file://notes/a.md", title="A", text=SPAN))
    corpus.close()
    assert main(["drop-record", "file://notes/a.md"]) == 0
    opened = Corpus(tmp_path / "evidence.db")
    try:
        assert opened.get_record("file://notes/a.md") is None
    finally:
        opened.close()


def test_match_postings_stops_at_twenty_files(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    folder = tmp_path / "postings"
    folder.mkdir()
    line = "- Must have experience commanding a lunar base\n"
    for index in range(21):
        (folder / f"{index:02d}.md").write_text(line, encoding="utf-8")
    Corpus(tmp_path / "evidence.db").close()
    assert main(["match", "--postings", str(folder)]) == 0
    assert "postings: 20 of 21" in capsys.readouterr().out


def test_a_sampled_seeker_does_not_record_unseen_uris(corpus: Corpus) -> None:
    corpus.begin_walk("slack", "/tmp/slack-export")
    corpus.upsert_record(Record(id="s", source="slack", uri="slack://1", title="Note", text=SPAN))
    assert corpus.finish_walk() == []
    assert corpus.unseen_rows() == []


def test_interrupted_job_shows_on_the_locker(tmp_path: Path, monkeypatch) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from dossier.web.app import create_app

    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    (jobs / "abc123.status").write_text("running\n", encoding="utf-8")
    app = create_app()
    with TestClient(app) as client:
        page = client.get("/drift")
        assert page.status_code == 200
        locker = client.get("/locker")
        assert "abc123" in locker.text
        assert "Interrupted" in locker.text
    assert (jobs / "abc123.status").read_text(encoding="utf-8").strip() == "interrupted"
