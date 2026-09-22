"""Request scope: sources, years, and effort over the saved defaults."""

from __future__ import annotations

from pathlib import Path

from dossier.cards import STATUS_APPROVED, ClaimCard
from dossier.config import Config
from dossier.match import match_posting
from dossier.profiles import load_profile, save_profile
from dossier.scope import (
    RequestScope,
    apply_request_scope,
    in_scope,
    known_sources,
    scope_toml,
    sources_for_request,
)
from dossier.store import Corpus, Record


def _cfg(**kwargs) -> Config:
    return Config(ask_fts=False, ask_passages=True, ask_embed=False, llm_enabled=False, **kwargs)


def _record(source: str, uri: str, text: str) -> Record:
    return Record(id=uri, source=source, uri=uri, title="note", text=text)


def test_all_checked_sources_mean_every_source() -> None:
    assert sources_for_request(list(known_sources())) is None
    assert sources_for_request(["slack"]) == ("slack",)
    assert sources_for_request([]) == ()


def test_year_keeps_undated_and_drops_the_outside_year() -> None:
    cfg = _cfg(scope_year_from=2018, scope_year_to=2020)
    inside = _record("slack", "slack://in", "Year: 2019\n\nLed ocean workshops.")
    outside = _record("slack", "slack://out", "Year: 2015\n\nLed ocean workshops.")
    undated = _record("slack", "slack://none", "Led ocean workshops last year.")
    assert in_scope(inside, cfg)
    assert not in_scope(outside, cfg)
    assert in_scope(undated, cfg)
    assert not in_scope(inside, _cfg(scope_sources=("employer",)))


def test_match_uses_only_the_checked_source_and_year(tmp_path: Path) -> None:
    corpus = Corpus(tmp_path / "evidence.db")
    try:
        corpus.upsert_record(
            _record(
                "slack",
                "slack://ocean",
                "Year: 2019\n\nLed the ocean workshops for the coastal team.",
            )
        )
        corpus.upsert_record(
            _record(
                "employer",
                "employer://old",
                "Year: 2014\n\nLed the ocean workshops for the ministry.",
            )
        )
        corpus.upsert_record(
            _record(
                "employer",
                "employer://new",
                "Year: 2020\n\nLed the ocean workshops for the harbour.",
            )
        )
        report = match_posting(
            corpus,
            "- Experience leading ocean workshops",
            _cfg(scope_sources=("employer",), scope_year_from=2018, scope_year_to=2021),
        )
    finally:
        corpus.close()
    assert [hit.uri for hit in report.requirements[0].evidence] == ["employer://new"]


def test_approved_span_outside_the_source_stays_out(tmp_path: Path) -> None:
    corpus = Corpus(tmp_path / "evidence.db")
    try:
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
                extras={"span": "Led ocean workshops last year.", "span_uri": "slack://a"},
            )
        )
        report = match_posting(
            corpus,
            "- Experience leading ocean workshops",
            _cfg(scope_sources=("employer",)),
        )
    finally:
        corpus.close()
    assert report.requirements[0].evidence == ()


def test_effort_on_a_request_does_not_need_a_new_file() -> None:
    cfg = apply_request_scope(
        _cfg(ask_mode="auto", effort="balanced"),
        RequestScope(sources=("slack",), year_from=2019, year_to=2019, effort="light"),
    )
    assert cfg.effort == "light"
    assert cfg.ask_mode == "exact"
    assert cfg.scope_sources == ("slack",)
    assert cfg.scope_year_from == 2019


def test_profile_stores_a_source_subset(tmp_path: Path) -> None:
    save_profile(
        "narrow",
        description="slack 2019",
        config={
            "effort": "high",
            "scope": {"sources": ["slack"], "year_from": 2019, "year_to": 2019},
            "ignored": {"nope": 1},
        },
        root=tmp_path,
    )
    profile = load_profile("narrow", tmp_path)
    assert profile.config["scope"]["sources"] == ["slack"]
    assert "ignored" not in profile.config
    from dossier.profiles import activate_profile

    activate_profile("narrow", tmp_path)
    text = (tmp_path / "dossier.toml").read_text(encoding="utf-8")
    assert 'effort = "high"' in text
    assert "slack" in text
    assert "year_from = 2019" in text


def test_ask_does_not_cite_a_source_left_out(tmp_path: Path) -> None:
    from dossier.interview import conduct
    from dossier.llm.client import NullLLMClient

    corpus = Corpus(tmp_path / "evidence.db")
    try:
        corpus.upsert_record(
            _record("slack", "slack://ocean", "Led the ocean workshops for the coastal team.")
        )
        result = conduct(
            corpus,
            "ocean workshops",
            _cfg(scope_sources=("employer",), ask_cards_first=False),
            NullLLMClient(),
            mode="exact",
            limit=5,
        )
    finally:
        corpus.close()
    assert result.refused
    assert "slack://ocean" not in result.citations


def test_cli_match_sources_and_year(tmp_path: Path, monkeypatch, capsys) -> None:
    from dossier.cli import main

    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(
        _record("slack", "slack://ocean", "Year: 2019\n\nLed the ocean workshops for the coastal team.")
    )
    corpus.upsert_record(
        _record("employer", "employer://new", "Year: 2020\n\nLed the ocean workshops for the harbour.")
    )
    corpus.close()
    posting = tmp_path / "posting.txt"
    posting.write_text("- Experience leading ocean workshops\n", encoding="utf-8")
    code = main(
        ["match", "--posting", str(posting), "--sources", "employer", "--year-from", "2018"]
    )
    assert code == 0
    written = list((tmp_path / "matches").glob("*.md"))
    text = written[0].read_text(encoding="utf-8")
    assert "employer://new" in text
    assert "slack://ocean" not in text
    capsys.readouterr()


def test_scope_toml_all_sources_flag() -> None:
    assert scope_toml(None, 0, 0)["all"] is True
    assert scope_toml(("slack",), 2018, 2020)["sources"] == ["slack"]
