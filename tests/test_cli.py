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
        "Cover letter. Quinn led the Oceana BBNJ working group.\n",
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


def test_cli_approve_all_skips_excluded_sources(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    corpus = Corpus(tmp_path / "evidence.db")
    for card_id, source in (("keep", "employer"), ("chat", "chatgpt"), ("git", "git")):
        corpus.put_card(
            ClaimCard(
                id=card_id,
                claim=f"Synthetic claim {card_id}. Not a real job.",
                citations=["fixture://note-1"],
                source=source,
                status=STATUS_PENDING,
            )
        )
    corpus.put_card(
        ClaimCard(
            id="already",
            claim="Synthetic refused claim. Not a real job.",
            citations=["fixture://note-1"],
            source="employer",
            status="refused",
            reason="no citations",
        )
    )
    corpus.close()
    assert main(["approve"]) == 2
    assert main(["approve", "--all", "--except", "chatgpt,git"]) == 0
    out = capsys.readouterr().out
    assert "employer  1 pending" in out
    assert "approved 1" in out
    corpus = Corpus(tmp_path / "evidence.db")
    assert corpus.get_card("keep").status == STATUS_APPROVED
    assert corpus.get_card("chat").status == STATUS_PENDING
    assert corpus.get_card("git").status == STATUS_PENDING
    assert corpus.get_card("already").status == "refused"
    corpus.close()
    assert main(["refuse", "chat"]) == 0
    corpus = Corpus(tmp_path / "evidence.db")
    assert corpus.get_card("chat").status == "refused"
    corpus.close()
    assert main(["reopen", "--all", "--source", "missing,employer"]) == 0
    again = capsys.readouterr()
    assert "no cards for missing" in again.err
    assert "reopened 2" in again.out
    corpus = Corpus(tmp_path / "evidence.db")
    assert corpus.get_card("keep").status == STATUS_PENDING
    assert corpus.get_card("already").status == STATUS_PENDING
    assert corpus.get_card("chat").status == "refused"
    corpus.close()


def test_cli_bulk_gate_rejects_a_mixed_id_and_an_overlap(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    corpus = Corpus(tmp_path / "evidence.db")
    for card_id, source in (("emp", "employer"), ("chat", "chatgpt")):
        corpus.put_card(
            ClaimCard(
                id=card_id,
                claim=f"Synthetic claim {card_id}. Not a real job.",
                citations=["fixture://note-1"],
                source=source,
                status=STATUS_PENDING,
            )
        )
    corpus.close()
    assert main(["approve", "emp", "--all"]) == 2
    assert "not both" in capsys.readouterr().err
    assert main(["refuse", "--all", "--source", "employer", "--except", "employer"]) == 0
    overlap = capsys.readouterr()
    assert "listed in --source and --except: employer" in overlap.err
    assert "no pending cards" in overlap.out
    assert main(["refuse", "--all", "--except", "chatgpt"]) == 0
    refused = capsys.readouterr().out
    assert "employer  1 pending" in refused
    assert "refused 1" in refused
    corpus = Corpus(tmp_path / "evidence.db")
    assert corpus.get_card("emp").status == "refused"
    assert corpus.get_card("chat").status == STATUS_PENDING
    corpus.close()
    assert main(["review", "--port", "0"]) == 2
    assert "port must be" in capsys.readouterr().err


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
            text="Quinn wrote a synthetic paper on coastal governance.",
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
            text="Quinn wrote a synthetic paper on coastal governance.",
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
    monkeypatch.setenv("DOSSIER_SLACK_USER_IDS", "UTESTSLACK")
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
    long_text = "Quinn drafted a coastal governance briefing. " * 12
    conn.execute("INSERT INTO slack.channels VALUES ('C1', 'policy', 'channel')")
    conn.execute(
        """
        INSERT INTO slack.messages VALUES
        ('C1', '1.0', 'policy', 'UTESTSLACK', 'Quinn', ?, 2023, ?, 0, 0, 0,
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
