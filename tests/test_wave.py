import json
import sqlite3
from pathlib import Path

import pytest

from dossier.ask import expand_tokens, respond, retrieve
from dossier.brief import ask_hits
from dossier.cards import STATUS_PENDING, ClaimCard
from dossier.cli import main
from dossier.config import Config
from dossier.extract import extract_corpus
from dossier.store import Corpus, Record


class _Boom:
    provider = "boom"

    def check_config(self, model: str) -> tuple[bool, str]:
        return True, "ok"

    def complete(self, request) -> str:
        raise AssertionError("model should not be called")

    def complete_json(self, request) -> dict:
        raise AssertionError("model should not be called")


class _Once:
    provider = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def check_config(self, model: str) -> tuple[bool, str]:
        return True, "ok"

    def complete(self, request) -> str:
        return ""

    def complete_json(self, request) -> dict:
        self.calls += 1
        return {
            "answer": "You wrote a synthetic paper on coastal governance.",
            "citations": ["zotero://fixture/a"],
        }


def _coastal(uri: str = "zotero://fixture/1") -> Record:
    return Record(
        id=uri,
        source="pubs",
        uri=uri,
        title="Synthetic coastal paper",
        text="Glen wrote a synthetic paper on coastal governance.",
    )


def test_fts_ranks_the_overlapping_record_first(corpus: Corpus) -> None:
    coastal = _coastal()
    other = Record(
        id="shop",
        source="chatgpt",
        uri="chatgpt://c/m",
        title="Shopping",
        text="Buy milk and eggs tomorrow.",
    )
    corpus.upsert_record(other)
    corpus.upsert_record(coastal)
    if corpus.fts_ok:
        found = corpus.search_fts('"coastal" OR "governance"', limit=5)
        assert found is not None
        assert found[0][0] == coastal.uri
        hits = retrieve(
            corpus.records(),
            "coastal governance",
            fts_rank={uri: rank for uri, rank in found},
        )
    else:
        assert corpus.search_fts('"coastal"', limit=5) is None
        hits = retrieve(corpus.records(), "coastal governance")
    assert hits[0].uri == coastal.uri


def test_overlap_breaks_equal_fts_ranks() -> None:
    weaker = Record(
        id="low",
        source="pubs",
        uri="zotero://low",
        title="Coastal note",
        text="A coastal note.",
    )
    stronger = Record(
        id="high",
        source="pubs",
        uri="zotero://high",
        title="Coastal governance paper",
        text="Glen wrote a synthetic paper on coastal governance.",
    )
    same = {"zotero://low": -1.0, "zotero://high": -1.0}
    hits = retrieve(
        [weaker, stronger],
        "coastal governance paper",
        fts_rank=same,
    )
    assert [hit.uri for hit in hits] == ["zotero://high", "zotero://low"]
    better_rank = {"zotero://low": -2.0, "zotero://high": -1.0}
    ranked = retrieve(
        [weaker, stronger],
        "coastal governance paper",
        fts_rank=better_rank,
    )
    assert ranked[0].uri == "zotero://low"


def test_exact_quotes_without_calling_the_model() -> None:
    hits = retrieve([_coastal()], "coastal governance paper")
    result = respond("coastal governance paper", hits, _Boom(), "fake", mode="exact")
    assert not result.refused
    assert result.citations == ["zotero://fixture/1"]
    assert "coastal governance" in result.text


def test_auto_falls_through_to_one_completion_on_a_tie() -> None:
    records = [
        _coastal("zotero://fixture/a"),
        Record(
            id="b",
            source="pubs",
            uri="zotero://fixture/b",
            title="Another coastal paper",
            text="Glen wrote a synthetic paper on coastal governance.",
        ),
    ]
    hits = retrieve(records, "coastal governance paper")
    assert len(hits) == 2
    assert hits[0].score == hits[1].score
    client = _Once()
    result = respond("coastal governance paper", hits, client, "fake", mode="auto")
    assert client.calls == 1
    assert not result.refused
    exact = respond("coastal governance paper", hits, _Boom(), "fake", mode="exact")
    assert not exact.refused


