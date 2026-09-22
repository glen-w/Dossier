"""One-message mbox fetch. Never parse Sent Mail or the IDDRI tree as a stream."""

from __future__ import annotations

import mailbox
import os
from collections.abc import Iterator
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from pathlib import Path

from dossier.identity import account_dir, is_blocked_mail_root, noise_folder, skip_folder

DEFAULT_MAX_BYTES = 200 * 1024 * 1024
TEXT_CAP = 8000

_SIDECAR_SUFFIXES = {
    ".msf",
    ".dat",
    ".html",
    ".json",
    ".bak",
    ".tmp",
    ".part",
    ".toc",
}
_SIDECAR_NAMES = {
    "msgfilterrules.dat",
    "filterlog.html",
    "popstate.dat",
    "foldercache.json",
}


DEFAULT_MAX_FILES = 40


def mbox_max_files() -> int:
    """Cap on mbox files opened in one exported folder. Not a tree walk."""
    raw = os.environ.get("DOSSIER_MBOX_MAX_FILES", "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return DEFAULT_MAX_FILES


def mbox_max_bytes() -> int:
    raw = os.environ.get("DOSSIER_MBOX_MAX_BYTES", "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return DEFAULT_MAX_BYTES


def _closed_folder(name: str) -> bool:
    """Sent, inbox, and newsletter-style folders are not opened."""
    return skip_folder(name) or noise_folder(name)


def mbox_openable(path: Path, folder_name: str, max_bytes: int | None = None) -> bool:
    cap = mbox_max_bytes() if max_bytes is None else max_bytes
    if _closed_folder(folder_name) or _closed_folder(path.name):
        return False
    try:
        return path.is_file() and path.stat().st_size <= cap
    except OSError:
        return False


def is_mbox_file(path: Path) -> bool:
    if not path.is_file():
        return False
    name = path.name
    if name.startswith("."):
        return False
    lower = name.lower()
    if lower in _SIDECAR_NAMES:
        return False
    if any(lower.endswith(s) for s in _SIDECAR_SUFFIXES):
        return False
    if lower.endswith(".sbd"):
        return False
    return True


def iter_mbox_files(root: Path) -> Iterator[tuple[Path, str]]:
    root = root.resolve()
    if is_blocked_mail_root(root):
        return
    if root.is_file() and is_mbox_file(root):
        yield root, root.name
        return
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Never stream the 26G IDDRI Thunderbird tree (or its Sent Mail).
        dirnames[:] = [
            d
            for d in dirnames
            if not d.startswith(".")
            and not is_blocked_mail_root(Path(dirpath) / d)
        ]
        for name in filenames:
            path = Path(dirpath) / name
            if not is_mbox_file(path):
                continue
            yield path, name


def find_mbox(mail_root: Path, account_key: str, folder_name: str) -> Path | None:
    if _closed_folder(folder_name):
        return None
    index = build_mbox_index(mail_root)
    return lookup_mbox(index, mail_root, account_key, folder_name)


def build_mbox_index(mail_root: Path) -> dict[tuple[str, str], Path]:
    """Map (account-dir name, folder basename) → mbox path. Skips Sent/INBOX."""
    index: dict[tuple[str, str], Path] = {}
    root = mail_root.resolve() if mail_root.exists() else mail_root
    start = root if root.is_dir() else root.parent
    if not start.exists():
        return index
    for path, name in iter_mbox_files(start):
        if _closed_folder(name) or _closed_folder(path.name):
            continue
        try:
            rel = path.relative_to(root if root.is_dir() else start)
            account = rel.parts[0] if len(rel.parts) > 1 else start.name
        except ValueError:
            account = start.name
        for key in ((account, name), (start.name, name)):
            prev = index.get(key)
            if prev is None or len(path.parts) < len(prev.parts):
                index[key] = path
    return index


def lookup_mbox(
    index: dict[tuple[str, str], Path],
    mail_root: Path,
    account_key: str,
    folder_name: str,
) -> Path | None:
    if _closed_folder(folder_name):
        return None
    mapped = account_dir(mail_root, account_key)
    for key in ((mapped.name, folder_name), (mail_root.name, folder_name)):
        path = index.get(key)
        if path is not None:
            return path
    return None


def normalize_message_id(value: str | None) -> str:
    return " ".join((value or "").strip().strip("<>").lower().split())


def fetch_mbox_body(
    mail_root: Path,
    *,
    account_key: str,
    folder_name: str,
    header_message_id: str,
    max_bytes: int | None = None,
    max_chars: int = TEXT_CAP,
    index: dict[tuple[str, str], Path] | None = None,
) -> str:
    if _closed_folder(folder_name):
        return ""
    catalog = index if index is not None else build_mbox_index(mail_root)
    path = lookup_mbox(catalog, mail_root, account_key, folder_name)
    if path is None or not mbox_openable(path, folder_name, max_bytes):
        return ""
    want = normalize_message_id(header_message_id)
    if not want:
        return ""
    try:
        box = mailbox.mbox(str(path), create=False)
    except Exception:
        return ""
    try:
        for key in box.keys():
            try:
                msg = box[key]
            except Exception:
                continue
            if msg is None:
                continue
            got = normalize_message_id(str(msg.get("Message-ID") or ""))
            if got != want:
                continue
            return _body_from_message(msg, folder_name, max_chars)
    finally:
        box.close()
    return ""


def parse_headers(mbox_path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        box = mailbox.mbox(str(mbox_path), create=False)
    except Exception:
        return out
    try:
        for key in box.keys():
            try:
                msg = box[key]
            except Exception:
                continue
            if msg is None:
                continue
            subject = _decode(msg.get("Subject"))
            sender = _decode(msg.get("From"))
            mid = normalize_message_id(str(msg.get("Message-ID") or "")) or str(key)
            year = 0
            try:
                parsed = parsedate_to_datetime(msg.get("Date") or "")
                if isinstance(parsed, datetime):
                    year = parsed.year
            except (TypeError, ValueError, IndexError):
                year = 0
            artifacts = _attachment_names(msg)
            out.append(
                {
                    "key": str(key),
                    "message_id": mid,
                    "subject": subject,
                    "from": sender,
                    "year": year,
                    "artifacts": artifacts,
                }
            )
    finally:
        box.close()
    return out


def _decode(value: object) -> str:
    if value is None:
        return ""
    try:
        return str(make_header(decode_header(str(value))))
    except Exception:
        return str(value)


def _attachment_names(msg) -> tuple[str, ...]:
    names: list[str] = []
    if not getattr(msg, "walk", None):
        return ()
    for part in msg.walk():
        disp = str(part.get("Content-Disposition") or "")
        filename = part.get_filename()
        if filename and ("attachment" in disp.lower() or filename):
            names.append(_decode(filename))
    return tuple(dict.fromkeys(n for n in names if n))


def _body_from_message(msg, folder_name: str, max_chars: int) -> str:
    try:
        from rollup.parse import parse_message

        parsed = parse_message(msg, folder_name, folder_name, max_chars, 20)
        text = (parsed.body_text or "").strip()
        if text:
            return text[:max_chars]
    except Exception:
        pass
    return _stdlib_body(msg, max_chars)


def _stdlib_body(msg, max_chars: int) -> str:
    texts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() != "text/plain":
                continue
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                texts.append(payload.decode(part.get_content_charset() or "utf-8", "replace"))
            elif isinstance(payload, str):
                texts.append(payload)
    else:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            texts.append(payload.decode(msg.get_content_charset() or "utf-8", "replace"))
        elif isinstance(payload, str):
            texts.append(payload)
    return "\n".join(texts).strip()[:max_chars]
