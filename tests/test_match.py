"""Job-spec match: split a posting, then rank evidence per requirement."""

from __future__ import annotations

from pathlib import Path

import pytest

from dossier.ask import Hit
from dossier.cards import STATUS_APPROVED, ClaimCard
from dossier.cli import main
from dossier.config import Config
from dossier.match import (
    GAP_BROAD,
    GAP_NONE,
    REQ_CAP,
    match_posting,
    split_requirements,
    write_match,
)
from dossier.store import Corpus, Record


def _cfg() -> Config:
    return Config(ask_fts=False, ask_passages=True, ask_embed=True, llm_enabled=False)


def _record(source: str, uri: str, text: str, title: str = "note") -> Record:
    return Record(id=uri, source=source, uri=uri, title=title, text=text)


def test_split_keeps_bullets_in_order_and_drops_benefits() -> None:
    ordered = split_requirements("- First ocean workshops\n- Second fisheries tables\n")
    assert [item.text for item in ordered] == [
        "First ocean workshops",
        "Second fisheries tables",
    ]
    assert all(not item.unsplit for item in ordered)

    spec = """
Benefits
- Pension scheme
- Extra leave
Requirements:
- Experience leading ocean workshops
"""
    kept = split_requirements(spec)
    assert [item.text for item in kept] == ["Experience leading ocean workshops"]


def test_split_keeps_a_cue_sentence_caps_and_marks_unsplit() -> None:
    spec = """
About the role
The team sits in Paris.
You will coordinate coastal workshops.
"""
    kept = split_requirements(spec)
    assert len(kept) == 1
    assert kept[0].text == "You will coordinate coastal workshops."
    assert not kept[0].unsplit

    lines = [
        f"- Experience item {index:02d} for ocean workshops" for index in range(REQ_CAP + 1)
    ]
    capped = split_requirements("\n".join(lines))
    assert len(capped) == REQ_CAP
    assert "item 00" in capped[0].text
    assert "item 19" in capped[-1].text
    assert all("item 20" not in item.text for item in capped)

    blob = split_requirements("We are a friendly team.")
    assert len(blob) == 1
    assert blob[0].unsplit
    assert split_requirements("  \n") == []


def test_rank_orders_requirements_and_drops_generic_overlap(tmp_path: Path) -> None:
    corpus = Corpus(tmp_path / "evidence.db")
    try:
        corpus.upsert_record(
            _record(
                "slack",
                "slack://ocean",
                "Year: 2019\n\nLed the ocean workshops for the coastal team.",
                title="Ocean workshop",
            )
        )
        corpus.upsert_record(
            _record(
                "employer",
                "employer://tables",
                "Built fisheries data tables for the annual report.",
                title="Fisheries tables",
            )
        )
        corpus.upsert_record(
            _record(
                "slack",
                "slack://noise",
                "Show the recorded work today in the office.",
                title="Status",
            )
        )
        corpus.upsert_record(
            _record(
                "employer",
                "employer://workshops",
                "Show the workshops on the coast.",
                title="Coast workshops",
            )
        )
        spec = """
- Experience leading ocean workshops
- Knowledge of lunar mining permits
- Knowledge of fisheries data tables
- Show the recorded work on workshops
"""
        report = match_posting(corpus, spec, _cfg())
    finally:
        corpus.close()

    assert [item.text for item in report.requirements] == [
        "Experience leading ocean workshops",
        "Knowledge of lunar mining permits",
        "Knowledge of fisheries data tables",
        "Show the recorded work on workshops",
    ]
    ocean, lunar, fisheries, workshops = report.requirements
    assert [hit.uri for hit in ocean.evidence] == ["slack://ocean"]
    assert ocean.evidence[0].year == "2019"
    assert ocean.evidence[0].route == "passage"
    assert lunar.gap == GAP_NONE
    assert lunar.evidence == ()
    assert [hit.uri for hit in fisheries.evidence] == ["employer://tables"]
    assert [hit.uri for hit in workshops.evidence] == ["employer://workshops"]
    assert "slack://noise" not in {hit.uri for hit in workshops.evidence}

    text = write_match(report, tmp_path / "matches").read_text(encoding="utf-8")
    assert "gap: no carrying evidence" in text
    assert "uri: slack://ocean" in text
    assert "2019" in text


def test_broad_requirement_is_a_gap(tmp_path: Path) -> None:
    corpus = Corpus(tmp_path / "evidence.db")
    try:
        corpus.upsert_record(
            _record("slack", "slack://1", "Show the recorded work and skills today.")
        )
        report = match_posting(corpus, "- Show recorded work skills", _cfg())
    finally:
        corpus.close()
    assert report.requirements[0].broad
    assert report.requirements[0].gap == GAP_BROAD
    assert report.requirements[0].evidence == ()


