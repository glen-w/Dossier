"""Claim cards. Refuse a claim the records will not carry (CareerForge rule)."""

from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass, field

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REFUSED = "refused"

# Paste-sized sentence. A stored span longer than this is not a span.
DEFAULT_SPAN_MAX = 320

_STOP = frozenset(
    {
        "that",
        "this",
        "with",
        "from",
        "have",
        "been",
        "were",
        "they",
        "their",
        "them",
        "into",
        "over",
        "under",
        "about",
        "which",
        "while",
        "where",
        "when",
        "your",
        "ours",
        "also",
        "than",
        "then",
        "some",
        "such",
        "only",
        "just",
        "very",
        "more",
        "most",
        "other",
        "what",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "there",
        "here",
        "like",
    }
)

# Words that show up in almost any export. Sharing one of them is not an answer.
GENERIC_TOKENS = frozenset(
    {
        "held",
        "work",
        "deliver",
        "delivered",
        "record",
        "records",
        "show",
        "shown",
        "recorded",
        "publish",
        "published",
        "role",
        "roles",
        "skill",
        "skills",
        "contribution",
        "contributions",
        "paper",
        "chapter",
        "report",
        "notes",
        "note",
        "file",
        "files",
        "text",
        "year",
        "years",
        "experience",
        "leading",
        "knowledge",
        "ability",
        "proven",
        "responsible",
    }
)


def token_covered(token: str, blob: set[str]) -> bool:
    """True when the evidence has this word, or the same word with one letter changed.

    `write` covers `wrote`. `drafting` covers `drafted`. An extra noun such as `lunar` still does not.
    """
    if token in blob:
        return True
    for other in blob:
        if len(other) == len(token) and sum(
            left != right for left, right in zip(token, other, strict=True)
        ) == 1:
            return True
        shared = 0
        for left, right in zip(token, other, strict=False):
            if left != right:
                break
            shared += 1
        if shared >= 5:
            return True
    return False

_ABBREV = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "sr",
        "jr",
        "vs",
        "etc",
        "al",
        "fig",
        "eq",
        "vol",
        "no",
        "pp",
        "ed",
        "eds",
        "inc",
        "ltd",
        "approx",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "sept",
        "oct",
        "nov",
        "dec",
        "st",
        "nd",
        "rd",
        "th",
        "e.g",
        "i.e",
        "u.s",
        "u.k",
    }
)


@dataclass(frozen=True)
class ClaimCard:
    id: str
    claim: str
    citations: list[str]
    source: str
    status: str
    reason: str = ""
    record_id: str = ""
    extras: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProposedClaim:
    claim: str
    citations: list[str]
    extras: dict[str, str] = field(default_factory=dict)


