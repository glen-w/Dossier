"""Offline tests for modules the suite barely entered. Synthetic files only."""

from __future__ import annotations

import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from dossier.drift import collect_drift, render_drift, write_drift
from dossier.embed import (
    HashEmbedder,
    OllamaEmbedder,
    cosine,
    index_passages,
    pack_vector,
    unpack_vector,
)
from dossier.nextstep import next_step
from dossier.office import MEMBER_CAP, _read_zip_member, extract_office
from dossier.store import Corpus, Record, read_backup, replace_locker
from dossier.text import lens_kind, with_lens_kind


def test_next_step_follows_the_reason_then_the_counts() -> None:
    base = dict(records=4, pending=0, approved=0, spanned=0, vectors=2, detected=1)
    assert next_step(**base, reason="empty question")[0] == "/ask"
    assert next_step(**base, reason="requirement is too broad")[0] == "/match"
    empty = dict(base, records=0, vectors=0)
    assert next_step(**empty, reason="no matching records")[0] == "/sources"
    thin = dict(base, vectors=0)
    assert next_step(**thin, reason="no matching records")[0] == "/index"
    assert next_step(**base, reason="no matching records")[0] == "/sources"
    waiting = dict(base, pending=2)
    assert next_step(**waiting, reason="no carrying evidence")[0] == "/review"
    href, sentence = next_step(**dict(base, approved=3, spanned=1), reason="no direct span")
    assert href == "/review"
    assert "Defend" in sentence
    assert next_step(**dict(base, records=0), reason="no carrying")[0] == "/sources"
    assert next_step(**base, reason="no carrying evidence")[0] == "/extract"
    assert next_step(**base, reason="citation missing")[0] == "/extract"
    assert next_step(records=0, pending=0, approved=0, spanned=0, vectors=0, detected=0)[0] == "/sources"
    assert "Turn on" in next_step(
        records=0, pending=0, approved=0, spanned=0, vectors=0, detected=0
    )[1]
    assert "Ingest a detected" in next_step(
        records=0, pending=0, approved=0, spanned=0, vectors=0, detected=2
    )[1]
    assert "1 pending card." in next_step(
        records=1, pending=1, approved=0, spanned=0, vectors=0, detected=1
    )[1]
    assert "1 approved card " in next_step(
        records=1, pending=0, approved=2, spanned=1, vectors=0, detected=1
    )[1]
    assert next_step(records=3, pending=0, approved=0, spanned=0, vectors=0, detected=1)[0] == "/index"
    assert next_step(records=3, pending=0, approved=1, spanned=1, vectors=2, detected=1)[0] == "/match"
    assert next_step(records=3, pending=0, approved=0, spanned=0, vectors=2, detected=1)[0] == "/extract"


def test_lens_kind_reads_headers_or_extras() -> None:
    assert lens_kind("body", {"lens": "Delivered", "kind": "Note"}) == ("delivered", "note")
    assert lens_kind("Lens: skills\nKind: talk\nbody") == ("skills", "talk")
    assert lens_kind("no headers") == ("", "")
    prefixed = with_lens_kind("already", "skills", "talk")
    assert prefixed.startswith("Lens: skills")
    assert with_lens_kind("Lens: kept") == "Lens: kept"


def test_office_edges_stay_inventory_lines(tmp_path: Path) -> None:
    text, reason = extract_office(tmp_path / "note.txt")
    assert text == ""
    assert reason == "not an office file"

    empty = tmp_path / "empty.docx"
    xml = (
        "<?xml version='1.0'?>"
        "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'/>"
    )
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("word/document.xml", xml)
    assert extract_office(empty)[1] == "no text in office file"

    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"not a zip")
    assert extract_office(broken)[1]

    slides = tmp_path / "talk.pptx"
    slide = (
        "<?xml version='1.0'?>"
        "<a:t xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'>"
        "Coastal governance workshop</a:t>"
    )
    with zipfile.ZipFile(slides, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", slide)
    text, reason = extract_office(slides)
    assert reason == ""
    assert "Coastal governance" in text

    huge = tmp_path / "huge.docx"
    with zipfile.ZipFile(huge, "w") as archive:
        archive.writestr("word/document.xml", b"<w:t>x</w:t>")
    with zipfile.ZipFile(huge) as archive:
        archive.getinfo("word/document.xml").file_size = MEMBER_CAP + 1
        with pytest.raises(RuntimeError, match="size cap"):
            _read_zip_member(archive, "word/document.xml")


def test_blank_pdf_is_an_inventory_line(tmp_path: Path) -> None:
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter

    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)
    text, reason = extract_office(path)
    assert text == ""
    assert reason == "no text in office file"


