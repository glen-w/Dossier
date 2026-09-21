from pathlib import Path

import pytest

from dossier.cards import STATUS_APPROVED, STATUS_PENDING, ClaimCard
from dossier.cli import main
from dossier.referees.rank import Person, note_pubs_coauthors, rank
from dossier.store import Corpus, Record
from dossier.tailor import arrange_letter


POSTING = "We need a workshop and a paper on ocean methods."


def _card(card_id: str, claim: str, *, status: str, span: str = "", kind: str = "workshop") -> ClaimCard:
    extras = {"lens": "delivered", "kind": kind}
    if span:
        extras["span"] = span
        extras["span_uri"] = "slack://1"
    return ClaimCard(
        id=card_id,
        claim=claim,
        citations=["slack://1"],
        source="slack",
        status=status,
        extras=extras,
    )


def _seed(corpus: Corpus) -> None:
    corpus.upsert_record(
        Record(
            id="r1",
            source="slack",
            uri="slack://1",
            title="note",
            text="Lens: delivered\nKind: workshop\nDrafted the ocean workshop briefing.",
        )
    )
    corpus.put_card(
        _card(
            "spanned",
            "Drafted the ocean workshop",
            status=STATUS_APPROVED,
            span="Drafted the ocean workshop briefing.",
        )
    )
    corpus.put_card(
        _card(
            "bare",
            "Drafted the ocean workshop again",
            status=STATUS_APPROVED,
        )
    )
    corpus.put_card(
        _card(
            "pending",
            "Drafted the ocean workshop pending",
            status=STATUS_PENDING,
            span="Drafted the ocean workshop briefing.",
        )
    )


def test_cv_quotes_spanned_cards_and_lists_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_CV_NAME", "Synthetic Person")
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    corpus = Corpus(tmp_path / "evidence.db")
    _seed(corpus)
    corpus.upsert_record(
        Record(
            id="pos",
            source="linkedin",
            uri="linkedin://positions/0",
            title="Analyst at Oceans",
            text="Analyst at Oceans.",
            table="linkedin.positions",
        )
    )
    corpus.close()
    posting = tmp_path / "posting.txt"
    posting.write_text(POSTING, encoding="utf-8")
    assert main(["tailor", "--posting", str(posting), "--kind", "cv"]) == 0
    out = capsys.readouterr().out
    path = Path(out.strip().splitlines()[-1])
    text = path.read_text(encoding="utf-8")
    assert "# CV" in text
    assert "Synthetic Person" in text
    assert "Analyst at Oceans" in text
    assert "Drafted the ocean workshop briefing." in text
    assert "citation: slack://1" in text
    assert "bare:" in text
    assert "pending" not in text
    assert "empty kinds: paper" in text
    assert "matched kinds: workshop" in text


def test_letter_arrange_rejects_a_new_employer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    corpus = Corpus(tmp_path / "evidence.db")
    _seed(corpus)
    corpus.close()
    posting = tmp_path / "posting.txt"
    posting.write_text(POSTING, encoding="utf-8")

    class _Fake:
        provider = "fake"

        def check_config(self, model: str) -> tuple[bool, str]:
            return True, "ok"

        def complete(self, request) -> str:
            return ""

        def complete_json(self, request) -> dict:
            return {
                "sentences": [
                    "I worked at Invented Labs.",
                    "Drafted the ocean workshop briefing.",
                ]
            }

    monkeypatch.setattr("dossier.cli.get_client", lambda cfg: _Fake())
    assert main(["tailor", "--posting", str(posting), "--kind", "letter", "--arrange"]) == 0
    captured = capsys.readouterr()
    err = captured.err
    out = captured.out
    text = Path(out.strip().splitlines()[-1]).read_text(encoding="utf-8")
    assert "arrange refused" in err
    assert "Invented Labs" not in text
    assert "Drafted the ocean workshop briefing." in text


