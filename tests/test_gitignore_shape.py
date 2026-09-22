import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "release" / "check_gitignore.py"
_spec = importlib.util.spec_from_file_location("check_gitignore", _PATH)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)

REQUIRED_LINES = _mod.REQUIRED_LINES
missing_patterns = _mod.missing_patterns
personal_tracked = _mod.personal_tracked


def test_repo_gitignore_has_the_personal_data_shape() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / ".gitignore").read_text(encoding="utf-8")
    assert missing_patterns(text) == []


def test_missing_pattern_is_reported() -> None:
    text = "\n".join(line for line in REQUIRED_LINES if line != "data/")
    assert missing_patterns(text) == ["data/"]


def test_tracked_personal_paths_are_rejected() -> None:
    assert personal_tracked(
        [
            "src/dossier/cli.py",
            "dossier.example.toml",
            "data/evidence.db",
            "data/dossier.toml",
            "notes.pdf",
            "exports/mail.mbox",
        ]
    ) == [
        "data/evidence.db",
        "data/dossier.toml",
        "notes.pdf",
        "exports/mail.mbox",
    ]
