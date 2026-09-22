import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from dossier.cards import STATUS_PENDING
from dossier.extract import extract_corpus
from dossier.llm.client import NullLLMClient
from dossier.paths import employer_paths, git_paths, git_user, pubs_collection, pubs_seed, pubs_top_k
from dossier.sources.chatgpt import ChatGPTSource
from dossier.sources.employer import EmployerSource
from dossier.sources.git import GitSource
from dossier.sources.mbox import MboxSource
from dossier.sources.slack import SlackSource
from dossier.store import Corpus

_MBOX = """From synthetic@example.test Mon Sep 21 12:00:00 2026
From: Synthetic <synthetic@example.test>
Subject: Please find the draft briefing
Date: Mon, 21 Sep 2026 12:00:00 +0000
Message-ID: <fixture-{n}@example.test>

Glen drafted a coastal governance briefing for the synthetic pack.
"""

_EXPORT = [
    {
        "title": "Oceana briefing",
        "id": "c1",
        "mapping": {
            "a": {
                "message": {
                    "id": "m1",
                    "author": {"role": "user"},
                    "content": {
                        "parts": [
                            "Help me write up that I drafted a coastal governance briefing for Oceana in 2023."
                        ]
                    },
                }
            },
            "b": {
                "message": {
                    "id": "m2",
                    "author": {"role": "assistant"},
                    "content": {"parts": ["ok"]},
                }
            },
        },
    }
]


