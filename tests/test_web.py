"""Workbench TestClient coverage (needs the [web] extra)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from dossier.cards import STATUS_APPROVED, ClaimCard, STATUS_PENDING, card_id
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


def test_checkbox_sets_offer_select_all_and_clear(client) -> None:
    test_client, _ = client
    for path in ("/ask", "/match", "/brief", "/settings", "/settings/lists"):
        page = test_client.get(path)
        assert page.status_code == 200
        html = page.text
        sets = html.count('class="checks"')
        assert sets >= 1
        assert html.count('data-checks="all"') == sets
        assert html.count('data-checks="none"') == sets


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


def test_review_defend_and_result_pages(client) -> None:
    test_client, root = client
    sentence = "Drafted the coastal governance workshop briefing for the ministry."
    cid = card_id(sentence, ["file://employer/note"])
    corpus = Corpus(root / "evidence.db")
    try:
        corpus.upsert_record(
            Record(
                id="emp",
                source="employer",
                uri="file://employer/note",
                title="briefing",
                text=sentence,
            )
        )
        corpus.put_card(
            ClaimCard(
                id=cid,
                claim=sentence,
                citations=["file://employer/note"],
                source="employer",
                status=STATUS_PENDING,
            )
        )
    finally:
        corpus.close()

    page = test_client.get("/review?status=pending")
    assert page.status_code == 200
    assert b"carrying sentence" in page.content
    assert b"Defend" in page.content

    resp = test_client.post(
        "/review/act",
        data={"action": "defend", "ids": cid, "status": "pending"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    corpus = Corpus(root / "evidence.db")
    try:
        card = corpus.get_card(cid)
        assert card is not None
        assert card.status == STATUS_PENDING
        assert card.extras["span"] == sentence
        corpus.approve(cid)
    finally:
        corpus.close()

    for path in ("/gaps", "/packet", "/tailor", "/locker"):
        assert test_client.get(path).status_code == 200

    locker = test_client.get("/locker")
    assert b"Match a job spec" in locker.content or b"Index passages" in locker.content
    assert b"use the CLI" not in locker.content

    resp = test_client.post("/packet/run", follow_redirects=True)
    assert resp.status_code == 200
    assert sentence.encode() in resp.content

    resp = test_client.post(
        "/tailor/run",
        data={"posting": "- experience drafting a coastal governance workshop briefing\n", "kind": "cv"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    location = resp.headers["location"]
    page = test_client.get(location)
    for _ in range(40):
        if sentence.encode() in page.content:
            break
        time.sleep(0.05)
        page = test_client.get(location)
    assert sentence.encode() in page.content


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
    page = test_client.get(f"/brief?job={job_id}")
    assert page.status_code == 200
    assert b"What did I deliver?" in page.content

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


def test_brief_viewer_shows_newest_and_rejects_other_paths(client) -> None:
    test_client, root = client
    empty = test_client.get("/brief")
    assert b"No briefs in data/briefs yet." in empty.content

    briefs = root / "briefs"
    briefs.mkdir()
    (briefs / "notes.md").write_text("NOT-A-STAMP", encoding="utf-8")
    (root / "secret.md").write_text("SECRET-TOKEN", encoding="utf-8")
    (briefs / "260101-000000.md").write_text(
        "prompts: ask=none\n# Dossier brief\n\n## one\n\nWhat did I deliver?\n\nAn older report.\nmode: exact\n",
        encoding="utf-8",
    )
    (briefs / "260923-120000.md").write_text(
        "# Dossier brief\n\n## two\n\nWhat did I publish?\n\nA <script>alert(1)</script> paper.\ncitations: rec-1\n",
        encoding="utf-8",
    )

    page = test_client.get("/brief")
    assert b"What did I publish?" in page.content
    assert b"An older report." not in page.content
    assert b"NOT-A-STAMP" not in page.content
    assert b"<script>alert" not in page.content
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in page.content
    assert b'<p class="meta">citations: rec-1</p>' in page.content

    older = test_client.get("/brief?file=260101-000000")
    assert b"What did I deliver?" in older.content
    assert b"An older report." in older.content
    assert b'<p class="meta">prompts: ask=none</p>' in older.content
    assert b"<h2>Dossier brief</h2>" in older.content
    assert b'<p class="meta">mode: exact</p>' in older.content
    assert b"An older report.\nmode:" not in older.content

    sneaky = test_client.get("/brief?file=../secret")
    assert sneaky.status_code == 200
    assert b"SECRET-TOKEN" not in sneaky.content
    assert b"No brief with that name." in sneaky.content
    assert b"What did I publish?" not in sneaky.content


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


def test_err_query_uses_blurb(client) -> None:
    test_client, _ = client
    resp = test_client.get("/ask?err=empty")
    assert resp.status_code == 200
    assert b"non-empty question" in resp.content
    assert b"err=empty" not in resp.content


def test_settings_subnav_on_lists(client) -> None:
    test_client, _ = client
    resp = test_client.get("/settings/lists")
    assert resp.status_code == 200
    assert b'href="/settings/prompts"' in resp.content
    assert b'href="/settings/packs"' in resp.content


def test_job_strip_idle_skips_htmx_poll(client) -> None:
    test_client, _ = client
    resp = test_client.get("/locker")
    assert resp.status_code == 200
    assert b"hx-trigger" not in resp.content


def test_sources_shows_ingest_summary_after_job(client, monkeypatch) -> None:
    test_client, root = client
    apps = root / "job applications"
    apps.mkdir()
    (apps / "note.md").write_text("Glen led a coastal workshop.\n", encoding="utf-8")
    monkeypatch.setenv("DOSSIER_APPLICATIONS", str(apps))
    resp = test_client.post(
        "/sources/ingest",
        data={"adapter": "applications"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "job=" in resp.headers["location"]
    job_id = resp.headers["location"].split("job=")[-1]
    deadline = __import__("time").time() + 10
    job = RUNNER.get(job_id)
    assert job is not None
    while job.status not in {"done", "error"} and __import__("time").time() < deadline:
        __import__("time").sleep(0.05)
    assert job.status == "done", job.error
    page = test_client.get(f"/sources?job={job_id}")
    assert page.status_code == 200
    assert b"Ingest finished" in page.content
    assert b"records" in page.content


def test_ask_surfaces_job_error(client, monkeypatch) -> None:
    test_client, _ = client

    def boom(job):  # noqa: ANN001
        raise RuntimeError("synthetic ask failure")

    monkeypatch.setattr(
        "dossier.web.app._start_ask",
        lambda *a, **k: RUNNER.start("ask", boom),
    )
    resp = test_client.post(
        "/ask/run",
        data={"question": "coastal governance"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    job_id = resp.headers["location"].split("job=")[-1]
    deadline = __import__("time").time() + 10
    job = RUNNER.get(job_id)
    assert job is not None
    while job.status not in {"done", "error"} and __import__("time").time() < deadline:
        __import__("time").sleep(0.05)
    assert job.status == "error"
    page = test_client.get(f"/ask?job={job_id}")
    assert page.status_code == 200
    assert b"synthetic ask failure" in page.content


def test_workbench_refuses_a_non_loopback_client(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    app = create_app()
    with TestClient(app, client=("192.0.2.1", 50000)) as remote:
        resp = remote.get("/locker")
    assert resp.status_code == 403
    assert resp.text == "loopback only"


def test_locker_rooms_and_next_step(client) -> None:
    test_client, _ = client
    page = test_client.get("/locker")
    assert page.status_code == 200
    html = page.text
    assert "Prepare" in html
    assert "Decide" in html
    assert "Use" in html
    for path in (
        "/locker",
        "/sources",
        "/extract",
        "/review",
        "/ask",
        "/match",
        "/tailor",
        "/packet",
        "/gaps",
        "/index",
        "/brief",
        "/run",
        "/settings",
    ):
        assert f'href="{path}"' in html
    assert 'href="/sources"' in html
    assert "Continue" in html
    assert "Detected" in html


def test_review_queue_advances_and_defend_keeps_status(client) -> None:
    test_client, root = client
    first = "Delivered a coastal governance workshop"
    second = "Built fisheries data tables for the annual report."
    corpus = Corpus(root / "evidence.db")
    try:
        corpus.upsert_record(
            Record(
                id="note",
                source="employer",
                uri="file://employer/note",
                title="note",
                text=second,
            )
        )
        corpus.put_card(
            ClaimCard(
                id=card_id(first, ["fixture://one"]),
                claim=first,
                citations=["fixture://one"],
                source="applications",
                status=STATUS_PENDING,
            )
        )
        held = card_id(second, ["file://employer/note"])
        corpus.put_card(
            ClaimCard(
                id=held,
                claim=second,
                citations=["file://employer/note"],
                source="employer",
                status=STATUS_PENDING,
            )
        )
    finally:
        corpus.close()

    weird = test_client.get("/review?view=nope")
    assert weird.status_code == 200
    assert b"coastal governance" in weird.content
    assert b"fisheries data tables" in weird.content
    assert b"1 of" not in weird.content

    queue = test_client.get("/review?view=queue&status=pending")
    assert b"1 of 2" in queue.content
    assert b'class="chip"' in queue.content
    assert b'data-key="a"' in queue.content
    assert b'data-key="r"' in queue.content
    assert b'data-key="d"' in queue.content
    assert b'data-key="k"' in queue.content
    assert b"coastal governance" in queue.content
    assert b"fisheries data tables" not in queue.content
    plain = test_client.get("/review?status=pending")
    assert b"Approve matching" not in plain.content
    sourced = test_client.get("/review?status=pending&source=applications")
    assert b"Approve matching" in sourced.content

    resp = test_client.post(
        "/review/act",
        data={
            "action": "approve",
            "ids": card_id(first, ["fixture://one"]),
            "status": "pending",
            "view": "queue",
            "offset": "0",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "view=queue" in resp.headers["location"]
    assert "offset=0" in resp.headers["location"]
    nxt = test_client.get(resp.headers["location"])
    assert b"fisheries data tables" in nxt.content
    assert b"coastal governance" not in nxt.content

    resp = test_client.post(
        "/review/act",
        data={
            "action": "defend",
            "ids": held,
            "status": "pending",
            "view": "queue",
            "offset": "0",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "noted=span" in resp.headers["location"]
    assert "offset=1" in resp.headers["location"]
    corpus = Corpus(root / "evidence.db")
    try:
        card = corpus.get_card(held)
        assert card is not None
        assert card.status == STATUS_PENDING
        assert card.extras["span"] == second
    finally:
        corpus.close()
    stored = test_client.get(resp.headers["location"])
    assert b"Status is unchanged" in stored.content
    assert b"No cards left in this queue." in stored.content

    bare = "Approved a claim with no stored span."
    corpus = Corpus(root / "evidence.db")
    try:
        corpus.put_card(
            ClaimCard(
                id=card_id(bare, ["fixture://bare"]),
                claim=bare,
                citations=["fixture://bare"],
                source="applications",
                status=STATUS_APPROVED,
            )
        )
    finally:
        corpus.close()
    gaps = test_client.get("/gaps")
    assert b"view=queue" in gaps.content
    assert bare.encode() in gaps.content


def test_match_rail_and_tailor_prefill(client) -> None:
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
    finally:
        corpus.close()

    spec = "- Experience leading ocean workshops\n- Knowledge of fisheries data tables\n"
    resp = test_client.post("/match/run", data={"spec": spec}, follow_redirects=False)
    location = resp.headers["location"]
    job_id = location.split("job=", 1)[1]
    job = RUNNER.get(job_id)
    assert job is not None
    deadline = time.time() + 5
    while job.status not in {"done", "error"} and time.time() < deadline:
        time.sleep(0.02)
    assert job.status == "done", job.error
    page = test_client.get(location)
    assert b"1 with a quote" in page.content
    assert b"1 gaps" in page.content
    assert b'class="rail"' in page.content
    assert b"rail-item met" in page.content
    assert b"rail-item gap" in page.content
    assert b"data-copy=" in page.content
    assert b'action="/tailor/run"' not in page.content
    assert spec.splitlines()[0].lstrip("- ").encode() in page.content
    assert f"/tailor?from={job_id}".encode() in page.content

    tailor = test_client.get(f"/tailor?from={job_id}")
    assert b"Experience leading ocean workshops" in tailor.content
    empty = test_client.get("/tailor?from=not-a-match")
    assert b"Experience leading ocean workshops" not in empty.content


def test_ask_refusal_keeps_the_next_link(client) -> None:
    test_client, _ = client
    resp = test_client.post(
        "/ask/run",
        data={"question": "What coastal workshop did I deliver?"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    location = resp.headers["location"]
    job_id = location.split("job=", 1)[1]
    job = RUNNER.get(job_id)
    assert job is not None
    deadline = time.time() + 5
    while job.status not in {"done", "error"} and time.time() < deadline:
        time.sleep(0.02)
    assert job.status == "done", job.error
    page = test_client.get(location)
    assert b"Refused" in page.content
    assert b"What coastal workshop did I deliver?" in page.content
    assert any(
        token in page.content
        for token in (b'href="/sources"', b'href="/index"', b'href="/extract"', b'href="/review"', b'href="/ask"')
    )


def test_review_hides_actions_while_the_locker_is_busy(client) -> None:
    import threading

    test_client, root = client
    corpus = Corpus(root / "evidence.db")
    try:
        corpus.put_card(
            ClaimCard(
                id=card_id("Delivered a coastal workshop", ["fixture://one"]),
                claim="Delivered a coastal workshop",
                citations=["fixture://one"],
                source="applications",
                status=STATUS_PENDING,
            )
        )
    finally:
        corpus.close()
    started = threading.Event()
    release = threading.Event()

    def work(job):  # noqa: ANN001
        started.set()
        release.wait(2)
        return {"ok": 1}

    job = RUNNER.start("demo", work)
    try:
        assert started.wait(2)
        page = test_client.get("/review?view=queue&status=pending")
        assert b"Delivered a coastal workshop" in page.content
        assert b">Approve<" not in page.content
        assert b">Defend<" not in page.content
    finally:
        release.set()
        deadline = time.time() + 2
        while job.status not in {"done", "error"} and time.time() < deadline:
            time.sleep(0.02)


def test_ask_kept_answer_is_a_citation_card(client) -> None:
    test_client, root = client
    sentence = "Led the ocean workshops for the coastal team."
    corpus = Corpus(root / "evidence.db")
    try:
        corpus.upsert_record(
            Record(
                id="ocean",
                source="slack",
                uri="slack://ocean",
                title="Ocean workshop",
                text=sentence,
            )
        )
    finally:
        corpus.close()
    resp = test_client.post(
        "/ask/run",
        data={"question": sentence, "mode": "exact"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    location = resp.headers["location"]
    job = RUNNER.get(location.split("job=", 1)[1])
    assert job is not None
    deadline = time.time() + 5
    while job.status not in {"done", "error"} and time.time() < deadline:
        time.sleep(0.02)
    assert job.status == "done", job.error
    page = test_client.get(location)
    assert b'id="ask-sentence"' in page.content
    assert b'data-copy="ask-sentence"' in page.content
    assert sentence.encode() in page.content
    assert b"slack://ocean" in page.content
    assert b"Refused" not in page.content


def test_gui_cli_missing_extra_message(monkeypatch) -> None:
    """Without fastapi installed path is covered by importorskip elsewhere;
    here we only check the argparse entry exists."""
    from dossier.cli import main

    # Port out of range should fail before import of heavy deps if host invalid…
    # Invalid host is checked inside web main after import.
    code = main(["gui", "--host", "0.0.0.0", "--port", "8766"])
    assert code == 2