def test_arrange_keeps_glue_and_exact_spans() -> None:
    class _Ok:
        provider = "fake"

        def complete_json(self, request) -> dict:
            return {
                "sentences": [
                    "I am applying for the role in the posting.",
                    "Drafted the ocean workshop briefing.",
                ]
            }

    arranged = arrange_letter(["Drafted the ocean workshop briefing."], _Ok(), "fake")
    assert arranged == [
        "I am applying for the role in the posting.",
        "Drafted the ocean workshop briefing.",
    ]


def test_empty_buffet_writes_no_quote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    Corpus(tmp_path / "evidence.db").close()
    posting = tmp_path / "posting.txt"
    posting.write_text(POSTING, encoding="utf-8")
    assert main(["tailor", "--posting", str(posting)]) == 1
    captured = capsys.readouterr()
    assert "nothing to quote; approve and defend first" in captured.err
    text = Path(captured.out.strip().splitlines()[-1]).read_text(encoding="utf-8")
    assert "Drafted" not in text
    assert "empty kinds: workshop" in text
    assert "empty kinds: paper" in text


def test_letter_keeps_four_matches(corpus: Corpus) -> None:
    from dossier.tailor import LETTER_CAP, select_cards

    for index in range(6):
        corpus.put_card(
            _card(
                f"c{index}",
                f"Drafted ocean workshop briefing {index}",
                status=STATUS_APPROVED,
                span=f"Drafted the ocean workshop briefing number {index}.",
            )
        )
    picked, _bare = select_cards(corpus, POSTING, limit=LETTER_CAP)
    assert len(picked) == 4


def test_pubs_flag_off_does_not_boost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_REFEREE_PUBS", "false")
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(
        Record(
            id="pub",
            source="pubs",
            uri="zotero://stub/bea",
            title="Note",
            text="Bea Paper co-wrote the coastal note.",
        )
    )
    corpus.close()
    people = tmp_path / "people.json"
    people.write_text(
        """
        [
          {"name": "Ada Keywords", "company": "Other", "keywords": "coastal governance"},
          {"name": "Bea Paper", "company": "Other", "keywords": "coastal governance"}
        ]
        """,
        encoding="utf-8",
    )
    posting = tmp_path / "posting.txt"
    posting.write_text("coastal governance methods\n", encoding="utf-8")
    assert main(["referees", "--posting", str(posting), "--people", str(people)]) == 0
    out = capsys.readouterr().out
    assert out.index("Ada Keywords") < out.index("Bea Paper")
    assert "coauthor" not in out


def test_pubs_coauthor_outranks_the_same_keyword_overlap() -> None:
    posting = "coastal governance methods"
    keyword = Person(name="Ada Keywords", company="Other", keywords="coastal governance")
    pubs_person = Person(name="Bea Paper", company="Other", keywords="coastal governance")
    plain = rank(posting, [keyword, pubs_person])
    boosted = rank(
        posting,
        note_pubs_coauthors(
            [keyword, pubs_person],
            ["Bea Paper co-wrote the coastal note."],
        ),
    )
    assert [item.name for item in plain] == ["Ada Keywords", "Bea Paper"]
    assert boosted[0].name == "Bea Paper"
    assert "coauthor" in boosted[0].why


def test_could_speak_to_cites_a_selected_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    corpus = Corpus(tmp_path / "evidence.db")
    _seed(corpus)
    corpus.close()
    people = tmp_path / "people.json"
    people.write_text(
        """
        [{"name": "Ada Workshop", "company": "Other", "keywords": "ocean workshop",
          "jobTitle": "Facilitator"}]
        """,
        encoding="utf-8",
    )
    posting = tmp_path / "posting.txt"
    posting.write_text(POSTING, encoding="utf-8")
    assert main(
        ["referees", "--posting", str(posting), "--people", str(people)]
    ) == 0
    out = capsys.readouterr().out
    assert "could speak to: Drafted the ocean workshop" in out
    assert "confirm before listing" in out
