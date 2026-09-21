"""Local identities for seekers. No CRM. Override with env."""

from __future__ import annotations

import os
import re
from pathlib import Path

DEFAULT_SLACK_USER_IDS = ("U05E73N5733", "UUDS0NJ9W")
DEFAULT_SPEAKER_NAMES = ("Glen Wright", "Glen")

DEFAULT_MAIL_ACCOUNTS: dict[str, str] = {
    "glen.wright@sciencespo.fr": "iddri",
    "glen.w.wright@gmail.com": "gmail",
    "garedebao@gmail.com": "gdb",
}

SKIP_BODY_FOLDERS = frozenset(
    {
        "sent mail",
        "sent",
        "sent messages",
        "inbox",
        "all mail",
        "newsletters",
        "receipts",
        "la vie de l'iddri",
        "news etc.",
        "bounced",
        "out of office",
        "trash",
        "spam",
        "junk",
        "drafts",
        "templates",
        "[gmail]",
        "important",
        "starred",
        "chats",
        "snoozed",
    }
)

NOISE_FOLDER_RE = re.compile(
    r"newsletter|receipt|news etc|la vie de l.?iddri|bounced|out of office",
    re.I,
)

ACTIVITY_FOLDER_RE = re.compile(
    r"teach|webinar|workshop|event|publicat|paper|book|policy|bbnj|iki|"
    r"prog|ocean energy|mining|mrf|training|brief|review|consult|side event|"
    r"mcs|oceans conference",
    re.I,
)

DELIVERY_SUBJECT_RE = re.compile(
    r"attached|please find|draft|comments|revised|agenda|submitted|"
    r"version|final|for review",
    re.I,
)

DOC_ATTACH_RE = re.compile(r"\.(pdf|docx?|pptx?|xlsx?)\b", re.I)

NOISE_SIGNALS = ("newsletter", "receipt", "subscription", "signup")


def slack_user_ids_from_env() -> tuple[str, ...]:
    raw = os.environ.get("DOSSIER_SLACK_USER_IDS", "").strip()
    if raw:
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    return ()


def speaker_names_from_env() -> tuple[str, ...]:
    raw = os.environ.get("DOSSIER_SPEAKER_NAMES", "").strip()
    if raw:
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    return ()


def resolve_speaker_names() -> tuple[str, ...]:
    return speaker_names_from_env() or DEFAULT_SPEAKER_NAMES


def mail_account_map() -> dict[str, str]:
    raw = os.environ.get("DOSSIER_MAIL_ACCOUNTS", "").strip()
    if not raw:
        return dict(DEFAULT_MAIL_ACCOUNTS)
    out: dict[str, str] = dict(DEFAULT_MAIL_ACCOUNTS)
    for part in raw.split(","):
        if ":" not in part:
            continue
        email, _, folder = part.partition(":")
        email, folder = email.strip().lower(), folder.strip()
        if email and folder:
            out[email] = folder
    return out


def skip_folder(name: str) -> bool:
    return (name or "").strip().lower() in SKIP_BODY_FOLDERS


def noise_folder(name: str) -> bool:
    return bool(NOISE_FOLDER_RE.search(name or ""))


def activity_folder(name: str) -> bool:
    return bool(ACTIVITY_FOLDER_RE.search(name or ""))


def account_dir(mail_root: Path, account_key: str) -> Path:
    key = (account_key or "").strip().lower()
    mapped = mail_account_map().get(key)
    if mapped:
        return mail_root / mapped
    if not mail_root.is_dir():
        return mail_root
    local = key.split("@")[0] if "@" in key else key
    try:
        children = list(mail_root.iterdir())
    except OSError:
        return mail_root
    for child in children:
        if child.is_dir() and child.name.lower() in {local, key}:
            return child
    return mail_root


def is_blocked_mail_root(path: Path) -> bool:
    """True for the full IDDRI Thunderbird tree — do not walk/parse it."""
    if path.name.lower() != "iddri":
        return False
    return (path / "[Gmail].sbd" / "Sent Mail").exists() or (path / "INBOX").exists()
