"""Split a record into passages. Headers stay on every chunk."""

from __future__ import annotations

import re

PASSAGE_CAP = 800
_HEADER = re.compile(
    r"^(Lens|Kind|Org|Year|Skills|Artifacts|People|Hunt):\s*",
    re.I,
)


def split_passages(text: str) -> list[str]:
    """Header block plus each paragraph. A short record stays one passage."""
    raw = text.strip()
    if not raw:
        return []
    lines = text.splitlines()
    headers: list[str] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if not _HEADER.match(stripped):
            break
        headers.append(stripped)
        index += 1
    rest = "\n".join(lines[index:]).strip()
    header = "\n".join(headers)
    if not rest:
        return [_cap(header or raw)]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", rest) if part.strip()]
    if len(paragraphs) == 1 and len(paragraphs[0]) <= PASSAGE_CAP and not header:
        return [paragraphs[0]]
    chunks: list[str] = []
    for paragraph in paragraphs or [rest]:
        chunks.extend(_pieces(paragraph))
    out: list[str] = []
    for chunk in chunks:
        piece = f"{header}\n\n{chunk}".strip() if header else chunk
        out.append(_cap(piece))
    return out or [_cap(raw)]


def _pieces(paragraph: str) -> list[str]:
    if len(paragraph) <= PASSAGE_CAP:
        return [paragraph]
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    chunks: list[str] = []
    buf = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if buf and len(buf) + 1 + len(sentence) > PASSAGE_CAP:
            chunks.append(buf)
            buf = sentence
        else:
            buf = f"{buf} {sentence}".strip()
    if buf:
        chunks.append(buf)
    return chunks or [_cap(paragraph)]


def _cap(text: str) -> str:
    return text.strip()[:PASSAGE_CAP]
