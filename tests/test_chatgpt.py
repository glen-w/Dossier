from pathlib import Path

import duckdb

from dossier.sources.chatgpt import ChatGPTSource
from dossier.store import Corpus


def _warehouse(path: Path) -> Path:
    db = path / "catalog.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute("CREATE SCHEMA chatgpt")
    conn.execute(
        """
        CREATE TABLE chatgpt.conversations (
            conversation_id VARCHAR,
            title VARCHAR
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE chatgpt.messages (
            conversation_id VARCHAR,
            message_id VARCHAR,
            role VARCHAR,
            text VARCHAR,
            ts_utc TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO chatgpt.conversations VALUES ('c1', 'Oceana briefing')"
    )
    conn.execute(
        """
        INSERT INTO chatgpt.messages VALUES
        ('c1', 'm1', 'user',
         'Help me write up that I drafted a coastal governance briefing for Oceana in 2023.',
         '2023-06-01 12:00:00'),
        ('c1', 'm2', 'assistant', 'ok', '2023-06-01 12:00:01')
        """
    )
    conn.close()
    return db


def test_chatgpt_reads_warehouse_messages(tmp_path: Path, corpus: Corpus) -> None:
    db = _warehouse(tmp_path)
    src = ChatGPTSource()
    assert src.detect(db)
    src.load(db, corpus)
    recs = corpus.records("chatgpt")
    assert len(recs) == 1
    assert recs[0].title == "Oceana briefing"
    assert "coastal governance briefing" in recs[0].text
    assert recs[0].uri.startswith("chatgpt://c1/")
