import json
from pathlib import Path

import pytest

from dossier.cli import main
from dossier.drafts import draft_record
from dossier.sources.meetings import MeetingsSource
from dossier.store import Corpus


@pytest.fixture(autouse=True)
def _default_speaker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOSSIER_SPEAKER_NAMES", raising=False)


def _write(
    root: Path,
    stem: str,
    speaker_map: dict[str, str],
    segments: list[tuple[str, str]],
    *,
    ignored: tuple[str, ...] = (),
    library: bool = True,
    imported_at: str = "2025-06-10T00:00:00Z",
) -> None:
    doc = {
        "schema_version": 1,
        "source": {
            "type": "whisperx",
            "imported_at": imported_at,
            "original_path": f"originals/{stem}.json",
        },
        "metadata": {"segment_count": len(segments)},
        "segments": [
            {"speaker": sid, "text": text, "start": float(i), "end": float(i + 1)}
            for i, (sid, text) in enumerate(segments)
        ],
    }
    side = {"speaker_map": speaker_map, "ignored_speakers": list(ignored)}
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{stem}.json").write_text(json.dumps(doc), encoding="utf-8")
    if library:
        maps = root / "metadata" / "speaker_maps"
        maps.mkdir(parents=True, exist_ok=True)
        (maps / f"{stem}.speaker_map.json").write_text(json.dumps(side), encoding="utf-8")
    else:
        (root / f"{stem}.speaker_map.json").write_text(json.dumps(side), encoding="utf-8")


def _library(root: Path) -> None:
    _write(
        root,
        "250610_ocean_webinar",
        {"SPEAKER_00": "Glen Wright", "SPEAKER_01": "Ada Lovelace"},
        [
            ("SPEAKER_00", "I drafted the ocean webinar briefing for the working group."),
            ("SPEAKER_01", "The parking meters on the street need a coin."),
        ],
    )
    _write(
        root,
        "250611_team",
        {"SPEAKER_00": "Ada Lovelace", "SPEAKER_01": "Bob"},
        [("SPEAKER_00", "Ada convened the team meeting and reviewed the agenda.")],
    )
    _write(
        root,
        "250612_placeholder",
        {"SPEAKER_00": "SPEAKER_00"},
        [("SPEAKER_00", "Glen drafted a briefing but this speaker was never named.")],
    )
    _write(
        root,
        "250613_ignored",
        {"SPEAKER_00": "Glen Wright", "SPEAKER_01": "Ada Lovelace"},
        [("SPEAKER_00", "I drafted the ignored briefing.")],
        ignored=("SPEAKER_00",),
    )
    _write(
        root,
        "250614_monologue",
        {"SPEAKER_00": "Glen"},
        [("SPEAKER_00", "Thinking about lunch tomorrow and nothing else.")],
    )
    _write(
        root,
        "250615_workshop",
        {"SPEAKER_00": "Glen Wright"},
        [("SPEAKER_00", "I taught the workshop session on coastal governance.")],
    )
    _write(
        root,
        "250610_ocean_webinar__inbox",
        {"SPEAKER_00": "Glen Wright", "SPEAKER_01": "Ada Lovelace"},
        [("SPEAKER_00", "Inbox duplicate of the ocean webinar. Should not be stored.")],
    )
    _write(
        root,
        "250610_ocean_webinar (conflicted copy 2026-08-23 232516)",
        {"SPEAKER_00": "Glen Wright", "SPEAKER_01": "Ada Lovelace"},
        [("SPEAKER_00", "Conflicted copy of the ocean webinar. Should not be stored.")],
    )
    maps = root / "metadata" / "speaker_maps"
    (root / "broken.json").write_text("{not json", encoding="utf-8")
    (maps / "broken.speaker_map.json").write_text("{not json", encoding="utf-8")


def test_named_speaker_meetings_keep_contributions(tmp_path: Path, corpus: Corpus) -> None:
    root = tmp_path / "library"
    _library(root)
    src = MeetingsSource()
    assert src.detect(root)
    assert not src.detect(tmp_path / "empty")
    src.load(root, corpus)
    recs = corpus.records("meetings")
    uris = {rec.uri for rec in recs}
    assert uris == {
        "meetings://250610_ocean_webinar",
        "meetings://250615_workshop",
    }
    webinar = next(rec for rec in recs if rec.uri.endswith("ocean_webinar"))
    assert webinar.table == "meetings.hits"
    assert "drafted the ocean webinar briefing" in webinar.text
    assert "parking" not in webinar.text
    assert "Inbox duplicate" not in webinar.text
    assert "Conflicted copy" not in webinar.text
    assert "Lens: " in webinar.text
    assert "contributions" in webinar.text
    assert "Kind: webinar" in webinar.text
    assert "Year: 2025" in webinar.text
    assert "Ada Lovelace" in webinar.text
    assert "Hunt: named-speaker, contributions" in webinar.text
    cards = draft_record(webinar, corpus)
    assert len(cards) == 1
    assert cards[0].status == "pending"
    assert cards[0].extras.get("kind") == "webinar"