def test_employer_allowlist_loads_text_and_skips_pdf(
    tmp_path: Path, corpus: Corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "Oceana"
    folder.mkdir()
    (folder / "note.md").write_text(
        "Drafted the coastal governance briefing for Oceana.\n",
        encoding="utf-8",
    )
    (folder / "cv.pdf").write_bytes(b"%PDF-fake")
    monkeypatch.setenv("DOSSIER_EMPLOYER_PATHS", str(folder))
    src = EmployerSource()
    assert src.detect(folder)
    assert not src.detect(tmp_path / "elsewhere")
    src.load(folder, corpus)
    recs = {rec.uri: rec for rec in corpus.records("employer")}
    assert "coastal governance briefing" in recs["file://employer/Oceana/note.md"].text
    assert "not ingested" in recs["file://employer/Oceana/cv.pdf"].text
    cards = extract_corpus(corpus, NullLLMClient(), "off", source="employer", use_llm=False)
    assert cards
    assert cards[0].status == STATUS_PENDING
    assert "coastal governance briefing" in cards[0].claim


def test_employer_load_reports_each_file(
    tmp_path: Path, corpus: Corpus, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "REN21"
    folder.mkdir()
    (folder / "note.md").write_text("Drafted the status report.\n", encoding="utf-8")
    (folder / "scan.pdf").write_bytes(b"%PDF-fake")
    monkeypatch.setenv("DOSSIER_EMPLOYER_PATHS", str(folder))
    EmployerSource().load(folder, corpus)
    err = capsys.readouterr().err
    assert "employer REN21" in err
    assert "stored=1" in err
    assert "inventory=1" in err
    assert "note.md" in err


def test_employer_paths_load_from_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "Oceana"
    folder.mkdir()
    monkeypatch.delenv("DOSSIER_EMPLOYER_PATHS", raising=False)
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    (tmp_path / "dossier.toml").write_text(
        f'[employer]\npaths = ["{folder}"]\n',
        encoding="utf-8",
    )
    assert EmployerSource().detect(folder)
    assert not EmployerSource().detect(tmp_path)


def test_chatgpt_export_folder(tmp_path: Path, corpus: Corpus) -> None:
    folder = tmp_path / "export"
    folder.mkdir()
    (folder / "conversations.json").write_text(json.dumps(_EXPORT), encoding="utf-8")
    src = ChatGPTSource()
    assert src.detect(folder)
    src.load(folder, corpus)
    assert corpus.records("chatgpt")[0].uri == "chatgpt://c1/m1"


def test_slack_export_matches_a_display_name(
    tmp_path: Path, corpus: Corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOSSIER_SLACK_USER_IDS", "Glen Wright")
    users = [{"id": "UTEST", "real_name": "Glen Wright", "profile": {"display_name": "glen"}}]
    messages = [
        {
            "type": "message",
            "user": "UTEST",
            "text": "Drafted the coastal governance briefing for the policy channel.",
            "ts": "1700000000.000100",
        }
    ]
    folder = tmp_path / "slack-export"
    folder.mkdir()
    (folder / "users.json").write_text(json.dumps(users), encoding="utf-8")
    channel = folder / "policy"
    channel.mkdir()
    (channel / "2024-01-01.json").write_text(json.dumps(messages), encoding="utf-8")
    SlackSource().load(folder, corpus)
    recs = corpus.records("slack")
    assert len(recs) == 1
    assert "coastal governance briefing" in recs[0].text


def test_documents_root_is_not_an_employer_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    docs = tmp_path / "Documents"
    docs.mkdir()
    (docs / "note.md").write_text("Drafted a private note.\n", encoding="utf-8")
    monkeypatch.setenv("DOSSIER_EMPLOYER_PATHS", str(docs))
    assert employer_paths() == ()
    assert not EmployerSource().detect(docs)


def test_chatgpt_export_zip_skips_short_replies(tmp_path: Path, corpus: Corpus) -> None:
    zpath = tmp_path / "chatgpt.zip"
    with zipfile.ZipFile(zpath, "w") as archive:
        archive.writestr("conversations.json", json.dumps(_EXPORT))
    src = ChatGPTSource()
    assert src.detect(zpath)
    src.load(zpath, corpus)
    recs = corpus.records("chatgpt")
    assert len(recs) == 1
    assert recs[0].title == "Oceana briefing"
    assert recs[0].uri == "chatgpt://c1/m1"
    assert "coastal governance briefing" in recs[0].text


def test_slack_export_keeps_named_user(
    tmp_path: Path, corpus: Corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOSSIER_SLACK_USER_IDS", "UTEST")
    users = [{"id": "UTEST", "real_name": "Glen Wright", "profile": {"display_name": "glen"}}]
    messages = [
        {
            "type": "message",
            "user": "UTEST",
            "text": "Drafted the coastal governance briefing for the policy channel.",
            "ts": "1700000000.000100",
        },
        {
            "type": "message",
            "user": "UOTHER",
            "text": "This other person wrote a long note that should stay out of the locker entirely.",
            "ts": "1700000001.000100",
        },
    ]
    zpath = tmp_path / "slack.zip"
    with zipfile.ZipFile(zpath, "w") as archive:
        archive.writestr("users.json", json.dumps(users))
        archive.writestr("policy/2024-01-01.json", json.dumps(messages))
    src = SlackSource()
    assert src.detect(zpath)
    src.load(zpath, corpus)
    recs = corpus.records("slack")
    assert len(recs) == 1
    assert "coastal governance briefing" in recs[0].text
    assert "other person" not in recs[0].text


def test_git_log_stores_subject_not_a_patch(
    tmp_path: Path, corpus: Corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("DOSSIER_GIT_USER", raising=False)
    repo = tmp_path / "sample"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    (repo / "notes.md").write_text("draft\n", encoding="utf-8")
    subprocess.run(["git", "add", "notes.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            "Drafted the coastal governance briefing for Oceana.",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    src = GitSource()
    assert src.detect(repo)
    assert not src.detect(tmp_path)
    src.load(repo, corpus)
    recs = corpus.records("git")
    assert len(recs) == 1
    assert recs[0].uri.startswith("git://sample/")
    assert "coastal governance briefing" in recs[0].text
    assert "Date: " in recs[0].text
    assert "notes.md" in recs[0].text
    assert "@@" not in recs[0].text


def test_git_user_keeps_matching_author_only(
    tmp_path: Path, corpus: Corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOSSIER_GIT_USER", "glen-w")
    repo = tmp_path / "sample"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    (repo / "notes.md").write_text("draft\n", encoding="utf-8")
    subprocess.run(["git", "add", "notes.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=other@example.com",
            "-c",
            "user.name=Other",
            "commit",
            "-m",
            "Unrelated note from another author.",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "notes.md").write_text("revision\n", encoding="utf-8")
    subprocess.run(["git", "add", "notes.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=glen-w@example.com",
            "-c",
            "user.name=Glen",
            "commit",
            "-m",
            "Drafted the coastal governance briefing for Oceana.",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    GitSource().load(repo, corpus)
    recs = corpus.records("git")
    assert len(recs) == 1
    assert "coastal governance briefing" in recs[0].text
    assert "another author" not in recs[0].text


def test_local_toml_names_git_author_and_pubs_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.delenv("DOSSIER_GIT_USER", raising=False)
    monkeypatch.delenv("DOSSIER_GIT_PATHS", raising=False)
    monkeypatch.delenv("DOSSIER_PUBS_SEED", raising=False)
    monkeypatch.delenv("DOSSIER_PUBS_TOP_K", raising=False)
    repo = tmp_path / "sample"
    (tmp_path / "dossier.toml").write_text(
        "\n".join(
            [
                "[git]",
                'user = "glen-w"',
                f'paths = ["{repo}"]',
                "",
                "[pubs]",
                'collection = "my pubs"',
                'seed = "my pubs"',
                "top_k = 353",
            ]
        ),
        encoding="utf-8",
    )
    assert git_user() == "glen-w"
    assert git_paths() == (repo,)
    assert pubs_collection() == "my pubs"
    assert pubs_seed() == "my pubs"
    assert pubs_top_k() == 353


def test_identity_is_empty_until_the_local_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dossier.identity import (
        configured_slack_user_ids,
        mail_account_map,
        resolve_speaker_names,
    )

    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.delenv("DOSSIER_SLACK_USER_IDS", raising=False)
    monkeypatch.delenv("DOSSIER_SPEAKER_NAMES", raising=False)
    monkeypatch.delenv("DOSSIER_MAIL_ACCOUNTS", raising=False)
    assert configured_slack_user_ids() == ()
    assert resolve_speaker_names() == ()
    assert mail_account_map() == {}
    (tmp_path / "dossier.toml").write_text(
        "\n".join(
            [
                "[identity]",
                'slack_user_ids = ["UEXAMPLE"]',
                'speaker_names = ["Case Speaker"]',
                "",
                "[identity.mail_accounts]",
                '"person@example.test" = "acct"',
            ]
        ),
        encoding="utf-8",
    )
    assert configured_slack_user_ids() == ("UEXAMPLE",)
    assert resolve_speaker_names() == ("Case Speaker",)
    assert mail_account_map() == {"person@example.test": "acct"}
    monkeypatch.setenv("DOSSIER_MAIL_ACCOUNTS", "other@example.test:other")
    assert mail_account_map()["other@example.test"] == "other"
    assert mail_account_map()["person@example.test"] == "acct"


def test_run_detects_every_listed_employer_and_git_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dossier.cli import _detected_targets

    first = tmp_path / "IDDRI"
    second = tmp_path / "teaching"
    first.mkdir()
    second.mkdir()
    repo = tmp_path / "sample"
    repo.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "init"], cwd=other, check=True, capture_output=True)
    monkeypatch.setenv("DOSSIER_EMPLOYER_PATHS", f"{first},{second}")
    monkeypatch.setenv("DOSSIER_GIT_PATHS", f"{repo},{other}")
    targets, skipped = _detected_targets(("employer", "git"))
    found = {(item.name, path) for item, path in targets}
    assert ("employer", first) in found
    assert ("employer", second) in found
    assert ("git", repo) in found
    assert ("git", other) in found
    assert skipped == []


def test_exported_mbox_stops_at_the_file_cap(
    tmp_path: Path, corpus: Corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOSSIER_MBOX_MAX_FILES", "1")
    folder = tmp_path / "export"
    folder.mkdir()
    (folder / "BBNJ policy").write_text(_MBOX.format(n=1), encoding="utf-8")
    (folder / "Ocean workshop").write_text(_MBOX.format(n=2), encoding="utf-8")
    MboxSource().load(folder, corpus)
    assert len(corpus.records("mbox")) == 1
