"""Question packs for dossier brief. The career pack ships in code."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


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
