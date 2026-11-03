"""Docs and code must name the same commands and environment variables."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dossier.cli import main

ROOT = Path(__file__).resolve().parents[1]


def _doc_text() -> str:
    parts = [path.read_text(encoding="utf-8") for path in sorted((ROOT / "docs").glob("*.md"))]
    parts.append((ROOT / "README.md").read_text(encoding="utf-8"))
    parts.append((ROOT / "dossier.example.toml").read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_every_env_var_the_code_reads_is_documented() -> None:
    names: set[str] = set()
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        names |= set(re.findall(r"""["'](DOSSIER_[A-Z0-9_]+)["']""", text))
    docs = _doc_text()
    missing = sorted(name for name in names if name not in docs)
    assert not missing, f"undocumented environment variables: {missing}"


def test_every_subcommand_is_in_the_cli_guide(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["--help"])
    assert stop.value.code == 0
    out = capsys.readouterr().out
    match = re.search(r"\{([a-z0-9,\-]+)\}", out)
    assert match, out
    commands = match.group(1).split(",")
    assert len(commands) >= 20
    guide = (ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
    missing = [name for name in commands if f"dossier {name}" not in guide]
    assert not missing, f"commands missing from docs/cli.md: {missing}"


def test_ci_installs_every_extra_the_tests_use() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for extra in ("vec", "render", "office", "web", "dev"):
        assert f"--extra {extra}" in ci, extra
    assert "dossier eval --retrieval" in ci


def test_sdist_excludes_hypothesis_cache() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/.hypothesis" in pyproject
    assert ".hypothesis/" in gitignore
