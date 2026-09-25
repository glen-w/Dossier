import pytest

from dossier.ask import Hit
from dossier.cards import STATUS_APPROVED, ClaimCard
from dossier.cli import main
from dossier.embed import index_passages
from dossier.interview import conduct
from dossier.show import gap_report
from dossier.store import Corpus, Record


class _Pair:
    model = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        out: list[list[float]] = []
        for text in texts:
            low = text.lower()
            if "zephyr" in low or "coastal governance briefing" in low:
                out.append([1.0, 0.0])
            else:
                out.append([0.0, 1.0])
        return out


def _cfg():
    from dossier.config import Config

    return Config(ask_fts=False, ask_embed=True, llm_max_calls=6, ask_hops=1)


def test_vector_neighbor_quotes_a_span_without_shared_tokens(corpus: Corpus) -> None:
    corpus.upsert_record(
        Record(
            id="r1",
            source="employer",
            uri="file://employer/note.md",
            title="note",
            text="Drafted the coastal governance briefing for Oceana.",
        )
    )
    index_passages(corpus, _Pair())
    asker = _Pair()
    result = conduct(
        corpus,
        "zephyr quilting handbook",
        _cfg(),
        _Boom(),
        mode="exact",
        limit=5,
        embedder=asker,
    )
    assert not result.refused
    assert "coastal governance briefing" in result.text
    assert result.citations == ["file://employer/note.md"]
    assert asker.calls == 1


def test_medium_cosine_neighbor_still_refuses(corpus: Corpus) -> None:
    class _Mid:
        model = "fake"

        def embed(self, texts: list[str]) -> list[list[float]]:
            out: list[list[float]] = []
            for text in texts:
                if "zephyr" in text.lower():
                    out.append([1.0, 0.0])
                else:
                    out.append([1.0, 1.0])
            return out

    corpus.upsert_record(
        Record(
            id="r1",
            source="employer",
            uri="file://employer/note.md",
            title="note",
            text="Drafted the coastal governance briefing for Oceana.",
        )
    )
    index_passages(corpus, _Mid())
    result = conduct(
        corpus,
        "zephyr quilting handbook",
        _cfg(),
        _Boom(),
        mode="exact",
        limit=5,
        embedder=_Mid(),
    )
    assert result.refused
    assert result.reason == "no direct span"


def test_index_drops_vectors_from_another_model(corpus: Corpus) -> None:
    class _Other:
        model = "other"

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.0, 1.0] for _ in texts]

    corpus.upsert_record(
        Record(
            id="r1",
            source="employer",
            uri="file://employer/note.md",
            title="note",
            text="Drafted the coastal governance briefing for Oceana.",
        )
    )
    index_passages(corpus, _Pair())
    assert corpus.vector_count("fake") >= 1
    index_passages(corpus, _Other())
    assert corpus.vector_count("fake") == 0
    assert corpus.vector_count("other") >= 1


def test_index_skips_when_the_provider_is_off(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    assert main(["index"]) == 0
    assert "index: skipped (provider off)" in capsys.readouterr().out


def test_cli_gaps_prints_targets_and_does_not_approve(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(
        Record(
            id="r1",
            source="slack",
            uri="slack://1",
            title="note",
            text="Lens: delivered\nKind: chapter\nDrafted the ocean chapter for the report.",
        )
    )
    corpus.close()
    assert main(["gaps"]) == 0
    out = capsys.readouterr().out
    assert "hint skills: ingest meetings or slack" in out
    assert "extract slack://1" in out
    corpus = Corpus(tmp_path / "evidence.db")
    try:
        assert corpus.cards(STATUS_APPROVED) == []
    finally:
        corpus.close()


def test_orthogonal_question_still_refuses(corpus: Corpus) -> None:
    corpus.upsert_record(
        Record(
            id="r1",
            source="employer",
            uri="file://employer/note.md",
            title="note",
            text="Drafted the coastal governance briefing for Oceana.",
        )
    )
    index_passages(corpus, _Pair())
    result = conduct(
        corpus,
        "parking ticket dispute",
        _cfg(),
        _Boom(),
        mode="exact",
        limit=5,
        embedder=_Pair(),
    )
    assert result.refused


def test_pubs_hits_quote_without_writing_the_corpus(corpus: Corpus) -> None:
    result = conduct(
        corpus,
        "synthetic paper on coastal governance",
        _cfg(),
        _Boom(),
        mode="exact",
        limit=5,
        extra_hits=[
            Hit(
                uri="zotero://stub/1",
                title="Stub",
                text="Quinn wrote a synthetic paper on coastal governance.",
                score=1,
            )
        ],
    )
    assert not result.refused
    assert result.citations == ["zotero://stub/1"]
    assert corpus.records() == []


def test_gaps_name_ingest_and_extract_targets(corpus: Corpus) -> None:
    corpus.upsert_record(
        Record(
            id="r1",
            source="slack",
            uri="slack://1",
            title="note",
            text="Lens: delivered\nKind: chapter\nDrafted the ocean chapter for the report.",
        )
    )
    corpus.upsert_record(
        Record(
            id="r2",
            source="slack",
            uri="slack://2",
            title="waiting",
            text="Lens: delivered\nKind: report\nNo card yet for this briefing.",
        )
    )
    corpus.put_card(
        ClaimCard(
            id="bare",
            claim="Drafted the ocean chapter",
            citations=["slack://1"],
            source="slack",
            status=STATUS_APPROVED,
            record_id="r1",
        )
    )
    report = gap_report(corpus)
    assert ("skills", "ingest meetings or slack") in report.hints
    assert report.unspanned_approved[0].id == "bare"
    assert "slack://2" in report.extract_targets
    assert "slack://1" not in report.extract_targets


class _Boom:
    provider = "boom"

    def check_config(self, model: str) -> tuple[bool, str]:
        return True, "ok"

    def complete(self, request) -> str:
        raise AssertionError("model should not be called")

    def complete_json(self, request) -> dict:
        raise AssertionError("model should not be called")
