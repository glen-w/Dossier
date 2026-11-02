from pathlib import Path

import pytest

from dossier.config import Config
from dossier.ops import detected_targets, ingest, locker_snapshot, readiness_notes
from dossier.store import Corpus


def test_locker_snapshot_and_notes(corpus: Corpus) -> None:
    cfg = Config(data_dir=str(corpus.db_path.parent), llm_enabled=False)
    snap = locker_snapshot(cfg, corpus)
    assert "records" in snap
    notes = readiness_notes(cfg, corpus)
    assert isinstance(notes, list)
    targets = detected_targets(())
    assert isinstance(targets, list)


def test_ingest_unknown_adapter(corpus: Corpus) -> None:
    with pytest.raises(ValueError, match="unknown adapter"):
        ingest(corpus, adapter="not-an-adapter")


def test_ingest_notes_folder(tmp_path: Path, corpus: Corpus) -> None:
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "note.md").write_text(
        "Quinn wrote a synthetic paper on coastal governance.\n", encoding="utf-8"
    )
    targets, before, after = ingest(corpus, adapter="notes", path=folder)
    assert targets
    assert after == before + 1
