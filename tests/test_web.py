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


def test_gui_cli_missing_extra_message(monkeypatch) -> None:
    """Without fastapi installed path is covered by importorskip elsewhere;
    here we only check the argparse entry exists."""
    from dossier.cli import main

    # Port out of range should fail before import of heavy deps if host invalid…
    # Invalid host is checked inside web main after import.
    code = main(["gui", "--host", "0.0.0.0", "--port", "8766"])
    assert code == 2
