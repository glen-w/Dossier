"""Question packs for dossier brief. The career pack ships in code."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dossier.cards import content_token_set, content_tokens
from dossier.lenses import infer_skills, kinds_mentioned
from dossier.paths import data_dir


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


def resolve_pack(spec: str, root: Path | None = None) -> list[PackQuestion]:
    """``career``, a saved name under ``$DOSSIER_DATA/packs``, or a JSON path."""
    if spec == "career":
        return list(CAREER)
    named = packs_dir(root) / f"{spec}.json"
    if named.is_file():
        return load_pack(str(named))
    return load_pack(spec)


def packs_dir(root: Path | None = None) -> Path:
    return (root or data_dir()) / "packs"


def list_saved_packs(root: Path | None = None) -> list[str]:
    folder = packs_dir(root)
    if not folder.is_dir():
        return []
    return sorted(path.stem for path in folder.glob("*.json"))


def questions_payload(questions: list[PackQuestion]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in questions:
        row = {"id": item.id, "question": item.question}
        if item.source:
            row["source"] = item.source
        if item.lens:
            row["lens"] = item.lens
        rows.append(row)
    return rows


def save_named_pack(name: str, raw: str, root: Path | None = None) -> list[PackQuestion]:
    cleaned = name.strip().lower()
    if cleaned in {"career", "posting", "default"}:
        raise ValueError(f"cannot overwrite {cleaned}")
    if not cleaned or not cleaned.replace("-", "").replace("_", "").isalnum():
        raise ValueError(f"invalid pack name {name!r}")
    folder = packs_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{cleaned}.json"
    path.write_text(raw.strip() + "\n", encoding="utf-8")
    try:
        return load_pack(str(path))
    except ValueError:
        path.unlink(missing_ok=True)
        raise


def delete_named_pack(name: str, root: Path | None = None) -> None:
    cleaned = name.strip().lower()
    if cleaned in {"career", "posting"}:
        raise ValueError(f"cannot delete {cleaned}")
    path = packs_dir(root) / f"{cleaned}.json"
    if path.is_file():
        path.unlink()


def _df(token: str, blobs: list[str]) -> int:
    return sum(1 for blob in blobs if token in content_token_set(blob))