def test_uncited_completion_is_refused() -> None:
    hits = retrieve([_coastal()], "coastal governance paper")

    class _Empty:
        provider = "fake"

        def complete_json(self, request) -> dict:
            return {"answer": "You wrote a synthetic paper on coastal governance.", "citations": []}

    result = respond("coastal governance", hits, _Empty(), "fake", mode="rich")
    assert result.refused
    assert result.reason == "no cited answer"


def test_follow_context_is_in_the_prompt() -> None:
    seen: list[str] = []

    class _Capture:
        provider = "fake"

        def complete_json(self, request) -> dict:
            seen.append(request.prompt)
            return {
                "answer": "You wrote a synthetic paper on coastal governance.",
                "citations": ["zotero://fixture/1"],
            }

    hits = retrieve([_coastal()], "coastal governance")
    result = respond(
        "coastal governance",
        hits,
        _Capture(),
        "fake",
        mode="rich",
        prior=["Earlier note about coastal governance."],
    )
    assert not result.refused
    assert "Earlier note about coastal governance." in seen[0]
    assert "Do not cite them" in seen[0]


def test_linkedin_draft_skips_the_model(corpus: Corpus) -> None:
    record = Record(
        id="pos",
        source="linkedin",
        uri="linkedin://positions/0",
        title="Analyst at Oceans",
        text="Analyst at Oceans. Paris. 2019–2022. Worked on coastal governance.",
        table="linkedin.positions",
    )
    corpus.upsert_record(record)
    cards = extract_corpus(corpus, _Boom(), "fake", use_llm=True)
    assert len(cards) == 1
    assert cards[0].status == STATUS_PENDING
    assert cards[0].claim == "Analyst at Oceans"
    assert corpus.record_has_open_card(record.id)


def test_seeker_draft_keeps_header_extras(corpus: Corpus) -> None:
    record = Record(
        id="slack1",
        source="slack",
        uri="slack://C/1.0",
        title="GSR ocean chapter",
        text="Lens: delivered\nKind: chapter\nOrg: REN21\nYear: 2023\nDrafted the GSR ocean chapter.",
        table="slack.hits",
    )
    corpus.upsert_record(record)
    cards = extract_corpus(corpus, _Boom(), "fake", use_llm=True)
    assert cards[0].status == STATUS_PENDING
    assert cards[0].extras["lens"] == "delivered"
    assert cards[0].extras["kind"] == "chapter"
    assert cards[0].extras["org"] == "REN21"


def test_open_card_is_not_sent_back_to_the_model(corpus: Corpus) -> None:
    record = Record(
        id="pos",
        source="linkedin",
        uri="linkedin://positions/0",
        title="Analyst at Oceans",
        text="Analyst at Oceans. Paris. Worked on coastal governance.",
        table="linkedin.positions",
    )
    corpus.upsert_record(record)
    first = extract_corpus(corpus, _Boom(), "fake", use_llm=True)
    assert first[0].status == STATUS_PENDING
    again = extract_corpus(corpus, _Boom(), "fake", use_llm=True)
    assert again == []


def test_skills_draft_copies_the_skills_line(corpus: Corpus) -> None:
    record = Record(
        id="skills",
        source="linkedin",
        uri="linkedin://skills",
        title="LinkedIn skills",
        text="Skills: facilitation, teaching",
        table="linkedin.skills",
    )
    corpus.upsert_record(record)
    cards = extract_corpus(corpus, _Boom(), "fake", use_llm=False)
    assert cards[0].claim == "Skills: facilitation, teaching"
    assert cards[0].status == STATUS_PENDING


