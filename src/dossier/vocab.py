"""GUI labels and short blurbs for the workbench.

Docs authority: docs/vocab.md. Keep these strings aligned with that page.
"""

from __future__ import annotations

# Primary nav. Rooms are layout groups; every key is still its own URL.
NAV_ROOMS = (
    ("Prepare", ("locker", "sources", "extract", "index")),
    ("Decide", ("review", "gaps")),
    ("Use", ("ask", "match", "tailor", "packet", "brief", "run")),
    ("Settings", ("settings",)),
)

NAV = tuple((key, key.replace("_", " ").title()) for _room, keys in NAV_ROOMS for key in keys)

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
    "match": "Match",
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
    "match": "Ordered evidence for each requirement in a pasted job spec.",
    "tailor": "CV or letter markdown from spanned approved cards.",
    "packet": "Markdown of spanned approved cards.",
    "gaps": "Empty lenses, unspanned cards, and records still waiting on extract.",
    "settings": "Common knobs. Phrase lists and the rest of the file stay in the gitignored dossier.toml.",
    "effort": "How hard the model should try: light, balanced, or high. Balanced uses a fast model for extract and the answer model for ask. Light drafts without a model. High uses the answer model for both.",
    "profile": "A named overlay of tunable knobs. Not identity.",
    "scope": "Sources, years, and effort for one request. Settings and profiles hold the defaults.",
    "prompt": "A versioned template for extract, ask, or tailor. A pack is a list of questions, not a prompt.",
    "pack": "A list of questions for a brief. Not a prompt.",
    "egress": "Text leaves the machine only when a remote LLM is opted in.",
    "locker_busy": "The locker is busy with another job.",
}

# Query-string err= keys → human lines (unknown keys pass through).
ERR = {
    "busy": "The locker is busy with another job.",
    "empty": "Ask needs a non-empty question.",
    "limit": "Limit must be a positive integer.",
    "year range": "Year from must be less than or equal to year to.",
    "Paste a job spec": "Paste a job spec before matching.",
    "max_calls": "max_calls must be zero (unlimited) or a positive integer.",
    "default": "Could not restore the default profile.",
}


def label(key: str) -> str:
    return LABELS.get(key, key.replace("_", " ").title())


def blurb(key: str) -> str:
    return BLURBS.get(key, "")


def err_message(key: str) -> str:
    if not key:
        return ""
    from urllib.parse import unquote

    cleaned = unquote(key)
    return ERR.get(cleaned, cleaned)