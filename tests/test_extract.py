from dossier.cards import STATUS_PENDING, ProposedClaim
from dossier.extract import (
    ExtractProgress,
    extract_corpus,
    extract_record,
    proposals_from_json,
    text_chunks,
)
from dossier.store import Record


class FakeLLM:
    provider = "fake"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def check_config(self, model: str) -> tuple[bool, str]:
        return True, "ok"

    def complete(self, request) -> str:
        import json

        return json.dumps(self.payload)

    def complete_json(self, request) -> dict:
        self.prompts.append(request.prompt)
        return self.payload


def test_text_chunks_splits_paragraphs() -> None:
    body = ("alpha " * 200).strip() + "\n\n" + ("beta " * 200).strip()
    chunks = text_chunks(body, chunk_chars=500, max_chunks=4)
    assert len(chunks) >= 2
    assert all(len(c) <= 500 for c in chunks)
    assert "alpha" in chunks[0]
    assert any("beta" in c for c in chunks)


def test_text_chunks_respects_max() -> None:
    parts = [f"para{i} " + ("x" * 400) for i in range(10)]
    chunks = text_chunks("\n\n".join(parts), chunk_chars=450, max_chunks=2)
    assert len(chunks) == 2


def test_extract_record_chunks_large_text(corpus) -> None:
    record = Record(
        id="r-chunk",
        source="pubs",
        uri="zotero://fixture/chunk",
        title="Long",
        text=("Glen wrote chapter one on coastal governance.\n\n" * 80)
        + "Glen drafted a second brief on ocean policy.",
    )
    corpus.upsert_record(record)
    client = FakeLLM(
        {
            "claims": [
                {
                    "claim": "Wrote on coastal governance",
                    "citations": [record.uri],
                }
            ]
        }
    )
    cards = extract_record(
        record,
        corpus,
        client,
        "fake",
        chunk_chars=200,
        max_chunks=3,
        timeout_seconds=60.0,
    )
    assert len(client.prompts) == 3
    assert all(len(p) < 2000 for p in client.prompts)
    assert cards[0].status == STATUS_PENDING


def test_extract_record_stores_pending(corpus) -> None:
    record = Record(
        id="r1",
        source="pubs",
        uri="zotero://fixture/1",
        title="Synthetic",
        text="Glen wrote a synthetic paper on coastal governance.",
    )
    corpus.upsert_record(record)
    client = FakeLLM(
        {
            "claims": [
                {
                    "claim": "Wrote a synthetic paper on coastal governance",
                    "citations": [record.uri],
                }
            ]
        }
    )
    cards = extract_record(record, corpus, client, "fake")
    assert len(cards) == 1
    assert cards[0].status == STATUS_PENDING
    assert corpus.get_card(cards[0].id) is not None


def test_proposals_from_json_default_uri() -> None:
    props = proposals_from_json(
        {"claims": [{"claim": "Did X"}]},
        "doc://1",
    )
    assert props == [ProposedClaim(claim="Did X", citations=["doc://1"])]


def test_seeker_claims_keep_lens_extras(corpus) -> None:
    record = Record(
        id="r2",
        source="slack",
        uri="slack://C/1.0",
        title="GSR ocean chapter",
        text="Lens: delivered\nKind: chapter\nOrg: REN21\nDrafted the GSR ocean chapter.",
    )
    corpus.upsert_record(record)
    client = FakeLLM(
        {
            "claims": [
                {
                    "claim": "Drafted the GSR ocean chapter",
                    "citations": [record.uri],
                    "lens": "delivered",
                    "kind": "chapter",
                    "org": "REN21",
                    "skills": ["knowledge-and-data"],
                }
            ]
        }
    )
    cards = extract_record(record, corpus, client, "fake")
    assert cards[0].status == STATUS_PENDING
    assert cards[0].extras["lens"] == "delivered"
    assert cards[0].extras["kind"] == "chapter"
    stored = corpus.get_card(cards[0].id)
    assert stored is not None
    assert stored.extras["org"] == "REN21"


def test_extract_prompt_keeps_braces(corpus) -> None:
    record = Record(
        id="r3",
        source="slack",
        uri="slack://brace",
        title="Notes {draft}",
        text="Drafted the {coastal} governance chapter for the report.",
    )
    corpus.upsert_record(record)
    seen: dict[str, str] = {}

    class _Capture(FakeLLM):
        def complete_json(self, request) -> dict:
            seen["prompt"] = request.prompt
            return self.payload

    client = _Capture(
        {
            "claims": [
                {
                    "claim": "Drafted the coastal governance chapter",
                    "citations": [record.uri],
                }
            ]
        }
    )
    cards = extract_record(record, corpus, client, "fake")
    assert "{coastal}" in seen["prompt"]
    assert "{draft}" in seen["prompt"]
    assert cards[0].status == STATUS_PENDING


def test_extract_corpus_reports_progress(corpus) -> None:
    record = Record(
        id="prog",
        source="linkedin",
        uri="linkedin://positions/prog",
        title="Analyst at Oceans",
        text="Analyst at Oceans. Paris. Worked on coastal governance.",
        table="linkedin.positions",
    )
    corpus.upsert_record(record)
    events: list[ExtractProgress] = []

    class _Boom:
        provider = "boom"

        def check_config(self, model: str) -> tuple[bool, str]:
            return True, "ok"

        def complete(self, request) -> str:
            raise AssertionError("model should not run")

        def complete_json(self, request) -> dict:
            raise AssertionError("model should not run")

    cards = extract_corpus(
        corpus,
        _Boom(),
        "fake",
        use_llm=True,
        on_progress=events.append,
    )
    assert cards
    assert events[0].phase == "start"
    assert events[0].total == 1
    assert any(ev.phase == "draft" for ev in events)
    assert events[-1].phase == "done"
    assert events[-1].cards_added == len(cards)
