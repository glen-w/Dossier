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


def test_cli_ask_refuses_when_nothing_matches(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(
        Record(
            id="r1",
            source="chatgpt",
            uri="chatgpt://c/m",
            title="Shopping",
            text="Buy milk and eggs.",
        )
    )
    corpus.close()
    code = main(["ask", "lunar base command"])
    out = capsys.readouterr().out
    assert code == 1
    assert "no matching records" in out


def test_cli_ask_prints_egress_before_model(tmp_path: Path, monkeypatch, capsys) -> None:
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
            title="Synthetic coastal paper",
            text="Glen wrote a synthetic paper on coastal governance.",
        )
    )
    corpus.close()
    code = main(["ask", "--mode", "rich", "coastal governance paper"])
    err = capsys.readouterr().err
    assert "leave this machine" in err
    assert code == 2


def test_cli_ingest_slack_synthetic_warehouse(tmp_path: Path, monkeypatch) -> None:
    import duckdb

    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path / "data"))
    db = tmp_path / "catalog.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute("CREATE SCHEMA slack")
    conn.execute("CREATE TABLE slack.channels (channel_id VARCHAR, name VARCHAR, kind VARCHAR)")
    conn.execute(
        """
        CREATE TABLE slack.messages (
            channel_id VARCHAR, ts VARCHAR, channel_name VARCHAR, user_id VARCHAR,
            user_name VARCHAR, text VARCHAR, year BIGINT, text_len BIGINT,
            n_files BIGINT, reply_count BIGINT, n_reactions BIGINT, is_bot BOOLEAN,
            is_thread_root BOOLEAN, is_reply BOOLEAN, thread_ts VARCHAR
        )
        """
    )
    long_text = "Glen drafted a coastal governance briefing. " * 12
    conn.execute("INSERT INTO slack.channels VALUES ('C1', 'policy', 'channel')")
    conn.execute(
        """
        INSERT INTO slack.messages VALUES
        ('C1', '1.0', 'policy', 'U05E73N5733', 'Glen', ?, 2023, ?, 0, 0, 0,
         FALSE, FALSE, FALSE, NULL)
        """,
        [long_text, len(long_text)],
    )
    conn.close()
    assert main(["ingest", "--adapter", "slack", str(db)]) == 0
    corpus = Corpus(tmp_path / "data" / "evidence.db")
    recs = corpus.records("slack")
    corpus.close()
    assert recs
    assert recs[0].uri.startswith("slack://")
