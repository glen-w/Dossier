"""The next useful step on the result loop. Does not run that step."""

from __future__ import annotations

from dossier.match import GAP_BROAD, GAP_NONE


def next_step(
    *,
    records: int,
    pending: int,
    approved: int,
    spanned: int,
    vectors: int,
    detected: int,
    reason: str = "",
) -> tuple[str, str]:
    """Return (path, sentence). Reason narrows the locker counts."""
    text = reason.strip().lower()
    if "empty question" in text:
        return "/ask", "Ask needs a non-empty question."
    if GAP_BROAD in text or "too broad" in text:
        return "/match", "Narrow the requirement. Generic words are not evidence."
    if "no matching records" in text:
        if records < 1:
            return "/sources", "Ingest a source you have."
        if vectors < 1:
            return "/index", "Index passages, then ask again."
        return "/sources", "Widen scope or ingest another source."
    if GAP_NONE in text or "no carrying" in text or "no direct span" in text:
        if pending:
            return "/review", "Review pending cards, then defend the ones you keep."
        if approved and spanned < approved:
            return "/review", "Defend approved cards so a sentence is stored."
        if records < 1:
            return "/sources", "Ingest a source you have."
        return "/extract", "Extract claim cards from records that have none."
    if "no cited" in text or "citation" in text:
        return "/extract", "Extract again. A claim needs a citation the record can carry."
    return _from_counts(
        records=records,
        pending=pending,
        approved=approved,
        spanned=spanned,
        vectors=vectors,
        detected=detected,
    )


def _from_counts(
    *,
    records: int,
    pending: int,
    approved: int,
    spanned: int,
    vectors: int,
    detected: int,
) -> tuple[str, str]:
    if records < 1 and detected < 1:
        return "/sources", "Turn on a source you have, then ingest it."
    if records < 1:
        return "/sources", "Ingest a detected source."
    if pending:
        return "/review", f"Review {pending} pending card{'s' if pending != 1 else ''}."
    if approved and spanned < approved:
        missing = approved - spanned
        return (
            "/review",
            f"Defend {missing} approved card{'s' if missing != 1 else ''} so tailor can quote.",
        )
    if records and vectors < 1:
        return "/index", "Index passages so a thin ask can find a neighbor."
    if spanned:
        return "/match", "Match a job spec, then tailor a CV or letter."
    return "/extract", "Extract claim cards from the records already in the locker."
