"""Property tests for the carrying-sentence contract. Synthetic text only."""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dossier.cards import (
    STATUS_APPROVED,
    STATUS_REFUSED,
    ClaimCard,
    adjudicate,
    card_id,
    carrying_span,
    content_tokens,
    current_span,
    evidence_carries,
    span_in_text,
    span_max,
)
from dossier.eval import ExactConfig
from dossier.interview import conduct
from dossier.llm.client import NullLLMClient
from dossier.show import defend_cards, render_packet
from dossier.store import Corpus, Record
from dossier.tailor import render_draft, select_cards

WORDS = [
    "quinn", "coastal", "governance", "kelp", "restoration", "workshop", "paper",
    "harbour", "survey", "marsh", "cable", "forum", "charter", "delegates", "ocean",
    "held", "work", "role", "the", "and", "of", "in", "a",
]
word = st.sampled_from(WORDS)
sentence = st.lists(word, min_size=1, max_size=14).map(lambda ws: " ".join(ws).capitalize() + ".")
body = st.lists(sentence, min_size=1, max_size=8).map(" ".join)
question = st.lists(word, min_size=0, max_size=10).map(" ".join)
noisy = st.text(alphabet="abcdefghijklmnopqrstuvwxyz.!? \n\"'()@:-*", max_size=600)


def _locker(texts: list[str]) -> Corpus:
    tmp = Path(tempfile.mkdtemp())
    corpus = Corpus(tmp / "evidence.db")
    for index, text in enumerate(texts):
        corpus.upsert_record(
            Record(
                id=f"r{index}",
                source="slack",
                uri=f"prop://{index}",
                title=f"Note {index}",
                text=text,
            )
        )
    return corpus


@given(claim=question, text=body)
@settings(max_examples=60, deadline=None)
def test_span_is_a_paste_sized_quote_that_carries_the_claim(claim: str, text: str) -> None:
    span = carrying_span(claim, text)
    if span:
        assert len(span) <= span_max()
        assert span_in_text(span, text)
        assert content_tokens(claim)


@given(claim=noisy, text=noisy)
@settings(max_examples=60, deadline=None)
def test_span_never_escapes_the_record_on_noisy_text(claim: str, text: str) -> None:
    span = carrying_span(claim, text)
    if span:
        assert len(span) <= span_max()
        assert span_in_text(span, text)


@given(claim=st.text(max_size=120), texts=st.lists(body, min_size=0, max_size=3))
@settings(max_examples=60, deadline=None)
def test_a_claim_with_no_content_words_is_always_refused(claim: str, texts: list[str]) -> None:
    if content_tokens(claim):
        return
    evidence = {f"prop://{i}": text for i, text in enumerate(texts)}
    status, _reason = adjudicate(claim, list(evidence), evidence)
    assert status == STATUS_REFUSED


@given(claim=question, uri=st.text(alphabet="xyz:/", max_size=8))
@settings(max_examples=40, deadline=None)
def test_an_uncited_or_unknown_citation_is_refused(claim: str, uri: str) -> None:
    status, _ = adjudicate(claim, [], {})
    assert status == STATUS_REFUSED
    status, _ = adjudicate(claim, [uri], {})
    assert status == STATUS_REFUSED


@given(texts=st.lists(body, min_size=1, max_size=5), asked=question)
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_ask_cites_only_what_exists_and_never_overruns(texts: list[str], asked: str) -> None:
    corpus = _locker(texts)
    try:
        known = {rec.uri for rec in corpus.records()}
        answer = conduct(corpus, asked, ExactConfig(), NullLLMClient(), mode="exact", limit=5)
        assert set(answer.citations) <= known
        if answer.refused:
            assert answer.reason
            if answer.reason != "incomplete":
                assert answer.citations == []
        else:
            assert answer.citations
            assert len(answer.text) <= span_max() * 4
    finally:
        corpus.close()


@given(texts=st.lists(body, min_size=1, max_size=4), claims=st.lists(question, min_size=1, max_size=4))
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_everything_pasted_is_a_current_span_under_the_cap(
    texts: list[str], claims: list[str]
) -> None:
    corpus = _locker(texts)
    try:
        for index, claim in enumerate(claims):
            uri = f"prop://{index % len(texts)}"
            corpus.put_card(
                ClaimCard(
                    id=card_id(claim or "x", [uri]),
                    claim=claim or "x",
                    citations=[uri],
                    source="slack",
                    status=STATUS_APPROVED,
                )
            )
        defend_cards(corpus)
        records = {rec.uri: rec.text for rec in corpus.records()}
        packet = render_packet(corpus)
        quotes = [line[2:] for line in packet.splitlines() if line.startswith("> ")]
        for quote in quotes:
            assert len(quote) <= span_max()
            assert any(span_in_text(quote, text) for text in records.values())
        picked, _bare = select_cards(corpus, " ".join(WORDS), limit=8)
        spans = {item.card.extras["span"].strip() for item in picked}
        for item in picked:
            assert current_span(corpus, item.card)
        letter = render_draft(kind="letter", posting="x", picked=picked, bare=[])
        prose = letter.split("# Coverage", 1)[0]
        for line in prose.splitlines():
            if line.strip() and not line.startswith("#"):
                assert line in spans
    finally:
        corpus.close()


@given(extra=st.sampled_from(["lunar", "everest", "quantum", "reactor"]))
@settings(max_examples=8, deadline=None)
def test_an_unsupported_specific_word_is_refused(extra: str) -> None:
    evidence = "Quinn wrote a synthetic paper on coastal governance."
    assert evidence_carries("synthetic paper on coastal governance", evidence)
    assert not evidence_carries(f"synthetic paper on coastal governance {extra}", evidence)


@given(value=st.one_of(st.none(), st.integers(), st.floats(allow_nan=False, allow_infinity=False),
                       st.text(max_size=12), st.booleans(), st.lists(st.integers(), max_size=2)))
@settings(max_examples=80, deadline=None)
def test_to_int_never_raises(value: object) -> None:
    from dossier.util import to_int

    assert isinstance(to_int(value), int)
    assert to_int(value, default=-7) is not None
