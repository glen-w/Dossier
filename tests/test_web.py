"""Workbench TestClient coverage (needs the [web] extra)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dossier.cards import ClaimCard, STATUS_PENDING, card_id
from dossier.store import Corpus, Record

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from dossier.jobs import RUNNER
from dossier.web.app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client, tmp_path


def test_locker_page(client) -> None:
    test_client, _ = client
    resp = test_client.get("/locker")
    assert resp.status_code == 200
    assert b"Locker" in resp.content
    assert b"records" in resp.content
    assert b"/static/logo.png" in resp.content
    assert b'alt="Dossier"' in resp.content


def test_settings_save_and_profile(client) -> None:
    test_client, root = client
    resp = test_client.post(
        "/settings/save",
        data={
            "effort": "light",
            "model": "qwen2.5:3b",
            "max_calls": "3",
            "ask_mode": "exact",
            "extract_llm": "off",
            "ask_planner": "off",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    toml = (root / "dossier.toml").read_text(encoding="utf-8")
    assert 'effort = "light"' in toml
    assert "qwen2.5:3b" in toml

    resp = test_client.post(
        "/settings/profile/save",
        data={"name": "quick", "description": "wave1"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert (root / "profiles" / "quick.json").is_file()

    resp = test_client.post(
        "/settings/profile/activate",
        data={"name": "default"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert 'effort = "balanced"' in (root / "dossier.toml").read_text(encoding="utf-8")


def test_phrase_lists_round_trip_into_the_seek(client, monkeypatch) -> None:
    test_client, root = client
    for name in (
        "DOSSIER_MAIL_EXCLUDE",
        "DOSSIER_MAIL_EXCLUDE_OFF",
        "DOSSIER_MAIL_KEEP",
        "DOSSIER_MAIL_KEEP_OFF",
    ):
        monkeypatch.delenv(name, raising=False)
    (root / "dossier.toml").write_text(
        '[identity]\nslack_user_ids = ["UEXAMPLE"]\n',
        encoding="utf-8",
    )
    page = test_client.get("/settings/lists")
    assert page.status_code == 200
    assert b"Drop folders" in page.content
    assert b"newsletter" in page.content
    assert b"Phrase lists" in test_client.get("/settings").content
    assert b"Phrase lists" in test_client.get("/sources").content

    ons = []
    for line in page.text.split("name=\"on\""):
        if "value=\"" not in line:
            continue
        value = line.split("value=\"", 1)[1].split("\"", 1)[0]
        if value.startswith("mail|exclude|newsletter"):
            continue
        ons.append(value)
    resp = test_client.post(
        "/settings/lists",
        data={"on": ons, "extra_mail_exclude": "promo\n"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    toml = (root / "dossier.toml").read_text(encoding="utf-8")
    assert "UEXAMPLE" in toml

    from dossier.identity import noise_folder
    from dossier.lists import mail_exclude, mail_keep

    assert "promo" in mail_exclude()
    assert "newsletter" not in mail_exclude()
    assert "admin" in mail_keep()
    assert noise_folder("Promo")
    assert not noise_folder("Newsletters")
    assert not noise_folder("Admin")


def test_review_approve(client) -> None:
    test_client, root = client
    corpus = Corpus(root / "evidence.db")
    try:
        claim = "Delivered a coastal governance workshop"
        cid = card_id(claim, ["fixture://one"])
        corpus.put_card(
            ClaimCard(
                id=cid,
                claim=claim,
                citations=["fixture://one"],
                source="applications",
                status=STATUS_PENDING,
            )
        )
    finally:
        corpus.close()

    resp = test_client.get("/review?status=pending")
    assert resp.status_code == 200
    assert b"coastal governance" in resp.content

    resp = test_client.post(
        "/review/act",
        data={"action": "approve", "ids": cid, "status": "pending"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    corpus = Corpus(root / "evidence.db")
    try:
        cards = corpus.cards("approved")
        assert any(card.id == cid for card in cards)
    finally:
        corpus.close()


def test_job_sse_fake(client) -> None:
    test_client, _ = client

    def work(job):  # noqa: ANN001
        from dossier.ui import note, stage

        stage("demo", "one step")
        note("halfway")
        return {"ok": 1}

    job = RUNNER.start("demo", work)
    deadline = __import__("time").time() + 2
    while job.status not in {"done", "error"} and __import__("time").time() < deadline:
        __import__("time").sleep(0.02)
    assert job.status == "done"

    resp = test_client.get(f"/api/jobs/{job.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["job"]["status"] == "done"

    # Collect a few SSE frames then stop.
    with test_client.stream("GET", f"/api/jobs/{job.id}/events") as stream:
        chunks = []
        for line in stream.iter_lines():
            if line.startswith("data:"):
                chunks.append(json.loads(line.removeprefix("data:").strip()))
            if any(c.get("kind") == "eof" for c in chunks):
                break
            if len(chunks) > 20:
                break
    assert chunks
    assert any(c.get("kind") in {"stage", "note", "status", "eof"} for c in chunks)


def test_pack_brief_and_prompt_override(client) -> None:
    import time

    test_client, root = client
    body = '[{"id": "one", "question": "What did I deliver?"}]'
    resp = test_client.post(
        "/settings/packs/save",
        data={"name": "short", "body": body},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert (root / "packs" / "short.json").is_file()

    resp = test_client.post(
        "/brief/run",
        data={"pack": "short", "posting": "", "mode": "exact"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    job_id = resp.headers["location"].split("job=")[-1]
    deadline = time.time() + 3
    status = ""
    while time.time() < deadline:
        payload = test_client.get(f"/api/jobs/{job_id}").json()["job"]
        status = payload["status"]
        if status in {"done", "error"}:
            break
        time.sleep(0.02)
    assert status == "done"
    briefs = list((root / "briefs").glob("*.md"))
    assert briefs
    text = briefs[0].read_text(encoding="utf-8")
    assert text.startswith("prompts: ask=none")

    resp = test_client.post("/index/run", follow_redirects=False)
    assert resp.status_code == 303
    job_id = resp.headers["location"].split("job=")[-1]
    deadline = time.time() + 3
    while time.time() < deadline:
        payload = test_client.get(f"/api/jobs/{job_id}").json()["job"]
        if payload["status"] in {"done", "error"}:
            assert payload["status"] == "done"
            page = test_client.get(f"/index?job={job_id}")
            assert page.status_code == 200
            assert b"Skipped: provider off" in page.content
            break
        time.sleep(0.02)

    resp = test_client.post(
        "/settings/prompts/override",
        data={
            "prompt_id": "ask",
            "system_prompt": "Short.",
            "user_template": "@@QUESTION@@",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert (root / "prompts" / "overrides" / "ask.json").is_file()
    resp = test_client.post(
        "/settings/prompts/restore",
        data={"prompt_id": "ask"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert not (root / "prompts" / "overrides" / "ask.json").is_file()


def test_phrase_lists_page_saves_a_change(client) -> None:
    from dossier.lists import PHRASE_LISTS

    test_client, root = client
    page = test_client.get("/settings/lists")
    assert page.status_code == 200
    assert b"Drop folders" in page.content
    assert b"newsletter" in page.content

    data = {
        "on": [
            f"{spec.section}|{spec.key}|{phrase}"
            for spec in PHRASE_LISTS
            for phrase in spec.default
            if not (spec.section == "mail" and spec.key == "exclude" and phrase == "receipt")
        ],
        "extra_mail_exclude": "promo",
    }
    resp = test_client.post("/settings/lists", data=data, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/settings/lists?saved=1")
    saved = test_client.get("/settings/lists?saved=1")
    assert b"Saved" in saved.content
    toml = (root / "dossier.toml").read_text(encoding="utf-8")
    assert "receipt" in toml
    assert "promo" in toml


def test_match_refuses_while_the_locker_is_busy(client) -> None:
    import threading

    test_client, _ = client
    started = threading.Event()
    release = threading.Event()

    def work(job):  # noqa: ANN001
        started.set()
        release.wait(2)
        return {"ok": 1}

    job = RUNNER.start("demo", work)
    try:
        assert started.wait(2)
        resp = test_client.post(
            "/match/run",
            data={"spec": "- Experience leading ocean workshops"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "err=busy" in resp.headers["location"]
    finally:
        release.set()
        deadline = __import__("time").time() + 2
        while job.status not in {"done", "error"} and __import__("time").time() < deadline:
            __import__("time").sleep(0.02)


def test_match_page_honours_checked_sources(client) -> None:
    test_client, root = client
    corpus = Corpus(root / "evidence.db")
    try:
        corpus.upsert_record(
            Record(
                id="ocean",
                source="slack",
                uri="slack://ocean",
                title="Ocean workshop",
                text="Led the ocean workshops for the coastal team.",
            )
        )
        corpus.upsert_record(
            Record(
                id="tables",
                source="employer",
                uri="employer://tables",
                title="Fisheries tables",
                text="Led the ocean workshops for the harbour office.",
            )
        )
    finally:
        corpus.close()

    resp = test_client.post(
        "/match/run",
        data={
            "spec": "- Experience leading ocean workshops",
            "scope_form": "1",
            "sources": ["slack"],
            "year_from": "",
            "year_to": "",
            "effort": "light",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    job_id = resp.headers["location"].split("job=", 1)[1]
    job = RUNNER.get(job_id)
    assert job is not None
    deadline = __import__("time").time() + 5
    while job.status not in {"done", "error"} and __import__("time").time() < deadline:
        __import__("time").sleep(0.02)
    assert job.status == "done", job.error
    page = test_client.get(resp.headers["location"])
    assert b"slack://ocean" in page.content
    assert b"employer://tables" not in page.content
    assert b"sources slack" in page.content
    assert b"effort light" in page.content


def test_settings_saves_scope_defaults(client) -> None:
    test_client, root = client
    resp = test_client.get("/settings")
    assert b"Year from" in resp.content
    assert b"slack" in resp.content
    resp = test_client.post(
        "/settings/save",
        data={
            "effort": "balanced",
            "model": "qwen2.5:3b",
            "max_calls": "0",
            "ask_mode": "auto",
            "extract_llm": "off",
            "ask_planner": "off",
            "scope_form": "1",
            "sources": ["slack", "pubs"],
            "year_from": "2018",
            "year_to": "2022",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    toml = (root / "dossier.toml").read_text(encoding="utf-8")
    assert "year_from = 2018" in toml
    assert "slack" in toml
    assert "pubs" in toml


def test_match_rejects_a_bad_year(client) -> None:
    test_client, _ = client
    resp = test_client.post(
        "/match/run",
        data={
            "spec": "- Experience leading ocean workshops",
            "scope_form": "1",
            "sources": ["slack"],
            "year_from": "12",
            "year_to": "",
            "effort": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "year" in resp.headers["location"]


def test_match_page_lists_both_requirements(client) -> None:
    test_client, root = client
    corpus = Corpus(root / "evidence.db")
    try:
        corpus.upsert_record(
            Record(
                id="ocean",
                source="slack",
                uri="slack://ocean",
                title="Ocean workshop",
                text="Led the ocean workshops for the coastal team.",
            )
        )
        corpus.upsert_record(
            Record(
                id="tables",
                source="employer",
                uri="employer://tables",
                title="Fisheries tables",
                text="Built fisheries data tables for the annual report.",
            )
        )
    finally:
        corpus.close()

    spec = (
        "- Experience leading ocean workshops\n"
        "- Knowledge of fisheries data tables\n"
    )
    resp = test_client.post("/match/run", data={"spec": spec}, follow_redirects=False)
    assert resp.status_code == 303
    location = resp.headers["location"]
    job_id = location.split("job=", 1)[1]
    job = RUNNER.get(job_id)
    assert job is not None
    deadline = __import__("time").time() + 5
    while job.status not in {"done", "error"} and __import__("time").time() < deadline:
        __import__("time").sleep(0.02)
    assert job.status == "done", job.error

    page = test_client.get(location)
    assert page.status_code == 200
    assert b"Experience leading ocean workshops" in page.content
    assert b"Knowledge of fisheries data tables" in page.content
    assert b"slack://ocean" in page.content
    assert b"employer://tables" in page.content
    assert b"Led the ocean workshops" in page.content


def test_workbench_refuses_a_non_loopback_client(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    app = create_app()
    with TestClient(app, client=("192.0.2.1", 50000)) as remote:
        resp = remote.get("/locker")
    assert resp.status_code == 403
    assert resp.text == "loopback only"


def test_gui_cli_missing_extra_message(monkeypatch) -> None:
    """Without fastapi installed path is covered by importorskip elsewhere;
    here we only check the argparse entry exists."""
    from dossier.cli import main

    # Port out of range should fail before import of heavy deps if host invalid…
    # Invalid host is checked inside web main after import.
    code = main(["gui", "--host", "0.0.0.0", "--port", "8766"])
    assert code == 2
