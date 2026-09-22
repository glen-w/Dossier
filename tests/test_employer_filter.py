"""Employer pre-filter: junk types, older copies, then an optional folder prompt."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dossier.llm.client import CompletionRequest, LLMClientError
from dossier.sources.employer import EmployerSource
from dossier.sources.employer_filter import version_stem
from dossier.store import Corpus


def test_version_stem_strips_copy_markers() -> None:
    assert version_stem("notes.md") == "notes"
    assert version_stem("notes (final).md") == "notes"
    assert version_stem("notes (final)2.md") == "notes"
    assert version_stem("Copy of notes.md") == "notes"
    assert version_stem("Workshop agenda (002).pdf") == "workshop agenda"
    assert version_stem("240306_ECF_data_meeting.pptx") != version_stem(
        "240307_Buildings_Forum.docx"
    )


def test_filter_skips_cache_hashed_names_and_keeps_newest_copy(
    tmp_path: Path, corpus: Corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "REN21"
    folder.mkdir()
    (folder / "notes.md").write_text("old notes\n", encoding="utf-8")
    (folder / "notes (final).md").write_text("final notes about the launch\n", encoding="utf-8")
    os.utime(folder / "notes.md", (1_000_000_000, 1_000_000_000))
    os.utime(folder / "notes (final).md", (1_700_000_000, 1_700_000_000))
    (folder / "240306_ECF.md").write_text("ECF meeting note\n", encoding="utf-8")
    (folder / "240307_Buildings.md").write_text("Buildings forum note\n", encoding="utf-8")
    (folder / "02b465832b0649134a04b7a24cffac25.pkl").write_bytes(b"pickle")
    (folder / "shot.png").write_bytes(b"png")
    (folder / "~$notes.docx").write_bytes(b"lock")
    cache = folder / "data" / "adaptation code" / "data" / "cache"
    cache.mkdir(parents=True)
    (cache / "kept.md").write_text("should not be read\n", encoding="utf-8")
    (cache / "aa.pkl").write_bytes(b"pkl")
    monkeypatch.setenv("DOSSIER_EMPLOYER_PATHS", str(folder))
    monkeypatch.setenv("DOSSIER_EMPLOYER_FILTER_LLM", "false")
    EmployerSource().load(folder, corpus)
    uris = {rec.uri for rec in corpus.records("employer")}
    assert "file://employer/REN21/notes (final).md" in uris
    assert "file://employer/REN21/notes.md" not in uris
    assert "file://employer/REN21/240306_ECF.md" in uris
    assert "file://employer/REN21/240307_Buildings.md" in uris
    assert not any("cache" in uri or uri.endswith(".pkl") or uri.endswith(".png") for uri in uris)
    assert not any("~$" in uri for uri in uris)


def test_filter_off_keeps_the_cache_file(
    tmp_path: Path, corpus: Corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "REN21"
    cache = folder / "cache"
    cache.mkdir(parents=True)
    (cache / "note.md").write_text("inside cache\n", encoding="utf-8")
    monkeypatch.setenv("DOSSIER_EMPLOYER_PATHS", str(folder))
    monkeypatch.setenv("DOSSIER_EMPLOYER_FILTER", "false")
    monkeypatch.setenv("DOSSIER_EMPLOYER_FILTER_LLM", "false")
    EmployerSource().load(folder, corpus)
    uris = {rec.uri for rec in corpus.records("employer")}
    assert "file://employer/REN21/cache/note.md" in uris


def test_llm_pass_drops_a_named_folder_and_keeps_the_rest(
    tmp_path: Path, corpus: Corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "REN21"
    (folder / "CSE").mkdir(parents=True)
    (folder / "CSE" / "minutes.md").write_text("Minutes of the coaching session.\n", encoding="utf-8")
    dumps = folder / "raw dumps"
    dumps.mkdir()
    (dumps / "table.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    class Fake:
        provider = "fake"

        def complete_json(self, request: CompletionRequest) -> dict[str, list[str]]:
            assert "CSE" in request.prompt
            assert "raw dumps" in request.prompt
            assert "Minutes" not in request.prompt
            return {"drop": ["raw dumps"]}

    monkeypatch.setenv("DOSSIER_EMPLOYER_PATHS", str(folder))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("DOSSIER_EMPLOYER_FILTER", "true")
    monkeypatch.setenv("DOSSIER_EMPLOYER_FILTER_LLM", "true")
    monkeypatch.setattr("dossier.sources.employer.get_client", lambda cfg: Fake())
    EmployerSource().load(folder, corpus)
    uris = {rec.uri for rec in corpus.records("employer")}
    assert "file://employer/REN21/CSE/minutes.md" in uris
    assert "file://employer/REN21/raw dumps/table.csv" not in uris


def test_llm_error_keeps_the_deterministic_set(
    tmp_path: Path, corpus: Corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "REN21"
    (folder / "CSE").mkdir(parents=True)
    (folder / "CSE" / "minutes.md").write_text("Minutes.\n", encoding="utf-8")
    (folder / "stuff i did").mkdir()
    (folder / "stuff i did" / "agenda.md").write_text("Agenda.\n", encoding="utf-8")

    class Broken:
        provider = "fake"

        def complete_json(self, request: CompletionRequest) -> dict[str, list[str]]:
            raise LLMClientError("invalid JSON")

    monkeypatch.setenv("DOSSIER_EMPLOYER_PATHS", str(folder))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("DOSSIER_EMPLOYER_FILTER", "true")
    monkeypatch.setenv("DOSSIER_EMPLOYER_FILTER_LLM", "true")
    monkeypatch.setattr("dossier.sources.employer.get_client", lambda cfg: Broken())
    EmployerSource().load(folder, corpus)
    uris = {rec.uri for rec in corpus.records("employer")}
    assert "file://employer/REN21/CSE/minutes.md" in uris
    assert "file://employer/REN21/stuff i did/agenda.md" in uris
