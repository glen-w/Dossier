"""Built-in include and exclude lists, plus toml and env edits."""

from pathlib import Path

import pytest

from dossier.identity import activity_folder, noise_folder
from dossier.lenses import is_noise_name


_LIST_ENV = (
    "DOSSIER_MAIL_EXCLUDE",
    "DOSSIER_MAIL_EXCLUDE_OFF",
    "DOSSIER_MAIL_KEEP",
    "DOSSIER_MAIL_KEEP_OFF",
    "DOSSIER_MAIL_ACTIVITY",
    "DOSSIER_MAIL_ACTIVITY_OFF",
    "DOSSIER_MAIL_SIGNALS",
    "DOSSIER_MAIL_SIGNALS_OFF",
    "DOSSIER_NAME_DROP",
    "DOSSIER_NAME_DROP_OFF",
    "DOSSIER_NAME_KEEP",
    "DOSSIER_NAME_KEEP_OFF",
    "DOSSIER_NAME_EXCLUDE",
    "DOSSIER_NAME_EXCLUDE_OFF",
    "DOSSIER_MAIL_CLOSED",
    "DOSSIER_MAIL_CLOSED_OFF",
    "DOSSIER_EMPLOYER_DIR_EXCLUDE",
    "DOSSIER_EMPLOYER_DIR_EXCLUDE_OFF",
    "DOSSIER_EMPLOYER_SUFFIX_EXCLUDE",
    "DOSSIER_EMPLOYER_SUFFIX_EXCLUDE_OFF",
    "DOSSIER_EMPLOYER_EXCLUDE",
    "DOSSIER_EMPLOYER_EXCLUDE_OFF",
    "DOSSIER_SLACK_EXCLUDE",
    "DOSSIER_SLACK_ACTIVITY",
    "DOSSIER_SLACK_ACTIVITY_OFF",
    "DOSSIER_MEETINGS_EXCLUDE",
    "DOSSIER_MEETINGS_EXCLUDE_OFF",
    "DOSSIER_GIT_EXCLUDE",
    "DOSSIER_CHATGPT_EXCLUDE",
    "DOSSIER_APPLICATIONS_DIR_EXCLUDE",
)


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    for name in _LIST_ENV:
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_defaults_drop_newsletters_and_keep_admin(isolated: Path) -> None:
    assert noise_folder("Newsletters")
    assert noise_folder("la vie de l\u2019iddri")
    assert noise_folder("google alerts")
    assert noise_folder("Trash")
    assert not noise_folder("Sent Mail")
    assert not activity_folder("facebook")
    assert activity_folder("IKI expert meeting")
    assert not activity_folder("wikipedia")
    assert not noise_folder("Admin")
    assert not noise_folder("Admin & receipts")
    assert not noise_folder("Ocean Finance")
    assert activity_folder("BBNJ policy")
    assert is_noise_name("Form frais for IKI/SHS.xlsx") is False
    assert is_noise_name("TimesheetTemplate_2020.xls") is True
    assert is_noise_name("registration form.pdf") is True


def test_toml_adds_and_turns_off_phrases(isolated: Path) -> None:
    (isolated / "dossier.toml").write_text(
        "\n".join(
            [
                "[mail]",
                'exclude = ["promo"]',
                'exclude_off = ["receipt"]',
                'activity_off = ["policy"]',
                "",
                "[names]",
                'keep = ["per diem"]',
                'drop_off = ["timesheet"]',
            ]
        ),
        encoding="utf-8",
    )
    assert noise_folder("Promo")
    assert noise_folder("Newsletters")
    assert not noise_folder("Receipts")
    assert not activity_folder("Marine Policy")
    assert activity_folder("Teaching")
    assert is_noise_name("TimesheetTemplate_2020.xls") is False
    assert is_noise_name("per diem form.pdf") is False
    assert is_noise_name("registration form.pdf") is True


