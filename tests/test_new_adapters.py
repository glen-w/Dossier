from pathlib import Path

from dossier.contributions import CONTRIBUTIONS
from dossier.sources.base import Source
from dossier.store import Corpus


def test_contributions_match_protocol() -> None:
    for item in CONTRIBUTIONS:
        assert isinstance(item.source, Source)
        assert item.source.detect
        assert item.source.load
        assert item.source.tables()


def test_notes_adapter_loads_markdown(tmp_path: Path, corpus: Corpus) -> None:
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "coastal.md").write_text(
        "Quinn wrote a synthetic paper on coastal governance.\n", encoding="utf-8"
    )
    outside = tmp_path / "secret.md"
    outside.write_text("should not ingest", encoding="utf-8")
    (folder / "link.md").symlink_to(outside)
    from dossier.sources.notes import NotesSource

    src = NotesSource()
    assert src.detect(folder)
    src.load(folder, corpus)
    recs = corpus.records("notes")
    assert len(recs) == 1
    assert "coastal governance" in recs[0].text
    assert all("should not ingest" not in rec.text for rec in recs)


def test_ics_adapter_loads_event(tmp_path: Path, corpus: Corpus) -> None:
    path = tmp_path / "talks.ics"
    path.write_text(
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\n"
        "SUMMARY:Coastal governance talk\n"
        "DTSTART:20230921T100000Z\n"
        "DESCRIPTION:Quinn presented a synthetic paper.\n"
        "END:VEVENT\nEND:VCALENDAR\n",
        encoding="utf-8",
    )
    from dossier.sources.calendar import CalendarSource

    src = CalendarSource()
    assert src.detect(path)
    src.load(path, corpus)
    recs = corpus.records("ics")
    assert len(recs) == 1
    assert "Coastal governance talk" in recs[0].text
    assert "2023" in recs[0].text
