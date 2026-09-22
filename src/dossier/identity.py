"""Local identities for seekers. No CRM.

Shipped defaults are empty. Names, Slack ids, and the mail-folder map
come from the environment or from gitignored ``$DOSSIER_DATA/dossier.toml``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from dossier.lists import folder_is_activity, folder_is_noise, mail_closed
from dossier.paths import _toml_list, _toml_section

# These stay closed even if a local list turns the others off.
_HARD_CLOSED = frozenset({"sent mail", "sent", "sent messages", "inbox", "all mail"})

DELIVERY_SUBJECT_RE = re.compile(
    r"attached|please find|draft|comments|revised|agenda|submitted|"
    r"version|final|for review",
    re.I,
)

DOC_ATTACH_RE = re.compile(r"\.(pdf|docx?|pptx?|xlsx?)\b", re.I)


def slack_user_ids_from_env() -> tuple[str, ...]:
    raw = os.environ.get("DOSSIER_SLACK_USER_IDS", "").strip()
    if raw:
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    return ()


def configured_slack_user_ids() -> tuple[str, ...]:
    """Env, else ``[identity] slack_user_ids`` in the local toml. Never a built-in id."""
    if env := slack_user_ids_from_env():
        return env
    return tuple(_toml_list("identity", "slack_user_ids"))


def speaker_names_from_env() -> tuple[str, ...]:
    raw = os.environ.get("DOSSIER_SPEAKER_NAMES", "").strip()
    if raw:
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    return ()


def resolve_speaker_names() -> tuple[str, ...]:
    """Env, else ``[identity] speaker_names``. Empty means you are not named."""
    if env := speaker_names_from_env():
        return env
    return tuple(_toml_list("identity", "speaker_names"))


def _file_mail_accounts() -> dict[str, str]:
    block = _toml_section("identity").get("mail_accounts")
    if not isinstance(block, dict):
        return {}
    out: dict[str, str] = {}
    for email, folder in block.items():
        key, name = str(email).strip().lower(), str(folder).strip()
        if key and name:
            out[key] = name
    return out


def mail_account_map() -> dict[str, str]:
    """Local toml, with ``DOSSIER_MAIL_ACCOUNTS`` (``email:folder`` pairs) overlaid."""
    out = _file_mail_accounts()
    raw = os.environ.get("DOSSIER_MAIL_ACCOUNTS", "").strip()
    if not raw:
        return out
    for part in raw.split(","):
        if ":" not in part:
            continue
        email, _, folder = part.partition(":")
        email, folder = email.strip().lower(), folder.strip()
        if email and folder:
            out[email] = folder
    return out


def skip_folder(name: str) -> bool:
    """True for folders whose bodies are not opened. Sent and Inbox stay closed."""
    folded = (name or "").strip().casefold()
    if folded in _HARD_CLOSED:
        return True
    return folded in mail_closed()


def noise_folder(name: str) -> bool:
    """True for newsletter-style folders. Kept phrases (admin, budget, finance) win."""
    return folder_is_noise(name)


def activity_folder(name: str) -> bool:
    return folder_is_activity(name)


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
