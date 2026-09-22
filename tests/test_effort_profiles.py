"""Effort presets and named profiles."""

from __future__ import annotations

from pathlib import Path

from dossier.config import Config
from dossier.effort import DEFAULT_EFFORT, apply_effort, normalize_effort
from dossier.profiles import (
    VIRTUAL_DEFAULT,
    activate_profile,
    list_profiles,
    load_profile,
    save_profile,
)
from dossier.settings_io import (
    common_settings_patch,
    read_toml_dict,
    save_common_settings,
)


def test_normalize_effort() -> None:
    assert normalize_effort(None) == DEFAULT_EFFORT
    assert normalize_effort("HIGH") == "high"
    assert normalize_effort("nope") == DEFAULT_EFFORT


def test_apply_effort_balanced_leaves_knobs() -> None:
    cfg = Config(
        ask_mode="rich",
        extract_llm=True,
        ask_planner="off",
        effort="balanced",
        llm_timeout_seconds=90.0,
        llm_model="qwen3.8:latest",
        effort_model_high="other:27b",
    )
    out = apply_effort(cfg)
    assert out.ask_mode == "rich"
    assert out.extract_llm is True
    assert out.effort == "balanced"
    assert out.llm_timeout_seconds == 90.0
    assert out.llm_max_num_ctx == 32_768
    assert out.llm_model == "qwen3.8:latest"


def test_apply_effort_light_and_high() -> None:
    base = Config(ask_mode="auto", extract_llm=True, ask_planner="off", effort="balanced")
    light = apply_effort(base, "light")
    assert light.extract_llm is False
    assert light.ask_mode == "exact"
    assert light.effort == "light"
    assert light.llm_timeout_seconds == 120.0
    assert light.llm_max_num_ctx == 8192
    high = apply_effort(base, "high")
    assert high.ask_mode == "rich"
    assert high.ask_planner == "rich"
    assert high.effort == "high"
    assert high.llm_timeout_seconds == 600.0
    assert high.llm_max_num_ctx == 32_768


def test_high_model_override_does_not_leak() -> None:
    cfg = Config(
        llm_model="qwen3.8:latest",
        effort="balanced",
        effort_model_high="other:27b",
    )
    assert apply_effort(cfg, "balanced").llm_model == "qwen3.8:latest"
    assert apply_effort(cfg, "high").llm_model == "other:27b"


def test_from_env_keeps_high_model_off_balanced(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    (tmp_path / "dossier.toml").write_text(
        '\n'.join(
            [
                'effort = "balanced"',
                "",
                "[efforts.high]",
                'model = "other:27b"',
                "",
                "[llm]",
                'model = "qwen3.8:latest"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    cfg = Config.from_env()
    assert cfg.effort == "balanced"
    assert cfg.llm_model == "qwen3.8:latest"
    assert cfg.llm_timeout_seconds == 300.0
    assert cfg.llm_max_num_ctx == 32_768
    assert cfg.effort_model_high == "other:27b"


def test_settings_round_trip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    path = tmp_path / "dossier.toml"
    save_common_settings(
        path,
        common_settings_patch(
            effort="light",
            model="qwen2.5:3b",
            max_calls=4,
            ask_mode="exact",
            extract_llm=False,
        ),
    )
    data = read_toml_dict(path)
    assert data["effort"] == "light"
    assert data["llm"]["model"] == "qwen2.5:3b"
    assert data["llm"]["max_calls"] == 4
    assert data["ask"]["mode"] == "exact"
    assert data["extract"]["llm"] is False
    cfg = Config.from_env()
    assert cfg.effort == "light"
    assert cfg.extract_llm is False
    assert cfg.ask_mode == "exact"
    assert cfg.llm_model == "qwen2.5:3b"
    assert cfg.llm_max_calls == 4


def test_profile_activate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    save_profile(
        "quick",
        description="fast pass",
        config={
            "effort": "light",
            "llm": {"model": "tiny", "max_calls": 2},
            "ask": {"mode": "exact"},
            "extract": {"llm": False},
        },
        root=tmp_path,
    )
    names = [p.name for p in list_profiles(tmp_path)]
    assert VIRTUAL_DEFAULT in names
    assert "quick" in names
    activate_profile("quick", tmp_path)
    data = read_toml_dict(tmp_path / "dossier.toml")
    assert data["effort"] == "light"
    assert data["llm"]["model"] == "tiny"
    loaded = load_profile("quick", tmp_path)
    assert loaded.description == "fast pass"
    activate_profile(VIRTUAL_DEFAULT, tmp_path)
    data2 = read_toml_dict(tmp_path / "dossier.toml")
    assert data2["effort"] == DEFAULT_EFFORT
