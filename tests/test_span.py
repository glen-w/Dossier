from pathlib import Path

from dossier.cards import STATUS_APPROVED, STATUS_PENDING, ClaimCard, carrying_span, evidence_carries
from dossier.cli import main
from dossier.show import defend_cards, find_span, gap_report, render_packet, write_packet
from dossier.store import Corpus, Record


def _record(uri: str, text: str, title: str = "Note") -> Record:
    return Record(id=uri, source="slack", uri=uri, title=title, text=text)


def test_span_returns_the_sentence_that_carries_the_claim() -> None:
    text = (
        "Ships sailed east that year. "
        "Glen wrote a synthetic paper on coastal governance."
    )
    span = carrying_span("synthetic paper on coastal governance", text)
    assert span == "Glen wrote a synthetic paper on coastal governance."


def test_split_tokens_pass_the_record_and_fail_the_sentence() -> None:
    text = "Alpha sailed east. Bravo stayed west. Charlie wrote notes. Delta kept records."
    claim = "alpha bravo charlie delta"
    assert evidence_carries(claim, text)
    assert carrying_span(claim, text) == ""


def test_header_line_is_not_a_span() -> None:
    text = "Lens: delivered\nKind: chapter\n"
    assert carrying_span("delivered chapter", text) == ""


def test_find_span_picks_the_shorter_sentence(corpus: Corpus) -> None:
    corpus.upsert_record(
        _record(
            "slack://long",
            "Glen wrote a very long synthetic paper on coastal governance and reefs.",
            title="Long",
        )
    )
    corpus.upsert_record(
        _record("slack://short", "Coastal governance paper.", title="Short")
    )
    shown = find_span(corpus, "coastal governance paper")
    assert shown is not None
    assert shown.uri == "slack://short"
    assert shown.title == "Short"


def test_defend_stores_span_and_keeps_approved(corpus: Corpus) -> None:
    rec = _record(
        "slack://1",
        "Glen wrote a synthetic paper on coastal governance. Ships sailed.",
    )
    corpus.upsert_record(rec)
    card = ClaimCard(
        id="card-1",
        claim="synthetic paper on coastal governance",
        citations=[rec.uri],
        source="slack",
        status=STATUS_APPROVED,
    )
    corpus.put_card(card)
    spanned, unspanned = defend_cards(corpus)
    assert unspanned == []
    assert spanned[0].status == STATUS_APPROVED
    loaded = corpus.get_card("card-1")
    assert loaded is not None
    assert loaded.status == STATUS_APPROVED
    assert "coastal governance" in loaded.extras["span"]
    assert loaded.extras["span_uri"] == rec.uri


def test_missing_citation_is_unspanned_and_unstored(corpus: Corpus) -> None:
    card = ClaimCard(
        id="card-2",
        claim="synthetic paper on coastal governance",
        citations=["missing://nope"],
        source="slack",
        status=STATUS_PENDING,
    )
    corpus.put_card(card)
    spanned, unspanned = defend_cards(corpus)
    assert spanned == []
    assert unspanned[0].id == "card-2"
    loaded = corpus.get_card("card-2")
    assert loaded is not None
    assert "span" not in loaded.extras
    assert loaded.status == STATUS_PENDING


def test_gaps_counts_lenses_and_lists_empty(corpus: Corpus) -> None:
    corpus.upsert_record(
        _record(
            "slack://1",
            "Lens: delivered\nKind: chapter\nDrafted the ocean chapter for the report.",
        )
    )
    report = gap_report(corpus)
    assert report.lens_counts["delivered"] == 1
    assert report.lens_counts["skills"] == 0
    assert "skills" in report.empty_lenses
    assert "contributions" in report.empty_lenses
    assert report.kind_counts["chapter"] == 1


def test_gaps_lists_a_single_spanned_card(corpus: Corpus) -> None:
    rec = _record(
        "slack://1",
        "Lens: delivered\nKind: chapter\nDrafted the ocean chapter for the report.",
    )
    corpus.upsert_record(rec)
    one = ClaimCard(
        id="only",
        claim="Drafted the ocean chapter",
        citations=[rec.uri],
        source="slack",
        status=STATUS_APPROVED,
        extras={"span": "Drafted the ocean chapter for the report.", "span_uri": rec.uri},
    )
    other = ClaimCard(
        id="pair-a",
        claim="Drafted the ocean chapter again",
        citations=[rec.uri],
        source="slack",
        status=STATUS_APPROVED,
        extras={
            "span": "Drafted the ocean chapter for the report.",
            "span_uri": rec.uri,
            "lens": "skills",
            "kind": "editing",
        },
    )
    twin = ClaimCard(
        id="pair-b",
        claim="Edited the ocean chapter",
        citations=[rec.uri],
        source="slack",
        status=STATUS_APPROVED,
        extras={
            "span": "Drafted the ocean chapter for the report.",
            "span_uri": rec.uri,
            "lens": "skills",
            "kind": "editing",
        },
    )
    for card in (one, other, twin):
        corpus.put_card(card)
    singles = {(line.lens, line.kind, line.card.id) for line in gap_report(corpus).singles}
    assert ("delivered", "chapter", "only") in singles
    assert not any(line[2] in {"pair-a", "pair-b"} for line in singles)


