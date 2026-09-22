from dossier.ask import approved_answer
from dossier.brief import run_pack
from dossier.cards import STATUS_APPROVED, ClaimCard
from dossier.config import Config
from dossier.packs import CAREER, PackQuestion
from dossier.store import Corpus, Record


class _Boom:
    provider = "boom"

    def check_config(self, model: str) -> tuple[bool, str]:
        return True, "ok"

    def complete(self, request) -> str:
        raise AssertionError("model should not be called")

    def complete_json(self, request) -> dict:
        raise AssertionError("model should not be called")


def _cfg() -> Config:
    return Config(ask_fts=False, ask_passages=False, ask_cards_first=True, ask_limit=5)


def _load(corpus: Corpus) -> None:
    corpus.upsert_record(
        Record(
            id="pos",
            source="linkedin",
            uri="linkedin://positions/0",
            title="Analyst at Oceans",
            text="Analyst at Oceans. Paris. Jan 2015–Feb 2018",
            table="linkedin.positions",
        )
    )
    corpus.upsert_record(
        Record(
            id="edu",
            source="linkedin",
            uri="linkedin://education/0",
            title="LLM at Example",
            text="LLM at Example. 2010–2012",
            table="linkedin.education",
        )
    )
    corpus.upsert_record(
        Record(
            id="skills",
            source="linkedin",
            uri="linkedin://skills",
            title="LinkedIn skills",
            text="Skills: Pedagogy, Facilitation",
            table="linkedin.skills",
        )
    )
    corpus.upsert_record(
        Record(
            id="pub",
            source="linkedin",
            uri="https://example.test/library",
            title="See the library",
            text="See the library",
            table="linkedin.publications",
        )
    )
    corpus.upsert_record(
        Record(
            id="chat",
            source="chatgpt",
            uri="chatgpt://c/held",
            title="Disk",
            text="The disk is already being held by something.",
        )
    )
    corpus.put_card(
        ClaimCard(
            id="card-held",
            claim="The disk is already being held by something.",
            citations=["chatgpt://c/held"],
            source="chatgpt",
            status=STATUS_APPROVED,
        )
    )
    corpus.upsert_record(
        Record(
            id="shot",
            source="slack",
            uri="slack://shot",
            title="image.png",
            text="Lens: delivered\nKind: report\nYear: 2024\nArtifacts: image.png",
        )
    )
    corpus.upsert_record(
        Record(
            id="report",
            source="slack",
            uri="slack://report",
            title="Cooling sidebar",
            text=(
                "Lens: delivered\nKind: report\nYear: 2024\n"
                "Skills: science-policy\nArtifacts: cooling sidebar.docx"
            ),
        )
    )
    corpus.upsert_record(
        Record(
            id="chapter",
            source="slack",
            uri="slack://chapter",
            title="Ocean chapter",
            text=(
                "Lens: delivered, contributions\nKind: chapter\nYear: 2023\n"
                "Artifacts: gsr ocean chapter.docx"
            ),
        )
    )
    corpus.upsert_record(
        Record(
            id="review",
            source="mbox",
            uri="mbox://review",
            title="Peer review",
            text=(
                "Lens: contributions\nKind: review\nYear: 2021\n"
                "Skills: teaching, photoshop\nArtifacts: peer review.docx"
            ),
        )
    )


def test_career_brief_lists_records_not_a_shared_verb(corpus: Corpus) -> None:
    _load(corpus)
    items = run_pack(corpus, list(CAREER), _cfg(), _Boom(), mode="exact")
    by_id = {item.id: result for item, result in items}
    assert [item.id for item, _result in items] == [q.id for q in CAREER]
    roles = by_id["roles"]
    assert roles.route == "inventory"
    assert "Analyst at Oceans (Jan 2015–Feb 2018)" in roles.text
    assert "LLM at Example" not in roles.text
    assert "held by" not in roles.text
    assert roles.citations == ["linkedin://positions/0"]
    skills = by_id["skills"]
    assert "- science-policy" in skills.text
    assert "- teaching" in skills.text
    assert "photoshop" not in skills.text
    assert "LinkedIn: Pedagogy, Facilitation" in skills.text
    assert "slack://report" in skills.citations
    delivered = by_id["delivered"]
    assert "cooling sidebar.docx" in delivered.text
    assert "image.png" not in delivered.text
    assert "gsr ocean chapter.docx" not in delivered.text
    contributions = by_id["contributions"]
    assert "peer review.docx" in contributions.text
    assert "cooling sidebar.docx" not in contributions.text
    publications = by_id["publications"]
    assert "See the library" in publications.text
    assert "gsr ocean chapter.docx" in publications.text
    assert "https://example.test/library" in publications.citations


def test_draft_copies_do_not_crowd_out_an_older_file(corpus: Corpus) -> None:
    for name, year in (
        ("cooling sidebar draft.docx", "2025"),
        ("cooling sidebar final.docx", "2025"),
        ("cooling sidebar revised.docx", "2024"),
        ("ocean mcs paper.docx", "2014"),
        ("registration form.pdf", "2026"),
    ):
        corpus.upsert_record(
            Record(
                id=name,
                source="slack",
                uri=f"slack://{name}",
                title=name,
                text=f"Lens: delivered\nKind: report\nYear: {year}\nArtifacts: {name}",
            )
        )
    items = run_pack(
        corpus,
        [PackQuestion("delivered", "What work did I deliver?", lens="delivered")],
        _cfg(),
        _Boom(),
        mode="exact",
    )
    text = items[0][1].text
    assert "ocean mcs paper.docx" in text
    assert "registration form" not in text
    assert text.count("cooling sidebar") == 1


def test_loose_approved_card_does_not_answer_roles(corpus: Corpus) -> None:
    _load(corpus)
    assert approved_answer(corpus, "What roles have I held?") is None


def test_empty_career_question_does_not_add_a_follow_up(corpus: Corpus) -> None:
    items = run_pack(
        corpus,
        [PackQuestion("roles", "What roles have I held?", source="linkedin")],
        _cfg(),
        _Boom(),
        mode="exact",
    )
    assert len(items) == 1
    assert items[0][1].refused
    assert items[0][1].reason == "nothing recorded"


def test_specific_question_still_uses_an_approved_card(corpus: Corpus) -> None:
    corpus.upsert_record(
        Record(
            id="r1",
            source="pubs",
            uri="zotero://fixture/1",
            title="Note",
            text="Glen wrote a synthetic paper on coastal governance.",
        )
    )
    corpus.put_card(
        ClaimCard(
            id="card1",
            claim="Synthetic paper on coastal governance.",
            citations=["zotero://fixture/1"],
            source="pubs",
            status=STATUS_APPROVED,
        )
    )
    answer = approved_answer(corpus, "coastal governance paper")
    assert answer is not None
    assert answer.text == "Synthetic paper on coastal governance."
