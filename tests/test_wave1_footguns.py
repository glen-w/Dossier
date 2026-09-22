from pathlib import Path

from dossier.cli import main
from dossier.identity import is_sent_metadata_uri, mbox_folder_from_uri
from dossier.paths import TomlConfigError, read_toml_dict
from dossier.store import Corpus, Record
from dossier.util import record_id


def test_read_toml_dict_rejects_bad_toml(tmp_path: Path) -> None:
    path = tmp_path / "dossier.toml"
    path.write_text("[[broken\n", encoding="utf-8")
    try:
        read_toml_dict(path)
        raise AssertionError("expected TomlConfigError")
    except TomlConfigError as exc:
        assert "invalid TOML" in str(exc)


def test_read_toml_dict_missing_is_empty(tmp_path: Path) -> None:
    assert read_toml_dict(tmp_path / "nope.toml") == {}


def test_mbox_sent_metadata_uri() -> None:
    assert mbox_folder_from_uri("mbox://acct/Sent Mail/42") == "Sent Mail"
    assert is_sent_metadata_uri("mbox://acct/Sent Mail/42")
    assert is_sent_metadata_uri("mbox://export/Inbox/9")
    assert not is_sent_metadata_uri("mbox://acct/Projects/42")


def test_doctor_warns_empty_identity_and_sent_metadata(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.delenv("DOSSIER_SLACK_USER_IDS", raising=False)
    monkeypatch.delenv("DOSSIER_SPEAKER_NAMES", raising=False)
    db = tmp_path / "evidence.db"
    corpus = Corpus(db)
    try:
        corpus.upsert_record(
            Record(
                id=record_id("mbox://a/Sent Mail/1"),
                source="mbox",
                uri="mbox://a/Sent Mail/1",
                title="draft attached",
                text="Subject only",
                table="mbox.messages",
            )
        )
    finally:
        corpus.close()

    class _Fake:
        name = "slack"

        def detect(self, path: Path) -> bool:
            return True

    class _Item:
        name = "slack"
        source = _Fake()

    monkeypatch.setattr(
        "dossier.cli.CONTRIBUTIONS",
        [_Item()],
    )
    monkeypatch.setattr("dossier.cli._default_path", lambda name: tmp_path)
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "mbox_sent_metadata: 1" in out
    assert "warn: slack detected but identity empty" in out


def test_doctor_fails_on_bad_toml(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    (tmp_path / "dossier.toml").write_text("[[broken\n", encoding="utf-8")
    assert main(["doctor"]) == 2
    assert "FAIL:" in capsys.readouterr().err
