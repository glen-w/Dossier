"""Turn a hit plus fetched text into a corpus record."""

from __future__ import annotations

from dossier.seekers.hits import Hit
from dossier.store import Record
from dossier.util import record_id

TEXT_CAP = 8000


def format_snippet(hit: Hit, body: str) -> str:
    lines = [
        f"Lens: {', '.join(hit.lenses)}",
        f"Kind: {hit.kind}",
        f"Org: {hit.org}" if hit.org else "",
        f"Year: {hit.year}" if hit.year else "",
        f"Skills: {', '.join(hit.skills)}" if hit.skills else "",
        f"Artifacts: {', '.join(hit.artifacts)}" if hit.artifacts else "",
        f"People: {', '.join(hit.people)}" if hit.people else "",
        f"Hunt: {', '.join(hit.hunts)}",
        "",
        (body.strip() or hit.preview).strip(),
    ]
    text = "\n".join(line for line in lines if line is not None)
    return text[:TEXT_CAP]


def record_from_hit(hit: Hit, body: str) -> Record:
    return Record(
        id=record_id(hit.uri),
        source=hit.source,
        uri=hit.uri,
        title=hit.title,
        text=format_snippet(hit, body),
        table=f"{hit.source}.hits",
    )
