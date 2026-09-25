"""Posting-shaped markdown from approved cards that already have a span."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dossier.cards import (
    STATUS_APPROVED,
    ClaimCard,
    content_token_set,
    header_values,
)
from dossier.lenses import infer_skills, kinds_mentioned
from dossier.llm.client import CompletionRequest, LLMClient, LLMClientError, ctx_tokens_for
from dossier.prompts import ARRANGE_BODY, active_prompt, render
from dossier.store import Corpus

CV_CAP = 8
LETTER_CAP = 4
GLUE = "I am applying for the role in the posting."
_ARRANGE = ARRANGE_BODY


@dataclass(frozen=True)
class Picked:
    card: ClaimCard
    lens: str
    kind: str
    score: int


def select_cards(corpus: Corpus, posting: str, *, limit: int) -> tuple[list[Picked], list[ClaimCard]]:
    """Spanned approved cards with posting overlap, and approved cards with no span."""
    posting_kinds = set(kinds_mentioned(posting))
    posting_skills = set(infer_skills(posting))
    posting_tokens = content_token_set(posting)
    picked: list[Picked] = []
    bare: list[ClaimCard] = []
    for card in corpus.cards(STATUS_APPROVED):
        span = (card.extras.get("span") or "").strip()
        if not span:
            bare.append(card)
            continue
        lens, kind = _lens_kind(corpus, card)
        score = _score(card, span, kind, posting_tokens, posting_kinds, posting_skills)
        if score <= 0:
            continue
        picked.append(Picked(card, lens, kind, score))
    picked.sort(key=lambda item: (-item.score, item.card.id))
    return picked[: max(0, limit)], bare


def linkedin_subtitle(corpus: Corpus) -> str:
    """The position heading when the corpus has exactly one."""
    titles = [
        rec.title.strip()
        for rec in corpus.records("linkedin")
        if rec.table == "linkedin.positions" or rec.uri.startswith("linkedin://positions/")
        if rec.title.strip()
    ]
    if len(titles) == 1:
        return titles[0]
    return ""


def render_draft(
    *,
    kind: str,
    posting: str,
    picked: list[Picked],
    bare: list[ClaimCard],
    name: str = "",
    subtitle: str = "",
    paragraphs: list[str] | None = None,
) -> str:
    lines = ["# Letter" if kind == "letter" else "# CV", ""]
    if name.strip():
        lines.extend([name.strip(), ""])
    if kind != "letter" and subtitle.strip():
        lines.extend([subtitle.strip(), ""])
    if kind == "letter":
        body = paragraphs if paragraphs else [item.card.extras["span"].strip() for item in picked]
        for paragraph in body:
            lines.extend([paragraph, ""])
    else:
        lines.extend(_cv_sections(picked))
    if bare:
        lines.extend(["# Not included", ""])
        for card in bare:
            lines.append(f"- {card.id}: {card.claim}")
        lines.append("")
    lines.extend(_coverage(posting, picked))
    return "\n".join(lines).rstrip() + "\n"


def write_draft(text: str, directory: Path, *, prompt_stamp: str = "prompts: none") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%y%m%d-%H%M%S")
    path = directory / f"{stamp}.md"
    if path.exists():
        stamp = datetime.now(UTC).strftime("%y%m%d-%H%M%S-%f")
        path = directory / f"{stamp}.md"
    body = text if text.startswith("prompts:") else f"{prompt_stamp.rstrip()}\n{text}"
    path.write_text(body, encoding="utf-8")
    return path


def arrange_letter(
    spans: list[str],
    client: LLMClient,
    model: str,
    *,
    max_num_ctx: int = 32_768,
    timeout_seconds: float = 300.0,
) -> list[str] | None:
    """One completion. Anything outside the spans and the glue line is a miss."""
    clean = [span.strip() for span in spans if span.strip()]
    if not clean:
        return None
    prompt = render(
        active_prompt("tailor_arrange"),
        {"SPANS": "\n".join(f"- {span}" for span in clean)},
    )
    try:
        data = client.complete_json(
            CompletionRequest(
                model=model,
                prompt=prompt,
                json_mode=True,
                num_ctx=ctx_tokens_for(prompt, max_num_ctx=max_num_ctx),
                timeout_seconds=timeout_seconds,
                think=False,
            )
        )
    except LLMClientError:
        return None
    raw = data.get("sentences") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return None
    return _accept(raw, clean)


def speak_to(profile: str, picked: list[Picked], *, limit: int = 2) -> list[str]:
    """Claims a referee's title, keywords, or company already overlap."""
    tokens = content_token_set(profile)
    if not tokens:
        return []
    claims: list[str] = []
    for item in picked:
        blob = content_token_set(f"{item.card.claim}\n{item.card.extras.get('span', '')}")
        if tokens & blob and item.card.claim not in claims:
            claims.append(item.card.claim)
        if len(claims) >= limit:
            break
    return claims


