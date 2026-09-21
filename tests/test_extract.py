from dossier.cards import STATUS_PENDING, ProposedClaim
from dossier.extract import extract_record, proposals_from_json
from dossier.store import Record


class FakeLLM:
    provider = "fake"

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def check_config(self, model: str) -> tuple[bool, str]:
        return True, "ok"

    def complete(self, request) -> str:
        import json

        return json.dumps(self.payload)

    def complete_json(self, request) -> dict:
        return self.payload


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