def test_source_cap_drops_a_third_hit_from_the_same_source(tmp_path: Path) -> None:
    corpus = Corpus(tmp_path / "evidence.db")
    try:
        text = "Led ocean workshops for coastal teams."
        corpus.upsert_record(_record("employer", "employer://1", text))
        for index in (1, 2, 3):
            corpus.upsert_record(_record("slack", f"slack://{index}", text))
        report = match_posting(
            corpus,
            "- Experience leading ocean workshops",
            _cfg(),
        )
    finally:
        corpus.close()
    uris = [hit.uri for hit in report.requirements[0].evidence]
    assert uris == ["employer://1", "slack://1", "slack://2"]
    assert sum(1 for hit in report.requirements[0].evidence if hit.source == "slack") == 2


def test_approved_span_sorts_first(tmp_path: Path) -> None:
    corpus = Corpus(tmp_path / "evidence.db")
    try:
        corpus.upsert_record(
            _record(
                "slack",
                "slack://z",
                "Experience leading ocean workshops for the ministry last spring.",
            )
        )
        corpus.upsert_record(
            _record("slack", "slack://a", "Led ocean workshops last year.")
        )
        corpus.put_card(
            ClaimCard(
                id="card-a",
                claim="Led ocean workshops",
                citations=["slack://a"],
                source="slack",
                status=STATUS_APPROVED,
                extras={
                    "span": "Led ocean workshops last year.",
                    "span_uri": "slack://a",
                },
            )
        )
        report = match_posting(
            corpus,
            "- Experience leading ocean workshops",
            _cfg(),
        )
    finally:
        corpus.close()
    evidence = report.requirements[0].evidence
    assert [hit.uri for hit in evidence] == ["slack://a", "slack://z"]
    assert evidence[0].route == "span"
    assert evidence[0].card_id == "card-a"
    assert evidence[0].card_status == "approved"
    assert evidence[0].rank == 1


def test_embedder_failure_still_returns_lexical_rows(tmp_path: Path) -> None:
    corpus = Corpus(tmp_path / "evidence.db")
    try:
        corpus.upsert_record(
            _record("slack", "slack://ocean", "Led the ocean workshops for the coastal team.")
        )

        class _Down:
            model = "fake"

            def embed(self, texts: list[str]) -> list[list[float]]:
                raise RuntimeError("ollama down")

        report = match_posting(
            corpus,
            "- Experience leading ocean workshops",
            _cfg(),
            embedder=_Down(),
        )
    finally:
        corpus.close()
    assert [hit.uri for hit in report.requirements[0].evidence] == ["slack://ocean"]


def test_fuses_neighbor_when_lexical_hits_already_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = Corpus(tmp_path / "evidence.db")
    try:
        corpus.upsert_record(
            _record("slack", "slack://1", "Led the ocean workshops for the coastal team.")
        )
        corpus.upsert_record(
            _record("employer", "employer://1", "Led the ocean workshops for the ministry.")
        )
        corpus.upsert_record(
            _record(
                "git",
                "git://budget",
                "Budget spreadsheets sat in the finance folder.",
                title="Budget",
            )
        )

        def _neighbors(corpus, vector, model, records, limit):  # noqa: ANN001
            return [
                Hit(
                    uri="git://budget",
                    title="Budget",
                    text="Budget spreadsheets sat in the finance folder.",
                    score=90,
                    cosine=0.9,
                )
            ]

        monkeypatch.setattr("dossier.match._vector_hits", _neighbors)

        class _Emb:
            model = "fake"

            def embed(self, texts: list[str]) -> list[list[float]]:
                return [[0.2, 0.8, 0.1]]

        report = match_posting(
            corpus,
            "- Experience leading ocean workshops",
            _cfg(),
            embedder=_Emb(),
        )
    finally:
        corpus.close()
    evidence = report.requirements[0].evidence
    assert {hit.uri for hit in evidence} >= {"slack://1", "employer://1", "git://budget"}
    neighbor = next(hit for hit in evidence if hit.uri == "git://budget")
    assert neighbor.route == "neighbor"


def test_cli_match_prints_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(
        _record("slack", "slack://ocean", "Led the ocean workshops for the coastal team.")
    )
    corpus.close()
    posting = tmp_path / "posting.txt"
    posting.write_text(
        "- Experience leading ocean workshops\n- Knowledge of lunar mining permits\n",
        encoding="utf-8",
    )
    code = main(["match", "--posting", str(posting)])
    assert code == 0
    out = capsys.readouterr().out
    assert "requirements: 2 · with evidence: 1 · gaps: 1" in out
    written = list((tmp_path / "matches").glob("*.md"))
    assert len(written) == 1
    assert "gap: no carrying evidence" in written[0].read_text(encoding="utf-8")

    empty = tmp_path / "empty.txt"
    empty.write_text("  \n", encoding="utf-8")
    code = main(["match", "--posting", str(empty)])
    assert code == 2
    assert "posting is empty" in capsys.readouterr().err
