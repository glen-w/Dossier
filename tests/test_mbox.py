from pathlib import Path

from dossier.sources.mbox import MboxSource
from dossier.store import Corpus

_MBOX = """From synthetic@example.test Mon Sep 21 12:00:00 2026
From: Synthetic <synthetic@example.test>
Subject: Please find the draft briefing
Date: Mon, 21 Sep 2026 12:00:00 +0000
Message-ID: <fixture-1@example.test>

Glen drafted a coastal governance briefing for the synthetic pack.
"""


def test_small_activity_folder_is_ingested(tmp_path: Path, corpus: Corpus) -> None:
    folder = tmp_path / "export"
    folder.mkdir()
    (folder / "BBNJ policy").write_text(_MBOX, encoding="utf-8")
    src = MboxSource()
    assert src.detect(folder)
    src.load(folder, corpus)
    recs = corpus.records("mbox")
    assert len(recs) == 1
    assert "coastal governance briefing" in recs[0].text
    assert recs[0].uri.startswith("mbox://export/BBNJ policy/")


def test_sent_mail_folder_is_skipped(tmp_path: Path, corpus: Corpus) -> None:
    folder = tmp_path / "export"
    folder.mkdir()
    (folder / "Sent Mail").write_text(_MBOX, encoding="utf-8")
    src = MboxSource()
    src.load(folder, corpus)
    assert corpus.records("mbox") == []


def test_iddri_tree_is_not_parsed(tmp_path: Path, corpus: Corpus, monkeypatch) -> None:
    root = tmp_path / "iddri"
    root.mkdir()
    (root / "INBOX").write_text("", encoding="utf-8")
    (root / "BBNJ policy").write_text(_MBOX, encoding="utf-8")
    monkeypatch.setattr(
        "dossier.sources.mbox.warehouse_db",
        lambda: tmp_path / "missing.duckdb",
    )
    src = MboxSource()
    assert src.detect(root)
    src.load(root, corpus)
    assert corpus.records("mbox") == []


def test_gloda_warehouse_skips_noise_and_does_not_open_sent_mail(
    tmp_path: Path, corpus: Corpus, monkeypatch
) -> None:
    import duckdb
    from dossier.fetch.mbox import fetch_mbox_body

    mail = tmp_path / "email"
    teaching = mail / "iddri" / "Teaching"
    teaching.parent.mkdir(parents=True)
    teaching.write_text(_MBOX.replace("BBNJ", "Teaching").replace("fixture-1", "teach-1"), encoding="utf-8")
    sent = mail / "iddri" / "[Gmail].sbd" / "Sent Mail"
    sent.parent.mkdir(parents=True)
    sent.write_text("From ignored\n\nshould not be parsed\n", encoding="utf-8")
    monkeypatch.setenv("DOSSIER_MAIL_ROOT", str(mail))
    monkeypatch.setenv("DOSSIER_MAIL_ACCOUNTS", "person@example.test:iddri")

    db = tmp_path / "catalog.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute("CREATE SCHEMA thunderbird")
    conn.execute(
        "CREATE TABLE thunderbird.folders (folder_id INTEGER, name VARCHAR, account_key VARCHAR)"
    )
    conn.execute(
        """
        CREATE TABLE thunderbird.messages (
            gloda_id INTEGER, folder_id INTEGER, header_message_id VARCHAR,
            subject VARCHAR, attachment_names VARCHAR, has_attachment BOOLEAN,
            direction VARCHAR, from_name VARCHAR, year INTEGER,
            starred BOOLEAN, replied BOOLEAN
        )
        """
    )
    conn.execute(
        "CREATE TABLE thunderbird.signals (message_id INTEGER, kind VARCHAR)"
    )
    conn.execute(
        """
        INSERT INTO thunderbird.folders VALUES
        (1, 'Teaching', 'person@example.test'),
        (2, 'Newsletters', 'person@example.test'),
        (3, 'Sent Mail', 'person@example.test')
        """
    )
    conn.execute(
        """
        INSERT INTO thunderbird.messages VALUES
        (10, 1, '<teach-1@example.test>',
         'Lecture slides for the ocean governance course',
         'lecture-slides.pdf', TRUE, 'sent', 'Glen Wright', 2024, FALSE, FALSE),
        (12, 2, '<news-1@example.test>',
         'IDDRI newsletter', 'digest.pdf', TRUE, 'sent', 'Glen Wright', 2024, FALSE, FALSE),
        (13, 3, '<sent-1@example.test>',
         'BBNJ fisheries brief attached', 'bbnj-brief.pdf', TRUE, 'sent',
         'Glen Wright', 2024, FALSE, FALSE)
        """
    )
    conn.close()
    src = MboxSource()
    assert src.detect(db)
    src.load(db, corpus)
    recs = corpus.records("mbox")
    uris = " ".join(r.uri for r in recs)
    assert "teach-1@example.test" in uris
    assert "news-1@example.test" not in uris
    sent_rec = next(r for r in recs if "sent-1@example.test" in r.uri)
    assert "should not be parsed" not in sent_rec.text
    assert "bbnj-brief.pdf" in sent_rec.text
    assert fetch_mbox_body(
        mail,
        account_key="person@example.test",
        folder_name="Sent Mail",
        header_message_id="<sent-1@example.test>",
    ) == ""


def test_oversize_mbox_is_not_opened(tmp_path: Path, monkeypatch) -> None:
    from dossier.fetch.mbox import fetch_mbox_body

    mail = tmp_path / "email"
    path = mail / "iddri" / "Teaching"
    path.parent.mkdir(parents=True)
    path.write_text(_MBOX, encoding="utf-8")
    monkeypatch.setenv("DOSSIER_MBOX_MAX_BYTES", "1")
    monkeypatch.setenv("DOSSIER_MAIL_ACCOUNTS", "person@example.test:iddri")
    body = fetch_mbox_body(
        mail,
        account_key="person@example.test",
        folder_name="Teaching",
        header_message_id="<fixture-1@example.test>",
        max_bytes=1,
    )
    assert body == ""