def test_recent_answers_skip_refusals_and_cap_at_three(corpus: Corpus) -> None:
    corpus.add_answer(
        question="nope",
        mode="exact",
        text="",
        citations=[],
        refused=True,
        reason="no matching records",
    )
    for index in range(4):
        corpus.add_answer(
            question=f"q{index}",
            mode="exact",
            text=f"Accepted answer number {index} about coastal governance",
            citations=["zotero://fixture/1"],
            refused=False,
            reason="",
        )
    texts = corpus.recent_accepted_texts(3)
    assert len(texts) == 3
    assert texts[0].endswith("1 about coastal governance")
    assert texts[-1].endswith("3 about coastal governance")
    corpus.put_card(
        ClaimCard(
            id="card-open",
            claim="Synthetic claim for tests. Not a real job.",
            citations=["fixture://note-1"],
            source="fixture",
            status=STATUS_PENDING,
        )
    )
    corpus.approve("card-open")
    assert len(corpus.recent_accepted_texts(3)) == 3


def test_lens_filter_uses_the_header() -> None:
    delivered = Record(
        id="d",
        source="slack",
        uri="slack://delivered",
        title="Ocean chapter",
        text="Lens: delivered\nKind: chapter\nDrafted the ocean chapter.",
    )
    skills = Record(
        id="s",
        source="slack",
        uri="slack://skills",
        title="Ocean chapter",
        text="Lens: skills\nKind: teaching\nTaught the ocean chapter.",
    )
    hits = retrieve([delivered, skills], "ocean chapter", lens="delivered")
    assert [hit.uri for hit in hits] == ["slack://delivered"]
    by_kind = retrieve([delivered, skills], "ocean chapter", kind="teaching")
    assert [hit.uri for hit in by_kind] == ["slack://skills"]


def test_lexicon_expands_a_lens_word() -> None:
    tokens = expand_tokens("what skills show up", None)
    assert "teaching" in tokens
    assert expand_tokens("what skills show up", ()) == ["skills", "show"]


def test_toml_defaults_and_env_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    (tmp_path / "dossier.toml").write_text(
        '[ask]\nmode = "exact"\nlimit = 3\n',
        encoding="utf-8",
    )
    cfg = Config.from_env()
    assert cfg.ask_mode == "exact"
    assert cfg.ask_limit == 3
    monkeypatch.setenv("DOSSIER_ASK_MODE", "rich")
    assert Config.from_env().ask_mode == "rich"


def test_brief_writes_under_the_data_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(_coastal())
    corpus.close()
    pack = tmp_path / "pack.json"
    pack.write_text(
        json.dumps([{"id": "coast", "question": "coastal governance paper"}]),
        encoding="utf-8",
    )
    assert main(["brief", "--pack", str(pack), "--mode", "exact"]) == 0
    briefs = list((tmp_path / "briefs").glob("*.md"))
    assert len(briefs) == 1
    text = briefs[0].read_text(encoding="utf-8")
    assert "citations: zotero://fixture/1" in text
    assert "coastal governance" in text


