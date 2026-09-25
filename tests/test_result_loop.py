"""Fixture corpus: draft, defend, match, tailor. Prove never approves."""

from __future__ import annotations

import zipfile
from pathlib import Path

from dossier.cards import STATUS_APPROVED, STATUS_PENDING, STATUS_REFUSED, ClaimCard, adjudicate, card_id
from dossier.config import Config
from dossier.match import match_posting
from dossier.nextstep import next_step
from dossier.office import extract_office
from dossier.review import apply_action, list_cards
from dossier.show import defend_cards
from dossier.sources.applications import ApplicationsSource
from dossier.store import Corpus, Record
from dossier.tailor import render_draft, select_cards

SENTENCE = "Drafted the coastal governance workshop briefing for the ministry."
POSTING = "- experience drafting a coastal governance workshop briefing\n"


def _seed(corpus: Corpus) -> str:
    corpus.upsert_record(
        Record(
            id="emp",
            source="employer",
            uri="file://employer/note",
            title="briefing",
            text=SENTENCE,
        )
    )
    corpus.upsert_record(
        Record(
            id="git",
            source="git",
            uri="git://repo/1",
            title="commit",
            text="Updated the repository README.",
        )
    )
    claim = SENTENCE
    cid = card_id(claim, ["file://employer/note"])
    corpus.put_card(
        ClaimCard(
            id=cid,
            claim=claim,
            citations=["file://employer/note"],
            source="employer",
            status=STATUS_PENDING,
        )
    )
    return cid


def test_next_step_names_review_when_cards_are_pending() -> None:
    href, sentence = next_step(
        records=2, pending=3, approved=0, spanned=0, vectors=0, detected=1
    )
    assert href == "/review"
    assert "pending" in sentence


def test_defend_stores_span_without_changing_status(corpus: Corpus) -> None:
    cid = _seed(corpus)
    shown = list_cards(corpus, status="pending")
    assert shown["cards"][0]["carrying"] == SENTENCE
    assert shown["cards"][0]["span"] == ""
    changed = apply_action(corpus, {"action": "defend", "ids": [cid]})
    assert changed == 1
    card = corpus.get_card(cid)
    assert card is not None
    assert card.status == STATUS_PENDING
    assert card.extras["span"] == SENTENCE


def test_fixture_loop_quotes_only_the_span(corpus: Corpus, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    cid = _seed(corpus)
    apply_action(corpus, {"action": "approve", "ids": [cid]})
    spanned, unspanned = defend_cards(corpus)
    assert [card.id for card in spanned] == [cid]
    assert unspanned == []
    bare = ClaimCard(
        id="bare",
        claim="Invented a prize the record does not mention.",
        citations=["git://repo/1"],
        source="git",
        status=STATUS_REFUSED,
        reason="evidence does not carry the claim",
    )
    status, _reason = adjudicate(bare.claim, bare.citations, {"git://repo/1": "Updated the repository README."})
    assert status == STATUS_REFUSED

    cfg = Config.from_env()
    report = match_posting(corpus, POSTING, cfg)
    quotes = [hit.quote for req in report.requirements for hit in req.evidence]
    assert SENTENCE in quotes
    assert bare.claim not in quotes

    corpus.get_card(cid)
    picked, missing = select_cards(corpus, POSTING, limit=8)
    text = render_draft(kind="cv", posting=POSTING, picked=picked, bare=missing)
    assert SENTENCE in text
    assert bare.claim not in text
    assert all(item.card.status == STATUS_APPROVED for item in picked)
    assert tmp_path  # fixture dir stays unused; the loop does not write a CV PDF


def test_docx_text_is_capped_and_a_bad_pdf_stays_inventory(tmp_path: Path, corpus: Corpus) -> None:
    docx = tmp_path / "briefing.docx"
    xml = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        f"<w:t>{SENTENCE}</w:t></w:document>"
    )
    with zipfile.ZipFile(docx, "w") as archive:
        archive.writestr("word/document.xml", xml)
    text, reason = extract_office(docx)
    assert reason == ""
    assert SENTENCE in text

    root = tmp_path / "job applications" / "pack"
    root.mkdir(parents=True)
    (root / "cv.pdf").write_bytes(b"not a pdf")
    ApplicationsSource().load(tmp_path / "job applications", corpus)
    pdf = next(rec for rec in corpus.records("applications") if rec.uri.endswith(".pdf"))
    assert "Binary body not ingested" in pdf.text
