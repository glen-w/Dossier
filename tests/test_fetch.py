from pathlib import Path

import duckdb

from dossier.fetch.mbox import fetch_mbox_body
from dossier.fetch.slack import fetch_slack_body
from dossier.seekers.hits import Hit


def test_fetch_mbox_does_not_expose_folder_walker() -> None:
    import dossier.fetch.mbox as mbox_fetch

    assert not hasattr(mbox_fetch, "parse_mbox_folder")


def test_iter_mbox_files_skips_blocked_iddri_tree(tmp_path: Path) -> None:
    from dossier.fetch.mbox import build_mbox_index, iter_mbox_files

    mail = tmp_path / "email"
    gmail = mail / "gmail"
    gmail.mkdir(parents=True)
    (gmail / "Teaching").write_text("From: a\nSubject: gmail\n\nok\n", encoding="utf-8")
    iddri = mail / "iddri"
    iddri.mkdir()
    (iddri / "INBOX").write_text("From: a\nSubject: inbox\n\nno\n", encoding="utf-8")
    deep = iddri / "Teaching"
    deep.write_text("From: a\nSubject: deep\n\nno\n", encoding="utf-8")

    paths = [p.name for p, _ in iter_mbox_files(mail)]
    assert "Teaching" in paths
    assert "INBOX" not in paths
    assert "deep" not in paths
    index = build_mbox_index(mail)
    assert ("gmail", "Teaching") in index
    assert not any(key[0].lower() == "iddri" for key in index)


def test_slack_fetch_includes_thread_root(tmp_path: Path) -> None:
    db = tmp_path / "catalog.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute("CREATE SCHEMA slack")
    conn.execute(
        """
        CREATE TABLE slack.messages (
            channel_id VARCHAR, ts VARCHAR, user_id VARCHAR, user_name VARCHAR,
            text VARCHAR, thread_ts VARCHAR, is_thread_root BOOLEAN, is_reply BOOLEAN
        )
        """
    )
    conn.execute(
        """
        INSERT INTO slack.messages VALUES
        ('C1', '1.0', 'U05E73N5733', 'Glen', 'Root: ocean chapter plan', '1.0', TRUE, FALSE),
        ('C1', '1.1', 'U05E73N5733', 'Glen', 'Reply with the draft notes', '1.0', FALSE, TRUE)
        """
    )
    hit = Hit(
        source="slack",
        uri="slack://C1/1.1",
        title="reply",
        preview="Reply with the draft notes",
        year=2024,
        org="REN21",
        kind="chapter",
        lenses=("delivered",),
        primary_lens="delivered",
        artifacts=(),
        people=("Glen",),
        skills=(),
        score=20,
        hunts=("t",),
        fetch_body=True,
        channel_id="C1",
        ts="1.1",
    )
    body = fetch_slack_body(conn, hit, ["U05E73N5733"])
    conn.close()
    assert "Reply with the draft notes" in body
    assert "ocean chapter plan" in body


def test_one_message_fetch_by_id(tmp_path: Path) -> None:
    mail = tmp_path / "email" / "iddri"
    mail.mkdir(parents=True)
    (mail / "Teaching").write_text(
        "From synthetic@example.test Mon Sep 21 12:00:00 2026\n"
        "From: Synthetic <synthetic@example.test>\n"
        "Subject: hi\n"
        "Date: Mon, 21 Sep 2026 12:00:00 +0000\n"
        "Message-ID: <one@test>\n"
        "\n"
        "Taught a course.\n",
        encoding="utf-8",
    )
    body = fetch_mbox_body(
        mail.parent,
        account_key="glen.wright@sciencespo.fr",
        folder_name="Teaching",
        header_message_id="<one@test>",
    )
    assert "Taught a course" in body
