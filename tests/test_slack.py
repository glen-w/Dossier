from pathlib import Path

import duckdb

from dossier.sources.slack import SlackSource
from dossier.store import Corpus


def _warehouse(path: Path) -> Path:
    db = path / "catalog.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute("CREATE SCHEMA slack")
    conn.execute(
        """
        CREATE TABLE slack.channels (
            channel_id VARCHAR,
            name VARCHAR,
            kind VARCHAR
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE slack.messages (
            channel_id VARCHAR,
            ts VARCHAR,
            channel_name VARCHAR,
            user_id VARCHAR,
            user_name VARCHAR,
            text VARCHAR,
            year BIGINT,
            text_len BIGINT,
            n_files BIGINT,
            reply_count BIGINT,
            n_reactions BIGINT,
            is_bot BOOLEAN,
            is_thread_root BOOLEAN,
            is_reply BOOLEAN,
            thread_ts VARCHAR
        )
        """
    )
    conn.execute("INSERT INTO slack.channels VALUES ('C1', 'policy', 'channel')")
    long_text = "Glen drafted a coastal governance briefing. " * 12
    conn.execute(
        """
        INSERT INTO slack.messages VALUES
        ('C1', '1.0', 'policy', 'UTESTSLACK', 'Glen', ?, 2023, ?, 0, 0, 0,
         FALSE, FALSE, FALSE, NULL),
        ('C1', '2.0', 'policy', 'UOTHER', 'Other', ?, 2023, ?, 0, 0, 0,
         FALSE, FALSE, FALSE, NULL)
        """,
        [long_text, len(long_text), "Buy milk and eggs only.", 22],
    )
    conn.close()
    return db


def test_slack_keeps_a_long_message_from_the_known_user(
    tmp_path: Path, corpus: Corpus, monkeypatch
) -> None:
    monkeypatch.setenv("DOSSIER_SLACK_USER_IDS", "UTESTSLACK")
    db = _warehouse(tmp_path)
    src = SlackSource()
    assert src.detect(db)
    src.load(db, corpus)
    recs = corpus.records("slack")
    assert len(recs) == 1
    assert recs[0].uri == "slack://C1/1.0"
    assert "coastal governance briefing" in recs[0].text
    assert "milk" not in recs[0].text


def test_slack_keeps_glen_file_and_skips_unrelated(
    tmp_path: Path, corpus: Corpus, monkeypatch
) -> None:
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
    conn.execute(
        """
        CREATE TABLE slack.files (
            channel_id VARCHAR, ts VARCHAR, file_id VARCHAR, name VARCHAR, filetype VARCHAR
        )
        """
    )
    conn.execute(
        "INSERT INTO slack.channels VALUES ('COCEAN', 'gsr_section_ocean', 'channel')"
    )
    conn.execute(
        """
        INSERT INTO slack.messages VALUES
        ('COCEAN', '1.0', 'gsr_section_ocean', 'UTESTSLACK', 'Glen',
         'Draft of the GSR ocean chapter attached.', 2024, 40, 1, 1, 2,
         FALSE, TRUE, FALSE, '1.0'),
        ('COCEAN', '9.0', 'gsr_section_ocean', 'UOTHER', 'Other',
         'Random chat about lunch.', 2024, 24, 0, 0, 0,
         FALSE, FALSE, FALSE, NULL)
        """
    )
    conn.execute(
        "INSERT INTO slack.files VALUES ('COCEAN', '1.0', 'F1', 'gsr-ocean-chapter.docx', 'docx')"
    )
    conn.close()
    src = SlackSource()
    src.load(db, corpus)
    recs = corpus.records("slack")
    uris = {r.uri for r in recs}
    assert "slack://COCEAN/1.0" in uris
    assert "slack://COCEAN/9.0" not in uris
    ocean = next(r for r in recs if r.uri.endswith("/1.0"))
    assert "gsr-ocean-chapter.docx" in ocean.text
    assert "chapter" in ocean.text.lower() or "report" in ocean.text.lower()