def _accept(raw: list, spans: list[str]) -> list[str] | None:
    allowed = set(spans)
    allowed.add(GLUE)
    out: list[str] = []
    for item in raw:
        text = str(item).strip()
        if not text or text not in allowed:
            return None
        if text not in out:
            out.append(text)
    if not any(sentence in spans for sentence in out):
        return None
    return out


def _cv_sections(picked: list[Picked]) -> list[str]:
    lines: list[str] = []
    groups: dict[str, list[Picked]] = {}
    for item in picked:
        groups.setdefault(item.lens or "other", []).append(item)
    for lens in sorted(groups):
        lines.extend([f"## {lens}", ""])
        for item in groups[lens]:
            span = item.card.extras["span"].strip()
            uri = (item.card.extras.get("span_uri") or "").strip() or (
                item.card.citations[0] if item.card.citations else ""
            )
            lines.append(f"- {item.card.claim}")
            lines.append("")
            lines.append(f"> {span}")
            lines.append("")
            if uri:
                lines.append(f"citation: {uri}")
                lines.append("")
    return lines


def _coverage(posting: str, picked: list[Picked]) -> list[str]:
    lines = ["# Coverage", ""]
    kind_hit, kind_miss = _split(
        kinds_mentioned(posting),
        lambda name: any(item.kind == name or _mentions(item, name) for item in picked),
    )
    skill_hit, skill_miss = _split(
        infer_skills(posting),
        lambda name: any(_mentions(item, name.replace("-", " ")) for item in picked),
    )
    lines.append("matched kinds: " + (", ".join(kind_hit) if kind_hit else "none"))
    for name in kind_miss:
        lines.append(f"empty kinds: {name} — defend or extract")
    lines.append("matched skills: " + (", ".join(skill_hit) if skill_hit else "none"))
    for name in skill_miss:
        lines.append(f"empty skills: {name} — defend or extract")
    lines.append("")
    return lines


def _split(names: tuple[str, ...], hit) -> tuple[list[str], list[str]]:
    yes: list[str] = []
    no: list[str] = []
    for name in names:
        if hit(name):
            yes.append(name)
        else:
            no.append(name)
    return yes, no


def _mentions(item: Picked, name: str) -> bool:
    blob = f"{item.card.claim}\n{item.card.extras.get('span', '')}".lower()
    return name.lower() in blob


def _score(
    card: ClaimCard,
    span: str,
    kind: str,
    posting_tokens: set[str],
    posting_kinds: set[str],
    posting_skills: set[str],
) -> int:
    blob = content_token_set(f"{card.claim}\n{span}")
    score = len(posting_tokens & blob)
    if kind and kind in posting_kinds:
        score += 3
    text = f"{card.claim} {span}".lower()
    if any(skill.replace("-", " ") in text for skill in posting_skills):
        score += 2
    return score


def _lens_kind(corpus: Corpus, card: ClaimCard) -> tuple[str, str]:
    lens = (card.extras.get("lens") or "").strip().lower()
    kind = (card.extras.get("kind") or "").strip().lower()
    if lens and kind:
        return lens, kind
    uri = (card.extras.get("span_uri") or "").strip()
    if not uri and card.citations:
        uri = card.citations[0]
    rec = corpus.get_record(uri) if uri else None
    if rec is None:
        return lens, kind
    if not lens:
        values = header_values(rec.text, "Lens")
        lens = values[0] if values else ""
    if not kind:
        values = header_values(rec.text, "Kind")
        kind = values[0] if values else ""
    return lens, kind
