from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from dossier.cards import carrying_span, evidence_carries, span_max
from dossier.drafts import _first_body


def test_first_body_takes_a_sentence_not_a_file() -> None:
    line = "Coastal governance paper. " + ("kelp " * 400)
    text = f"Lens: delivered\n{line}"
    first = _first_body(text)
    assert first
    assert len(first) <= span_max()
    assert "Coastal governance paper" in first


@given(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz. \n", min_size=1, max_size=800),
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz. \n", min_size=1, max_size=400),
)
@settings(max_examples=40, deadline=None)
def test_carrying_span_never_exceeds_cap(claim: str, text: str) -> None:
    span = carrying_span(claim, text)
    assert len(span) <= span_max()
    if span:
        assert evidence_carries(claim, span)