def test_ollama_embedder_uses_the_local_client(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class _Response:
        def __init__(self, payload: dict, fail: bool = False) -> None:
            self.payload = payload
            self.fail = fail

        def raise_for_status(self) -> None:
            if self.fail:
                raise httpx.HTTPError("down")

        def json(self) -> dict:
            return self.payload

    class _Client:
        def __init__(self, timeout: float = 10) -> None:
            self.timeout = timeout

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def get(self, url: str) -> _Response:
            calls.append(url)
            return _Response({"models": [{"name": "nomic-embed-text:latest"}]})

        def post(self, url: str, json: dict) -> _Response:
            calls.append(url)
            if json["input"] == ["bad"]:
                return _Response({}, fail=True)
            if json["input"] == ["empty"]:
                return _Response({"embeddings": [[]]})
            if json["input"] == ["one"]:
                return _Response({"embedding": [0.5, 0.5]})
            return _Response({"embeddings": [[0.1, 0.2]]})

    monkeypatch.setattr("dossier.embed.httpx.Client", _Client)
    local = OllamaEmbedder("http://127.0.0.1:11434/v1", False, "nomic-embed-text")
    assert local.base_url == "http://127.0.0.1:11434"
    ok, message = local.check()
    assert ok and message == "ok"
    assert local.embed([]) == []
    assert local.embed(["coast"]) == [[0.1, 0.2]]
    assert local.embed(["one"]) == [[0.5, 0.5]]
    from dossier.embed import EmbedError

    with pytest.raises(EmbedError):
        local.embed(["bad"])
    with pytest.raises(EmbedError):
        local.embed(["empty"])
    missing = OllamaEmbedder("http://127.0.0.1:11434", False, "missing-model")

    class _Missing(_Client):
        def get(self, url: str) -> _Response:
            return _Response({"models": []})

    monkeypatch.setattr("dossier.embed.httpx.Client", _Missing)
    assert missing.check()[0] is False

    class _Down(_Client):
        def get(self, url: str) -> _Response:
            return _Response({}, fail=True)

    monkeypatch.setattr("dossier.embed.httpx.Client", _Down)
    assert "unreachable" in OllamaEmbedder("http://127.0.0.1:11434", False, "nomic").check()[1]
    remote = OllamaEmbedder("http://example.com", False, "nomic")
    assert remote.check()[0] is False


def test_hash_embedder_and_vector_math() -> None:
    embedder = HashEmbedder(dim=8)
    assert embedder.check() == (True, "ok")
    empty = embedder.embed([""])[0]
    assert empty[0] == 1.0
    packed = pack_vector([1.0, -2.0])
    assert unpack_vector(packed) == pytest.approx([1.0, -2.0])
    assert unpack_vector(b"\x00\x00") == []
    assert cosine([], [1.0]) == 0.0
    assert cosine([0.0], [0.0]) == 0.0
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_index_reports_batches_and_stops_on_an_empty_page(tmp_path: Path) -> None:
    corpus = Corpus(tmp_path / "evidence.db")
    try:
        corpus.upsert_record(
            Record(id="r", source="notes", uri="notes://1", title="Note", text="Quinn wrote a note.")
        )
        seen: list[tuple[int, int]] = []
        index_passages(corpus, HashEmbedder(dim=8), on_batch=lambda done, total: seen.append((done, total)))
        assert seen[0] == (0, seen[0][1])
        assert seen[-1][0] == seen[-1][1]
        corpus.passages_missing_vector = lambda *args, **kwargs: []  # type: ignore[method-assign]
        corpus.drop_other_vectors("other")
        index_passages(corpus, HashEmbedder(dim=8, model="other"), limit=3)
    finally:
        corpus.close()


def test_drift_report_names_empty_sections_and_does_not_overwrite(tmp_path: Path, corpus: Corpus) -> None:
    text = render_drift(collect_drift(corpus))
    assert "None." in text
    corpus.upsert_record(
        Record(id="a", source="notes", uri="notes://a", title="A", text="Short.")
    )
    assert collect_drift(corpus).duplicates == ()

    class _Clock:
        @staticmethod
        def now(tz: object) -> datetime:
            return datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)

    import dossier.drift as drift_mod

    drift_mod.datetime = _Clock  # type: ignore[assignment]
    try:
        first, _report = write_drift(corpus, tmp_path)
        second, _again = write_drift(corpus, tmp_path)
    finally:
        drift_mod.datetime = datetime
    assert first != second
    assert second.exists()


def test_read_backup_refuses_a_missing_file_and_an_empty_database(tmp_path: Path) -> None:
    missing = read_backup(tmp_path / "nope.db")
    assert missing.ok is False
    assert "missing" in missing.reason
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    info = read_backup(empty)
    assert info.ok is False
    assert "no locker tables" in info.reason
    with pytest.raises(RuntimeError):
        replace_locker(tmp_path / "live.db", empty)