def test_packet_quotes_spanned_cards_and_lists_the_rest(corpus: Corpus, tmp_path: Path) -> None:
    quoted = ClaimCard(
        id="yes",
        claim="Drafted the ocean chapter",
        citations=["slack://1"],
        source="slack",
        status=STATUS_APPROVED,
        extras={
            "span": "Drafted the ocean chapter for the report.",
            "span_uri": "slack://1",
            "lens": "delivered",
            "kind": "chapter",
        },
    )
    bare = ClaimCard(
        id="no",
        claim="Convened a workshop",
        citations=["slack://2"],
        source="slack",
        status=STATUS_APPROVED,
    )
    corpus.put_card(quoted)
    corpus.put_card(bare)
    text = render_packet(corpus)
    assert "> Drafted the ocean chapter for the report." in text
    assert "citation: slack://1" in text
    assert "Convened a workshop" in text.split("# Not included", 1)[1]
    assert "> Convened" not in text
    path = write_packet(corpus, tmp_path / "packets")
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == "prompts: none\n" + text


def test_cli_span_refuses_when_no_sentence(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(_record("slack://1", "Ships sailed east that year."))
    corpus.close()
    assert main(["span", "coastal governance paper"]) == 1
    out = capsys.readouterr().out
    assert "refused" in out
    assert "no sentence carries this claim" in out


def test_span_uri_ignores_other_records(corpus: Corpus) -> None:
    corpus.upsert_record(_record("slack://short", "Coastal governance paper.", title="Short"))
    corpus.upsert_record(
        _record(
            "slack://other",
            "Glen wrote a synthetic paper on coastal governance.",
            title="Other",
        )
    )
    shown = find_span(corpus, "coastal governance paper", uri="slack://other")
    assert shown is not None
    assert shown.uri == "slack://other"


def test_defend_keeps_the_first_carrying_citation_and_other_extras(corpus: Corpus) -> None:
    weak = _record("slack://weak", "Ships sailed east that year.")
    strong = _record(
        "slack://strong",
        "Glen wrote a synthetic paper on coastal governance.",
    )
    corpus.upsert_record(weak)
    corpus.upsert_record(strong)
    card = ClaimCard(
        id="ordered",
        claim="synthetic paper on coastal governance",
        citations=[weak.uri, strong.uri],
        source="slack",
        status=STATUS_PENDING,
        extras={"org": "REN21", "lens": "delivered"},
    )
    corpus.put_card(card)
    defend_cards(corpus)
    loaded = corpus.get_card("ordered")
    assert loaded is not None
    assert loaded.status == STATUS_PENDING
    assert loaded.extras["span_uri"] == strong.uri
    assert loaded.extras["org"] == "REN21"
    assert loaded.extras["lens"] == "delivered"
    defend_cards(corpus)
    again = corpus.get_card("ordered")
    assert again is not None
    assert again.extras["org"] == "REN21"
    assert again.extras["span_uri"] == strong.uri


def test_defend_leaves_refused_cards_alone(corpus: Corpus) -> None:
    rec = _record("slack://1", "Glen wrote a synthetic paper on coastal governance.")
    corpus.upsert_record(rec)
    card = ClaimCard(
        id="refused-1",
        claim="synthetic paper on coastal governance",
        citations=[rec.uri],
        source="slack",
        status="refused",
        reason="left refused",
    )
    corpus.put_card(card)
    spanned, unspanned = defend_cards(corpus)
    assert spanned == []
    assert unspanned == []
    loaded = corpus.get_card("refused-1")
    assert loaded is not None
    assert loaded.status == "refused"
    assert "span" not in loaded.extras


def test_cli_defend_prints_unspanned_and_span_filters(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(
        _record("slack://1", "Glen wrote a synthetic paper on coastal governance.")
    )
    corpus.put_card(
        ClaimCard(
            id="missing",
            claim="synthetic paper on coastal governance",
            citations=["missing://nope"],
            source="slack",
            status=STATUS_PENDING,
        )
    )
    corpus.close()
    assert main(["defend"]) == 0
    out = capsys.readouterr().out
    assert "unspanned missing" in out
    assert main(["span", "--source", "mbox", "coastal governance paper"]) == 1
    assert main(["span", ""]) == 1
    err = capsys.readouterr().out
    assert "empty claim" in err
