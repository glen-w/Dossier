from pathlib import Path

from dossier.cards import STATUS_APPROVED, STATUS_PENDING, ClaimCard
from dossier.cli import main
from dossier.store import Corpus, Record


def test_approve_pending_card(corpus: Corpus) -> None:
    corpus.put_card(
        ClaimCard(
            id="abc123",
            claim="Synthetic claim for tests. Not a real job.",
            citations=["fixture://note-1"],
            source="fixture",
            status=STATUS_PENDING,
        )
    )
    approved = corpus.approve("abc123")
    assert approved.status == STATUS_APPROVED


def test_cli_ingest_buffet_approve(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    apps = tmp_path / "job applications"
    apps.mkdir()
    (apps / "cover.md").write_text(
        "Cover letter. Glen led the Oceana BBNJ working group.\n",
        encoding="utf-8",
    )
    assert main(["ingest", "--adapter", "applications", str(apps)]) == 0
    corpus = Corpus(tmp_path / "evidence.db")
    recs = corpus.records("applications")
    assert recs
    corpus.put_card(
        ClaimCard(
            id="card1",
            claim="Led the Oceana BBNJ working group",
            citations=[recs[0].uri],
            source="applications",
            status=STATUS_PENDING,
            record_id=recs[0].id,
        )
    )
    corpus.close()
    assert main(["buffet", "--status", "pending"]) == 0
    assert main(["approve", "card1"]) == 0
    assert main(["buffet", "--status", "approved"]) == 0


def test_cli_extract_prints_egress_and_needs_llm(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "litellm")
    monkeypatch.setenv("DOSSIER_LLM_API_BASE", "https://example.invalid/v1")

    class Blocked:
        provider = "litellm"

        def check_config(self, model: str) -> tuple[bool, str]:
            return False, "blocked for test"

    monkeypatch.setattr("dossier.cli.get_client", lambda cfg: Blocked())
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(
        Record(
            id="r1",
            source="pubs",
            uri="zotero://fixture/1",
            title="Synthetic",
            text="Glen wrote a synthetic paper on coastal governance.",
        )
    )
    corpus.close()
    code = main(["extract"])
    err = capsys.readouterr().err
    assert "leave this machine" in err
    assert "blocked for test" in err
    assert code == 2
