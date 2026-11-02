"""Shared caps, header regex, and lens/kind helpers."""

from __future__ import annotations

import re

from dossier.cards import header_values

TEXT_CAP = 8_000
TEXT_CAP_OFFICE = 20_000
HEADER_RE = re.compile(
    r"^(Lens|Kind|Org|Year|Skills|Artifacts|People|Hunt):\s*(.*)$",
    re.I,
)


def with_lens_kind(text: str, lens: str = "delivered", kind: str = "note") -> str:
    """Prefix Lens/Kind headers when the adapter did not write them."""
    body = (text or "").strip()
    if HEADER_RE.search(body):
        return body[:TEXT_CAP]
    return f"Lens: {lens}\nKind: {kind}\n\n{body}"[:TEXT_CAP]


def lens_kind(text: str, extras: dict[str, str] | None = None) -> tuple[str, str]:
    extras = extras or {}
    lens = (extras.get("lens") or "").strip().lower()
    kind = (extras.get("kind") or "").strip().lower()
    if not lens:
        values = header_values(text, "Lens")
        lens = values[0] if values else ""
    if not kind:
        values = header_values(text, "Kind")
        kind = values[0] if values else ""
    return lens, kind
