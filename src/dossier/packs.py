"""Question packs for dossier brief. The career pack ships in code."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dossier.cards import content_token_set, content_tokens
from dossier.lenses import infer_skills, kinds_mentioned


@dataclass(frozen=True)
class PackQuestion:
    id: str
    question: str
    source: str | None = None
    lens: str | None = None


CAREER: tuple[PackQuestion, ...] = (
    PackQuestion("roles", "What roles have I held?", source="linkedin"),
    PackQuestion("delivered", "What work did I deliver?", lens="delivered"),
    PackQuestion("skills", "What skills does the record show?", lens="skills"),
    PackQuestion("contributions", "What contributions are recorded?", lens="contributions"),
    PackQuestion("publications", "What did I publish?", source="linkedin"),
)


def load_pack(spec: str) -> list[PackQuestion]:
    if spec == "career":
        return list(CAREER)
    path = Path(spec).expanduser()
    if not path.is_file():
        raise ValueError(f"unknown pack {spec!r}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"pack {path} is not JSON") from exc
    if not isinstance(data, list) or not data:
        raise ValueError(f"pack {path} needs a list of questions")
    out: list[PackQuestion] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError(f"pack {path} has a non-object question")
        qid = str(item.get("id") or "").strip()
        question = str(item.get("question") or "").strip()
        if not qid or not question:
            raise ValueError(f"pack {path} needs id and question")
        source = str(item.get("source") or "").strip() or None
        lens = str(item.get("lens") or "").strip() or None
        out.append(PackQuestion(qid, question, source, lens))
    return out


def posting_pack(text: str) -> list[PackQuestion]:
    """Questions from kinds and skills already named in a local posting."""
    kinds = kinds_mentioned(text)
    skills = infer_skills(text)
    delivered = "What work did I deliver?"
    if kinds:
        delivered = "What delivered work matches " + " ".join(kinds[:4]) + "?"
    skills_q = "What skills does the record show?"
    if skills:
        shown = " ".join(skill.replace("-", " ") for skill in skills[:4])
        skills_q = f"What skills match {shown}?"
    return [
        PackQuestion("roles", "What roles have I held?", source="linkedin"),
        PackQuestion("delivered", delivered, lens="delivered"),
        PackQuestion("skills", skills_q, lens="skills"),
        PackQuestion("contributions", "What contributions are recorded?", lens="contributions"),
    ]


def follow_up(
    parent_id: str,
    question: str,
    blobs: list[str],
    *,
    source: str | None = None,
    lens: str | None = None,
) -> PackQuestion | None:
    """One closed follow-up from the rarest content token. No model."""
    tokens = content_tokens(question)
    if not tokens or parent_id.endswith("-follow"):
        return None
    scored = sorted(tokens, key=lambda token: (_df(token, blobs), -len(token), token))
    token = scored[0]
    return PackQuestion(
        f"{parent_id}-follow",
        f"which record mentions {token}?",
        source,
        lens,
    )


def _df(token: str, blobs: list[str]) -> int:
    return sum(1 for blob in blobs if token in content_token_set(blob))
