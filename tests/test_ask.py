from dossier.ask import answer_question, retrieve
from dossier.store import Record


class _Boom:
    provider = "boom"

    def check_config(self, model: str) -> tuple[bool, str]:
        return True, "ok"

    def complete(self, request) -> str:
        raise AssertionError("model should not be called")

    def complete_json(self, request) -> dict:
        raise AssertionError("model should not be called")


class _Payload:
    provider = "fake"

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def check_config(self, model: str) -> tuple[bool, str]:
        return True, "ok"

    def complete(self, request) -> str:
        return ""

    def complete_json(self, request) -> dict:
        return self.payload


def _records() -> list[Record]:
    return [
        Record(
            id="r1",
            source="pubs",
            uri="zotero://fixture/1",
            title="Synthetic coastal paper",
            text="Glen wrote a synthetic paper on coastal governance.",
        ),
        Record(
            id="r2",
            source="chatgpt",
            uri="chatgpt://c/m",
            title="Shopping",
            text="Buy milk and eggs.",
        ),
    ]


def test_retrieve_caps_the_prompt_at_eight_hits() -> None:
    records = [
        Record(
            id=f"r{i}",
            source="pubs",
            uri=f"zotero://fixture/{i}",
            title=f"Paper {i}",
            text=f"coastal governance topic number {i}",
        )
        for i in range(12)
    ]
    hits = retrieve(records, "coastal governance", limit=50)
    assert len(hits) == 8


def test_retrieve_ranks_overlapping_record() -> None:
    hits = retrieve(_records(), "What did I write on coastal governance?")
    assert [hit.uri for hit in hits] == ["zotero://fixture/1"]


def test_no_hits_skips_the_model() -> None:
    result = answer_question("lunar base", [], _Boom(), "fake")
    assert result.refused
    assert result.reason == "no matching records"


def test_cited_answer_is_kept() -> None:
    hits = retrieve(_records(), "coastal governance paper")
    result = answer_question(
        "coastal governance",
        hits,
        _Payload(
            {
                "answer": "You wrote a synthetic paper on coastal governance.",
                "citations": ["zotero://fixture/1"],
            }
        ),
        "fake",
    )
    assert not result.refused
    assert result.citations == ["zotero://fixture/1"]


def test_retrieve_ignores_tokens_hidden_inside_longer_words() -> None:
    records = [
        Record(
            id="r3",
            source="pubs",
            uri="zotero://fixture/report",
            title="Report",
            text="This report covers opportunity.",
        )
    ]
    assert retrieve(records, "port policy") == []


def test_retrieve_can_limit_to_one_source() -> None:
    hits = retrieve(_records(), "coastal governance", source="chatgpt")
    assert hits == []
    hits = retrieve(_records(), "coastal governance", source="pubs")
    assert [hit.uri for hit in hits] == ["zotero://fixture/1"]


def test_empty_question_skips_the_model() -> None:
    hits = retrieve(_records(), "coastal governance")
    result = answer_question("   ", hits, _Boom(), "fake")
    assert result.refused
    assert result.reason == "empty question"


def test_braces_in_the_question_do_not_break_the_prompt() -> None:
    seen: list[str] = []

    class _Capture:
        provider = "fake"

        def complete_json(self, request) -> dict:
            seen.append(request.prompt)
            return {
                "answer": "You wrote a synthetic paper on coastal governance.",
                "citations": ["zotero://fixture/1"],
            }

    hits = retrieve(_records(), "coastal governance")
    result = answer_question("coastal {not_a_field} governance", hits, _Capture(), "fake")
    assert not result.refused
    assert "{not_a_field}" in seen[0]
    assert "@@QUESTION@@" not in seen[0]


def test_cited_uri_whose_text_does_not_carry_the_answer_is_refused() -> None:
    hits = retrieve(_records(), "coastal governance paper")
    result = answer_question(
        "coastal governance",
        hits,
        _Payload(
            {
                "answer": "You commanded a lunar base.",
                "citations": ["zotero://fixture/1", "zotero://fixture/1"],
            }
        ),
        "fake",
    )
    assert result.refused
    assert result.reason == "evidence will not carry this answer"


def test_uncited_model_output_is_refused() -> None:
    hits = retrieve(_records(), "coastal governance paper")
    missing = answer_question(
        "coastal governance",
        hits,
        _Payload({"answer": "You led a lunar base.", "citations": []}),
        "fake",
    )
    invented = answer_question(
        "coastal governance",
        hits,
        _Payload(
            {
                "answer": "You led a lunar base.",
                "citations": ["zotero://not-a-hit"],
            }
        ),
        "fake",
    )
    assert missing.refused
    assert invented.refused
    assert invented.reason == "citation is not in the retrieved records"