def test_phrase_list_patch_turns_a_builtin_off_and_adds_one(isolated: Path) -> None:
    from dossier.lists import PHRASE_LISTS, phrase_list_patch
    from dossier.settings_io import save_common_settings

    checked = {
        (spec.section, spec.key, phrase)
        for spec in PHRASE_LISTS
        for phrase in spec.default
        if not (spec.section == "mail" and spec.key == "exclude" and phrase == "receipt")
    }
    extras = {(spec.section, spec.key): "" for spec in PHRASE_LISTS}
    extras[("mail", "exclude")] = "promo\n"
    save_common_settings(isolated / "dossier.toml", phrase_list_patch(checked, extras))
    assert not noise_folder("Receipts")
    assert noise_folder("Promo")
    assert noise_folder("Newsletters")


def test_source_lists_follow_the_same_edit(isolated: Path) -> None:
    from dossier.identity import skip_folder
    from dossier.lists import (
        employer_dirs,
        employer_slugs,
        employer_suffixes,
        excluded,
        meetings_dirs,
        phrase_blocked,
        slack_activity,
        slack_exclude,
    )
    from dossier.sources.employer_filter import _skip_dir, _skip_file

    assert _skip_file("shot.png", enabled=True)
    assert _skip_dir("cache", enabled=True)
    assert "admin" in employer_slugs()
    assert "metadata" in meetings_dirs()
    assert "gsr_" in slack_activity()
    assert skip_folder("Trash")
    assert skip_folder("Sent Mail")
    (isolated / "dossier.toml").write_text(
        "\n".join(
            [
                "[employer]",
                'suffix_exclude_off = [".png"]',
                'dir_exclude = ["scratch"]',
                'slug_exclude_off = ["admin"]',
                'exclude = ["scratch-notes"]',
                "",
                "[meetings]",
                'exclude = ["holding"]',
                'exclude_off = ["metadata"]',
                "",
                "[slack]",
                'exclude = ["random"]',
                'activity_off = ["policy"]',
                "",
                "[mail]",
                'closed_off = ["trash"]',
                "",
                "[git]",
                'exclude = ["wip"]',
                "",
                "[chatgpt]",
                'exclude = ["scratch chat"]',
            ]
        ),
        encoding="utf-8",
    )
    assert ".png" not in employer_suffixes()
    assert "scratch" in employer_dirs()
    assert _skip_dir(".git", enabled=False)
    assert "admin" not in employer_slugs()
    assert excluded("employer", "work/scratch-notes.md")
    assert "holding" in meetings_dirs()
    assert "metadata" not in meetings_dirs()
    assert phrase_blocked(slack_exclude(), "random-chatter")
    assert "policy" not in slack_activity()
    assert "gsr_" in slack_activity()
    assert not skip_folder("Trash")
    assert not noise_folder("Trash")
    assert skip_folder("Sent Mail")
    assert not noise_folder("Sent Mail")
    assert excluded("git", "wip the notes")
    assert not excluded("git", "swipe the deck")
    assert not excluded("git", "workshop notes")
    assert not excluded("git", "ocean brief")
    assert excluded("chatgpt", "scratch chat about energy")
    assert not excluded("linkedin", "Researcher")


def test_applications_skip_cache_directories(isolated: Path, corpus) -> None:
    from dossier.sources.applications import ApplicationsSource

    root = isolated / "job applications"
    (root / "cache").mkdir(parents=True)
    (root / "cache" / "note.md").write_text("inside cache\n", encoding="utf-8")
    (root / "letter.md").write_text("the letter\n", encoding="utf-8")
    ApplicationsSource().load(root, corpus)
    uris = [rec.uri for rec in corpus.records("applications")]
    assert any(uri.endswith("letter.md") for uri in uris)
    assert not any("cache" in uri for uri in uris)


def test_env_overrides_the_file(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (isolated / "dossier.toml").write_text(
        '[mail]\nexclude = ["promo"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DOSSIER_MAIL_EXCLUDE", "widgets")
    assert noise_folder("Widgets")
    assert not noise_folder("Promo")
    assert noise_folder("Newsletters")
