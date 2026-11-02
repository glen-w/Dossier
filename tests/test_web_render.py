"""Workbench Tailor page: format choice and the download route."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from dossier.cards import STATUS_APPROVED, ClaimCard
from dossier.store import Corpus, Record

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from dossier.jobs import RUNNER
from dossier.web.app import create_app

SENTENCE = "Drafted the ocean workshop briefing."


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(
        Record(
            id="r1",
            source="slack",
            uri="slack://1",
            title="Note",
            text=f"Lens: delivered\nKind: workshop\n{SENTENCE}",
        )
    )
    corpus.put_card(
        ClaimCard(
            id="c1",
            claim="Drafted the ocean workshop",
            citations=["slack://1"],
            source="slack",
            status=STATUS_APPROVED,
            extras={"span": SENTENCE, "span_uri": "slack://1", "lens": "delivered", "kind": "workshop"},
        )
    )
    corpus.close()
    with TestClient(create_app()) as test_client:
        yield test_client, tmp_path


def _run(test_client, fmt: str):
    resp = test_client.post(
        "/tailor/run",
        data={"posting": "We need an ocean workshop.", "kind": "cv", "fmt": fmt, "with_sources": "1"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    location = resp.headers["location"]
    job = RUNNER.get(location.split("job=", 1)[1])
    for _ in range(100):
        if job.status in {"done", "error"}:
            break
        time.sleep(0.05)
    assert job.status == "done", job.error
    return location, job.result


def test_tailor_page_offers_formats(client) -> None:
    test_client, _ = client
    page = test_client.get("/tailor")
    assert page.status_code == 200
    for option in (b"docx", b"pdf", b"html"):
        assert option in page.content


@pytest.mark.parametrize("fmt,suffix", [("html", ".html"), ("docx", ".docx"), ("pdf", ".pdf")])
def test_format_job_writes_a_file_and_links_it(client, fmt: str, suffix: str) -> None:
    if fmt == "pdf":
        pytest.importorskip("fpdf")
    test_client, root = client
    location, result = _run(test_client, fmt)
    assert result["file"].endswith(suffix)
    assert (root / "drafts" / result["file"]).is_file()
    page = test_client.get(location)
    assert f"/tailor/file?name={result['file']}".encode() in page.content
    got = test_client.get(f"/tailor/file?name={result['file']}")
    assert got.status_code == 200
    assert "attachment" in got.headers["content-disposition"]
    assert got.headers["x-content-type-options"] == "nosniff"
    assert len(got.content) > 200


def test_markdown_job_has_no_download(client) -> None:
    test_client, _ = client
    _location, result = _run(test_client, "markdown")
    assert result["file"] == ""


@pytest.mark.parametrize(
    "name",
    ["", "../evidence.db", "..%2Fevidence.db", "/etc/passwd", "sub/dir.md", "x.exe", "nope.pdf"],
)
def test_download_refuses_anything_outside_the_drafts_folder(client, name: str) -> None:
    test_client, root = client
    (root / "secret.html").write_text("secret", encoding="utf-8")
    assert test_client.get("/tailor/file", params={"name": name}).status_code == 404
    assert test_client.get("/tailor/file", params={"name": "secret.html"}).status_code == 404


def test_unknown_format_falls_back_to_markdown(client) -> None:
    test_client, _ = client
    _location, result = _run(test_client, "rtf")
    assert result["file"] == ""