def span_max() -> int:
    """Hard cap for a stored carrying sentence."""
    raw = os.environ.get("DOSSIER_EXTRACT_SPAN_MAX", "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = DEFAULT_SPAN_MAX
        return max(40, value)
    return DEFAULT_SPAN_MAX


def card_id(claim: str, citations: list[str]) -> str:
    key = claim.strip() + "\0" + "\0".join(citations)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def content_tokens(text: str) -> list[str]:
    """Words long enough to match a record. Shared by the locker and ask."""
    return [
        w
        for w in re.findall(r"[a-z0-9]+", text.lower())
        if len(w) >= 4 and w not in _STOP
    ]


def content_token_set(text: str) -> set[str]:
    return set(content_tokens(text))


def specific_tokens(text: str) -> list[str]:
    """Content tokens that are not generic filler."""
    return [token for token in content_tokens(text) if token not in GENERIC_TOKENS]


_HEADER_LINE = re.compile(
    r"^(Lens|Kind|Org|Year|Skills|Artifacts|People|Hunt):",
    re.I,
)


def header_values(text: str, key: str) -> list[str]:
    """Values on the first `Key:` line. Seeker headers are a closed set."""
    prefix = key.lower() + ":"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith(prefix):
            raw = stripped.split(":", 1)[1]
            return [part.strip().lower() for part in raw.split(",") if part.strip()]
    return []


def _is_abbrev(token: str) -> bool:
    stripped = token.rstrip(".").lower()
    return stripped in _ABBREV or (len(stripped) == 1 and stripped.isalpha())


def _split_line(line: str) -> list[str]:
    """Split one line on terminal punctuation, keeping abbreviations together."""
    parts: list[str] = []
    start = 0
    i = 0
    length = len(line)
    while i < length:
        ch = line[i]
        if ch in ".!?" :
            nxt = i + 1
            while nxt < length and line[nxt] in ".!?\"'”’)":
                nxt += 1
            rest = line[nxt:]
            if ch == ".":
                before = line[start:i]
                last = before.rsplit(None, 1)
                word = last[-1] if last else ""
                if _is_abbrev(word):
                    i = nxt
                    continue
                if rest and rest[0].islower():
                    i = nxt
                    continue
            if rest and not rest[0].isspace() and rest[0] not in "\"'”’)":
                i += 1
                continue
            chunk = line[start:nxt].strip()
            if chunk:
                parts.append(chunk)
            start = nxt
            i = nxt
            continue
        i += 1
    tail = line[start:].strip()
    if tail:
        parts.append(tail)
    return parts or ([line.strip()] if line.strip() else [])


def sentences(text: str, *, cap: int | None = None) -> list[str]:
    """Non-header sentences. A header line is not a span. Over-cap chunks drop."""
    limit = span_max() if cap is None else cap
    body: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or _HEADER_LINE.match(stripped):
            continue
        body.extend(_split_line(stripped))
    return [part for part in body if part and len(part) <= limit]


def carrying_span(claim: str, text: str, *, cap: int | None = None) -> str:
    """The shortest sentence that carries the claim, or empty.

    Stricter than `evidence_carries` on the whole record: the words must
    sit in one sentence under the span cap. Ties keep the earlier sentence.
    """
    limit = span_max() if cap is None else cap
    best = ""
    best_score = -1
    best_len = 0
    tokens = content_tokens(claim)
    if not tokens:
        return ""
    for sentence in sentences(text, cap=limit):
        if not evidence_carries(claim, sentence):
            continue
        blob = content_token_set(sentence)
        score = sum(1 for token in tokens if token in blob)
        length = len(sentence)
        if score > best_score or (score == best_score and (not best or length < best_len)):
            best = sentence
            best_score = score
            best_len = length
    if len(best) > limit:
        return ""
    return best


def evidence_carries(claim: str, evidence: str) -> bool:
    """True when evidence text can carry the claim without an LLM.

    Match whole words. A token inside a longer word does not count.
    A claim with no content words is refused. Short claims still need
    about half their tokens. Every specific (non-generic) token must be
    covered by the evidence, including a one-letter difference such as
    write and wrote. One supported word does not carry an extra noun
    the record never uses. Generic tokens, including requirement cues
    such as experience and knowledge, may still overlap in part.
    """
    if not evidence.strip():
        return False
    tokens = content_tokens(claim)
    if not tokens:
        return False
    blob = content_token_set(evidence)
    hits = sum(1 for token in tokens if token in blob)
    specific = [token for token in tokens if token not in GENERIC_TOKENS]
    if len(tokens) == 1:
        return bool(specific) and hits == 1
    if len(tokens) <= 8:
        need = max(2, math.ceil(len(tokens) * 0.5))
    else:
        need = max(3, math.ceil(len(tokens) * 0.4))
    if hits < need:
        return False
    if specific and not all(token_covered(token, blob) for token in specific):
        return False
    return True


def span_is_usable(claim: str, span: str, *, cap: int | None = None) -> bool:
    """True when a stored span is still a paste-sized carrying sentence."""
    limit = span_max() if cap is None else cap
    text = span.strip()
    if not text or len(text) > limit:
        return False
    return evidence_carries(claim, text)


def span_in_text(span: str, text: str) -> bool:
    """True when the span is still written in the record text (whitespace-insensitive)."""
    needle = " ".join(span.split())
    if not needle:
        return False
    return needle in " ".join(text.split())


def current_span(corpus: object, card: ClaimCard) -> str:
    """The stored span when it is paste-sized, carries the claim, and is still in its record.

    Empty otherwise. A re-ingest that changed the cited record makes the span stale,
    so nothing is pasted from it until `defend --refresh` re-spans the card.
    """
    span = (card.extras.get("span") or "").strip()
    if not span or not span_is_usable(card.claim, span):
        return ""
    uri = (card.extras.get("span_uri") or "").strip()
    uris = [uri] if uri else list(card.citations)
    get_record = getattr(corpus, "get_record", None)
    if get_record is None:
        return span
    for candidate in uris:
        rec = get_record(candidate)
        if rec is not None and span_in_text(span, rec.text):
            return span
    return ""


def adjudicate(
    claim: str,
    citations: list[str],
    evidence_by_uri: dict[str, str],
) -> tuple[str, str]:
    """Return (status, reason). pending if the records carry the claim, else refused."""
    text = claim.strip()
    if not text:
        return STATUS_REFUSED, "empty claim"
    tokens = content_tokens(text)
    if not tokens:
        return STATUS_REFUSED, "claim has no content words"
    if len(text) > span_max() * 4:
        return STATUS_REFUSED, "claim is too long to paste"
    uris = [u.strip() for u in citations if u and str(u).strip()]
    if not uris:
        return STATUS_REFUSED, "no citations"
    chunks: list[str] = []
    for uri in uris:
        body = (evidence_by_uri.get(uri) or "").strip()
        if not body:
            return STATUS_REFUSED, f"citation missing or empty: {uri}"
        chunks.append(body)
    if not evidence_carries(text, "\n".join(chunks)):
        return STATUS_REFUSED, "evidence will not carry this claim"
    return STATUS_PENDING, ""
