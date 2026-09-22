"""GUI labels and short blurbs for the workbench.

Docs authority: docs/vocab.md. Keep these strings aligned with that page.
"""

from __future__ import annotations

# Primary nav (wave 1).
NAV = (
    ("locker", "Locker"),
    ("sources", "Sources"),
    ("extract", "Extract"),
    ("review", "Review"),
    ("ask", "Ask"),
    ("settings", "Settings"),
)

LABELS = {
    "locker": "Locker",
    "warehouse": "Warehouse",
    "source": "Source",
    "sources": "Sources",
    "ingest": "Ingest",
    "seek": "Seek",
    "fetch": "Fetch",
    "record": "Record",
    "passage": "Passage",
    "extract": "Extract",
    "draft": "Draft",
    "card": "Card",
    "lens": "Lens",
    "kind": "Kind",
    "review": "Review",
    "span": "Span",
    "defend": "Defend",
    "packet": "Packet",
    "ask": "Ask",
    "pack": "Pack",
    "brief": "Brief",
    "tailor": "Tailor",
    "prove": "Prove",
    "run": "Run",
    "effort": "Effort",
    "profile": "Profile",
    "identity": "Identity",
    "prompt": "Prompt",
    "settings": "Settings",
}

BLURBS = {
    "locker": "Local evidence store (evidence.db) and the host process around it.",
    "sources": "Registered adapters. Ingest copies their text into the locker.",
    "extract": "Propose claim cards from records already in the locker.",
    "review": "Human gate: approve, refuse, or reopen cards.",
    "ask": "One cited answer from the locker, or a refusal.",
    "settings": "Common knobs. Full config stays in the gitignored dossier.toml.",
    "effort": "How hard the model should try: light, balanced, or high.",
    "profile": "A named overlay of tunable knobs. Not identity.",
    "egress": "Text leaves the machine only when a remote LLM is opted in.",
    "locker_busy": "The locker is busy with another job.",
}


def label(key: str) -> str:
    return LABELS.get(key, key.replace("_", " ").title())


def blurb(key: str) -> str:
    return BLURBS.get(key, "")
