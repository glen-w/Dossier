"""Prompt catalogue: builtins match the old strings, overrides win."""

from __future__ import annotations

from pathlib import Path

from dossier.extract import EXTRACT_PROMPT, SEEKER_PROMPT_TAIL
from dossier.prompts import (
    active_prompt,
    render,
    resolve,
    restore_builtin,
    save_override,
    start_prompt_log,
    stop_prompt_log,
)


def test_builtin_render_matches_previous_strings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    extract = active_prompt("extract", tmp_path)
    rendered = render(
        extract,
        {"URI": "file://a", "TITLE": "T", "TEXT": "body"},
        record=False,
    )
    expected = (
        EXTRACT_PROMPT.replace("@@URI@@", "file://a")
        .replace("@@TITLE@@", "T")
        .replace("@@TEXT@@", "body")
    )
    assert rendered == expected
    seeker = resolve("extract_seeker", tmp_path)
    seeker_text = render(
        seeker,
        {"URI": "file://a", "TITLE": "T", "TEXT": "body"},
        record=False,
    )
    assert seeker_text == expected + SEEKER_PROMPT_TAIL


def test_override_bumps_version_and_wins(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    saved = save_override(
        "ask",
        system_prompt="Stay short.",
        user_template="Q: @@QUESTION@@\n@@RECORDS@@\n@@PRIOR@@",
        root=tmp_path,
    )
    assert saved.version == 2
    assert saved.source == "override"
    loaded = active_prompt("ask", tmp_path)
    assert loaded.version == 2
    text = render(
        loaded,
        {"QUESTION": "What?", "RECORDS": "none", "PRIOR": ""},
        record=False,
    )
    assert text.startswith("Stay short.")
    token = start_prompt_log()
    render(loaded, {"QUESTION": "What?", "RECORDS": "none", "PRIOR": ""})
    stamp = stop_prompt_log(token, empty="ask=none")
    assert stamp == "prompts: ask@2"
    restore_builtin("ask", tmp_path)
    assert active_prompt("ask", tmp_path).version == 1
    token = start_prompt_log()
    stamp = stop_prompt_log(token, empty="ask=none")
    assert stamp == "prompts: ask=none"


def test_custom_file_wins_over_override(tmp_path: Path) -> None:
    from dossier.prompts import save_custom

    save_override(
        "ask",
        system_prompt="",
        user_template="override @@QUESTION@@",
        root=tmp_path,
    )
    custom_dir = tmp_path / "prompts" / "custom"
    custom_dir.mkdir(parents=True)
    (custom_dir / "ask.json").write_text(
        """{
  "prompt_id": "ask",
  "version": 9,
  "title": "Custom ask",
  "family": "ask",
  "system_prompt": "",
  "user_template": "custom @@QUESTION@@"
}
""",
        encoding="utf-8",
    )
    loaded = resolve("ask", tmp_path)
    assert loaded.source == "custom"
    assert loaded.version == 9
    saved = save_custom(
        "ask_short",
        title="Short ask",
        family="ask",
        system_prompt="",
        user_template="@@QUESTION@@",
        root=tmp_path,
    )
    assert saved.version == 1
    assert resolve("ask_short", tmp_path).source == "custom"