def test_run_does_not_approve(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    monkeypatch.setenv("DATA_DUMPS_WAREHOUSE", str(tmp_path / "missing.duckdb"))
    monkeypatch.setenv("DOSSIER_APPLICATIONS", str(tmp_path / "not-applications"))
    monkeypatch.setenv("DOSSIER_CURSOR_PROJECTS", str(tmp_path / "no-cursor"))
    monkeypatch.setenv("DOSSIER_GROK_BLOBS", str(tmp_path / "no-grok"))
    monkeypatch.setenv("DOSSIER_MAIL_ROOT", str(tmp_path / "no-mail"))
    monkeypatch.setattr("dossier.sources.pubs.HttpPubsRetriever.ping", lambda self: False)
    approved: list[str] = []

    def _refuse_approve(self, card_id: str):
        approved.append(card_id)
        raise AssertionError("approve called")

    monkeypatch.setattr(Corpus, "approve", _refuse_approve)
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(
        Record(
            id="pos",
            source="linkedin",
            uri="linkedin://positions/0",
            title="Analyst at Oceans",
            text="Analyst at Oceans. Paris. Worked on coastal governance.",
            table="linkedin.positions",
        )
    )
    corpus.close()
    assert main(["run", "--mode", "exact"]) == 0
    assert approved == []
    again = Corpus(tmp_path / "evidence.db")
    pending = again.cards("pending")
    again.close()
    assert any(card.claim == "Analyst at Oceans" for card in pending)
    assert list((tmp_path / "briefs").glob("*.md"))


def test_empty_fts_does_not_fall_back_to_overlap() -> None:
    hits = retrieve([_coastal()], "coastal governance", fts_rank={})
    assert hits == []


def test_fts_outside_filter_falls_back_to_overlap() -> None:
    delivered = Record(
        id="d",
        source="mbox",
        uri="mbox://delivered",
        title="Ocean chapter",
        text="Lens: delivered\nKind: chapter\nI deliver the ocean chapter for the work report.",
    )
    outsider = Record(
        id="x",
        source="employer",
        uri="file://employer/transcript",
        title="Team notes",
        text="Lens: skills\nKind: workshop\nLong work notes about deliverables.",
    )
    fts = {outsider.uri: -10.0, delivered.uri: -1.0}
    # Global FTS prefers the outsider; lens keeps only delivered → use overlap.
    hits = retrieve(
        [delivered, outsider],
        "What work did I deliver?",
        lens="delivered",
        fts_rank=fts,
    )
    assert [hit.uri for hit in hits] == [delivered.uri]
    # When FTS hits exist only outside the filter, still keep overlap.
    outside_only = {outsider.uri: -10.0}
    again = retrieve(
        [delivered, outsider],
        "What work did I deliver?",
        lens="delivered",
        fts_rank=outside_only,
    )
    assert [hit.uri for hit in again] == [delivered.uri]


def test_narrow_source_surfaces_without_token_overlap(corpus: Corpus) -> None:
    role = Record(
        id="li",
        source="linkedin",
        uri="linkedin://positions/0",
        title="Adjunct Professor at Sciences Po",
        text="Adjunct Professor at Sciences Po. Paris. Jan 2015",
        table="linkedin.positions",
    )
    # retrieve alone still refuses hollow token overlap
    assert retrieve([role], "What roles have I held?", source="linkedin") == []
    corpus.upsert_record(role)
    hits = ask_hits(
        corpus,
        "What roles have I held?",
        Config(ask_fts=False, ask_passages=False, ask_embed=False, lexicon=()),
        limit=5,
        source="linkedin",
    )
    assert [hit.uri for hit in hits] == [role.uri]
    assert hits[0].score == 0


def test_ask_hits_uses_empty_fts_result(corpus: Corpus) -> None:
    corpus.upsert_record(_coastal())
    corpus.search_fts = lambda match, limit: []  # type: ignore[method-assign]
    corpus.search_passages = lambda match, limit: []  # type: ignore[method-assign]
    hits = ask_hits(
        corpus,
        "coastal governance paper",
        Config(ask_fts=True, lexicon=()),
        limit=5,
    )
    assert hits == []
    overlap = ask_hits(
        corpus,
        "coastal governance paper",
        Config(ask_fts=False, lexicon=()),
        limit=5,
    )
    assert overlap[0].uri == "zotero://fixture/1"


def test_fts_ignores_uri_and_source(corpus: Corpus) -> None:
    corpus.upsert_record(
        Record(
            id="shop",
            source="slack",
            uri="slack://coastal",
            title="Shopping",
            text="Buy milk and eggs tomorrow.",
        )
    )
    if not corpus.fts_ok:
        pytest.skip("sqlite build has no fts5")
    assert corpus.search_fts('"coastal" OR "slack"', limit=5) == []
    found = corpus.search_fts('"milk"', limit=5)
    assert found is not None and found[0][0] == "slack://coastal"


def test_old_fts_schema_is_rebuilt(tmp_path: Path) -> None:
    probe = sqlite3.connect(":memory:")
    try:
        probe.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    except sqlite3.OperationalError:
        probe.close()
        pytest.skip("sqlite build has no fts5")
    probe.close()
    db = tmp_path / "evidence.db"
    first = Corpus(db)
    first.upsert_record(
        Record(
            id="shop",
            source="slack",
            uri="slack://coastal",
            title="Shopping",
            text="Buy milk and eggs tomorrow.",
        )
    )
    first.close()
    conn = sqlite3.connect(db)
    conn.execute("DROP TABLE records_fts")
    conn.execute(
        """
        CREATE VIRTUAL TABLE records_fts USING fts5(
            uri, source, title, text, tokenize='unicode61'
        )
        """
    )
    conn.execute(
        "INSERT INTO records_fts (uri, source, title, text) VALUES (?, ?, ?, ?)",
        ("slack://coastal", "slack", "Shopping", "Buy milk and eggs tomorrow."),
    )
    conn.commit()
    conn.close()
    again = Corpus(db)
    try:
        assert again.search_fts('"coastal"', limit=5) == []
        found = again.search_fts('"milk"', limit=5)
        assert found is not None and found[0][0] == "slack://coastal"
    finally:
        again.close()


def test_retrieve_caps_at_eight_hits() -> None:
    records = [
        Record(
            id=str(i),
            source="pubs",
            uri=f"zotero://fixture/{i}",
            title="Synthetic coastal paper",
            text="Glen wrote a synthetic paper on coastal governance.",
        )
        for i in range(12)
    ]
    hits = retrieve(records, "coastal governance", limit=50)
    assert len(hits) == 8


def test_education_and_publication_drafts_skip_the_model(corpus: Corpus) -> None:
    education = Record(
        id="edu",
        source="linkedin",
        uri="linkedin://education/0",
        title="MSc at Oceans",
        text="MSc at Oceans. 2011–2013. Coastal governance.",
        table="linkedin.education",
    )
    publication = Record(
        id="pub",
        source="linkedin",
        uri="https://example.invalid/paper",
        title="Coastal governance paper",
        text="Coastal governance paper. Ocean Press. 2020.",
        table="linkedin.publications",
    )
    corpus.upsert_record(education)
    corpus.upsert_record(publication)
    cards = extract_corpus(corpus, _Boom(), "fake", use_llm=True)
    by_uri = {card.citations[0]: card for card in cards}
    assert by_uri[education.uri].claim == "MSc at Oceans"
    assert by_uri[publication.uri].claim == "Coastal governance paper"
    assert all(card.status == STATUS_PENDING for card in cards)


def test_draft_falls_back_to_a_body_line(corpus: Corpus) -> None:
    record = Record(
        id="pos",
        source="linkedin",
        uri="linkedin://positions/1",
        title="Hidden heading",
        text="Analyst at Oceans. Paris.",
        table="linkedin.positions",
    )
    corpus.upsert_record(record)
    cards = extract_corpus(corpus, _Boom(), "fake", use_llm=True)
    assert cards[0].claim == "Analyst at Oceans. Paris."


def test_auto_calls_once_when_no_sentence_carries_the_question() -> None:
    record = Record(
        id="split",
        source="pubs",
        uri="zotero://fixture/split",
        title="Notes",
        text=(
            "Glen drafted the notes.\n"
            "The workshop met in March.\n"
            "A separate paper covered fish.\n"
            "Editing happened the next week.\n"
            "Methods sat in an appendix."
        ),
    )
    question = "drafted workshop paper editing methods"
    hits = retrieve([record], question)
    assert len(hits) == 1
    exact = respond(question, hits, _Boom(), "fake", mode="exact")
    assert exact.refused
    client = _Once()
    result = respond(question, hits, client, "fake", mode="auto")
    assert client.calls == 1
    assert result.refused


def test_run_allowlist_skips_unknown_adapters(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    monkeypatch.setenv("DOSSIER_RUN_ADAPTERS", "not-an-adapter")
    monkeypatch.setenv("DATA_DUMPS_WAREHOUSE", str(tmp_path / "missing.duckdb"))
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(
        Record(
            id="pos",
            source="linkedin",
            uri="linkedin://positions/0",
            title="Analyst at Oceans",
            text="Analyst at Oceans. Paris.",
            table="linkedin.positions",
        )
    )
    corpus.close()
    assert main(["run", "--mode", "exact"]) == 0
    out = capsys.readouterr().out
    assert "skip not-an-adapter: unknown adapter" in out
    again = Corpus(tmp_path / "evidence.db")
    try:
        assert any(card.claim == "Analyst at Oceans" for card in again.cards("pending"))
    finally:
        again.close()
