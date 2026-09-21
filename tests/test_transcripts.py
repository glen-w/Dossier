import json
from pathlib import Path

from dossier.sources.transcripts import TranscriptsSource
from dossier.store import Corpus


def test_cursor_jsonl_keeps_user_queries(tmp_path: Path, corpus: Corpus) -> None:
    project = tmp_path / "my-project" / "agent-transcripts"
    project.mkdir(parents=True)
    line = {
        "role": "user",
        "message": {
            "content": [
                {
                    "type": "text",
                    "text": "<user_query>\nDraft a note that I led the Oceana BBNJ working group.\n</user_query>",
                }
            ]
        },
    }
    (project / "abc.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
    src = TranscriptsSource()
    assert src.detect(tmp_path)
    src.load(tmp_path, corpus)
    recs = corpus.records("transcripts")
    assert len(recs) == 1
    assert recs[0].uri.startswith("cursor://")
    assert "Oceana BBNJ" in recs[0].text
    assert "<user_query>" not in recs[0].text


def test_grok_json_blob(tmp_path: Path, corpus: Corpus) -> None:
    grok = tmp_path / "sand-client-persistence"
    grok.mkdir()
    payload = {"message": {"text": "Synthetic Grok Bot note: drafted an Oceana coastal briefing."}}
    (grok / "synthetic.blob").write_text(json.dumps(payload), encoding="utf-8")
    src = TranscriptsSource()
    assert src.detect(grok)
    src.load(grok, corpus)
    recs = corpus.records("transcripts")
    assert recs[0].uri.startswith("grok://")
    assert "Oceana coastal briefing" in recs[0].text