def test_speaker_names_env_overrides_the_default(
    tmp_path: Path, corpus: Corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "library"
    _library(root)
    monkeypatch.setenv("DOSSIER_SPEAKER_NAMES", "Ada Lovelace")
    MeetingsSource().load(root, corpus)
    recs = {rec.uri: rec for rec in corpus.records("meetings")}
    assert set(recs) == {
        "meetings://250611_team",
        "meetings://250610_ocean_webinar",
    }
    assert "convened the team meeting" in recs["meetings://250611_team"].text
    webinar = recs["meetings://250610_ocean_webinar"].text
    assert "parking meters" in webinar
    assert "drafted the ocean webinar briefing" not in webinar


def test_colocated_export_folder(tmp_path: Path, corpus: Corpus) -> None:
    root = tmp_path / "export"
    _write(
        root,
        "250520-team-meeting",
        {"SPEAKER_00": "Glen", "SPEAKER_01": "Ada"},
        [("SPEAKER_00", "I chaired the team meeting and drafted the note.")],
        library=False,
    )
    src = MeetingsSource()
    assert src.detect(root)
    src.load(root, corpus)
    recs = corpus.records("meetings")
    assert len(recs) == 1
    assert recs[0].uri == "meetings://250520-team-meeting"
    assert recs[0].title == "team meeting"
    assert "chaired the team meeting" in recs[0].text


def test_display_name_segments_and_near_miss_names(tmp_path: Path, corpus: Corpus) -> None:
    root = tmp_path / "library"
    _write(
        root,
        "250701_ocean_webinar",
        {"SPEAKER_00": "Glen Wright", "SPEAKER_01": "Ada"},
        [
            ("Glen Wright", "I drafted the ocean webinar briefing."),
            ("Ada", "The parking meters on the street need a coin."),
        ],
    )
    _write(
        root,
        "250702_notes",
        {"SPEAKER_00": "Glen Wright"},
        [("Glen Wright", "Thinking about lunch tomorrow and nothing else.")],
    )
    _write(
        root,
        "250703_glenda",
        {"SPEAKER_00": "Glenda", "SPEAKER_01": "Bob"},
        [("SPEAKER_00", "Glenda drafted the coastal briefing for the group.")],
    )
    _write(
        root,
        "250704_numeric",
        {"0": "Glen Wright", "1": "Ada"},
        [
            ("0", "I edited the numeric-id briefing."),
            ("1", "Unrelated parking note from Ada."),
        ],
    )
    MeetingsSource().load(root, corpus)
    recs = {rec.uri: rec.text for rec in corpus.records("meetings")}
    assert set(recs) == {
        "meetings://250701_ocean_webinar",
        "meetings://250704_numeric",
    }
    assert "drafted the ocean webinar briefing" in recs["meetings://250701_ocean_webinar"]
    assert "parking" not in recs["meetings://250701_ocean_webinar"]
    assert "edited the numeric-id briefing" in recs["meetings://250704_numeric"]
    assert "Unrelated parking" not in recs["meetings://250704_numeric"]


def test_year_org_and_silent_named_speaker(tmp_path: Path, corpus: Corpus) -> None:
    root = tmp_path / "library"
    _write(
        root,
        "REN21-team-call",
        {"SPEAKER_00": "Glen", "SPEAKER_01": "Ada"},
        [("SPEAKER_00", "I convened the REN21 team call.")],
        imported_at="2024-03-01T00:00:00Z",
    )
    _write(
        root,
        "20260619120000_checkin",
        {"SPEAKER_00": "Glen Wright", "SPEAKER_01": "Ada"},
        [("SPEAKER_00", "I drafted the June check-in note.")],
    )
    _write(
        root,
        "250801_quiet",
        {"SPEAKER_00": "Glen Wright", "SPEAKER_01": "Ada"},
        [("SPEAKER_01", "Ada spoke. Glen was named and said nothing.")],
    )
    MeetingsSource().load(root, corpus)
    recs = {rec.uri: rec.text for rec in corpus.records("meetings")}
    assert "meetings://250801_quiet" not in recs
    assert "Year: 2024" in recs["meetings://REN21-team-call"]
    assert "Org: REN21" in recs["meetings://REN21-team-call"]
    assert "Year: 2026" in recs["meetings://20260619120000_checkin"]


def test_caps_quotas_and_escapes(
    tmp_path: Path, corpus: Corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "library"
    long = "I drafted the ocean webinar briefing. " * 400
    _write(
        root,
        "250901_ocean_webinar",
        {"SPEAKER_00": "Glen", "SPEAKER_01": "Ada"},
        [("SPEAKER_00", long), ("SPEAKER_01", "parking")],
    )
    _write(
        root,
        "250902_ocean_webinar",
        {"SPEAKER_00": "Glen", "SPEAKER_01": "Ada"},
        [("SPEAKER_00", "I drafted the second ocean webinar briefing.")],
    )
    monkeypatch.setenv("DOSSIER_SEEKER_PER_STRATUM", "1")
    monkeypatch.setenv("DOSSIER_SEEKER_OVERALL", "1")
    MeetingsSource().load(root, corpus)
    recs = corpus.records("meetings")
    assert len(recs) == 1
    assert len(recs[0].text) <= 8000
    assert "drafted" in recs[0].text
    assert "parking" not in recs[0].text

    outside = tmp_path / "outside.json"
    outside.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": {"imported_at": "2025-01-01T00:00:00Z"},
                "segments": [
                    {
                        "speaker": "SPEAKER_00",
                        "text": "Secret phrase that must stay outside the corpus.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    leak_root = tmp_path / "leak"
    maps = leak_root / "metadata" / "speaker_maps"
    maps.mkdir(parents=True)
    (maps / "250903_leak.speaker_map.json").write_text(
        json.dumps(
            {
                "speaker_map": {"SPEAKER_00": "Glen", "SPEAKER_01": "Ada"},
                "ignored_speakers": [],
            }
        ),
        encoding="utf-8",
    )
    (leak_root / "250903_leak.json").symlink_to(outside)
    MeetingsSource().load(leak_root, corpus)
    blob = " ".join(rec.text for rec in corpus.records("meetings"))
    assert "Secret phrase" not in blob

    fat = tmp_path / "fat"
    monkeypatch.setattr("dossier.seekers.meetings.MAX_BYTES", 80)
    _write(
        fat,
        "250904_ocean_webinar",
        {"SPEAKER_00": "Glen", "SPEAKER_01": "Ada"},
        [("SPEAKER_00", "I drafted a briefing that is longer than the byte cap.")],
    )
    before = {rec.uri for rec in corpus.records("meetings")}
    MeetingsSource().load(fat, corpus)
    assert {rec.uri for rec in corpus.records("meetings")} == before


def test_single_file_and_inbox_only_copy(tmp_path: Path, corpus: Corpus) -> None:
    root = tmp_path / "export"
    _write(
        root,
        "250520-team-meeting",
        {"SPEAKER_00": "Glen", "SPEAKER_01": "Ada"},
        [("SPEAKER_00", "I chaired this exported team meeting.")],
        library=False,
    )
    src = MeetingsSource()
    path = root / "250520-team-meeting.json"
    assert src.detect(path)
    src.load(path, corpus)
    inbox = tmp_path / "inbox-only"
    _write(
        inbox,
        "250521_team__inbox",
        {"SPEAKER_00": "Glen", "SPEAKER_01": "Ada"},
        [("SPEAKER_00", "I drafted the inbox-only team note.")],
    )
    src.load(inbox, corpus)
    uris = {rec.uri for rec in corpus.records("meetings")}
    assert "meetings://250520-team-meeting" in uris
    assert "meetings://250521_team__inbox" in uris


def test_cli_ingest_meetings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path / "data"))
    root = tmp_path / "library"
    _library(root)
    assert main(["ingest", "--adapter", "meetings", str(root)]) == 0
    corpus = Corpus(tmp_path / "data" / "evidence.db")
    try:
        uris = {rec.uri for rec in corpus.records("meetings")}
    finally:
        corpus.close()
    assert "meetings://250610_ocean_webinar" in uris
    assert "meetings://250614_monologue" not in uris
