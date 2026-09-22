"""Include and exclude phrases. Built in, then edited in the local toml.

Each source has a ``[section]``. Missing keys keep the built-in list. A list
adds phrases. The matching ``_off`` list turns built-in phrases off.
Environment variables ``DOSSIER_<SECTION>_<KEY>`` override the file and use
commas. Phrases are words, not regular expressions.

Folder keep wins over folder exclude, so an admin folder stays even when its
name also says receipt. For file names, drop wins over keep, and keep wins
over exclude: a timesheet stays out, a budget form stays in.
"""

from __future__ import annotations

import os
import re

from dossier.paths import _toml_list, _toml_section

# Never matches. DuckDB uses RE2, which has no lookahead.
_NEVER = "a^"

DEFAULT_MAIL_EXCLUDE = (
    "newsletter",
    "receipt",
    "news etc",
    "la vie de l'iddri",
    "out of office",
    "google alert",
    "amazon affiliate",
    "bounce",
)
DEFAULT_MAIL_KEEP = (
    "admin",
    "budget",
    "finance",
)
DEFAULT_MAIL_ACTIVITY = (
    "teach",
    "webinar",
    "workshop",
    "event",
    "publicat",
    "paper",
    "book",
    "policy",
    "bbnj",
    "iki",
    "prog",
    "ocean energy",
    "mining",
    "mrf",
    "training",
    "brief",
    "review",
    "consult",
    "side event",
    "mcs",
    "oceans conference",
)
DEFAULT_MAIL_SIGNALS = (
    "newsletter",
    "receipt",
    "subscription",
    "signup",
)

# Substring. A timesheet stays noise even when the filename also says budget.
DEFAULT_NAME_DROP = (
    "timesheet",
    "time sheet",
    "time-sheet",
    "payslip",
    "bulletin de paie",
    "conge",
    "congé",
)
# Substring. Saves a name the exclude list would drop.
DEFAULT_NAME_KEEP = (
    "frais",
    "budget",
    "expense",
    "reimburs",
    "rembours",
    "ordre de mission",
    "mission order",
)
# Word or phrase, unless the phrase itself contains punctuation.
# ``^`` anchors the start. ``^term$`` matches the whole name.
DEFAULT_NAME_EXCLUDE = (
    "form",
    "consent",
    "registration",
    "invoice",
    "receipt",
    "passport",
    "duplicat",
    "bulletin",
    "judging",
    "appointment",
    "engagement",
    "attendee report",
    "logistics",
    "ordonnance",
    "holiday date",
    "holiday dates",
    "chatgpt",
    "gemini testing",
    "booking.com",
    "image.png",
    "image.jpg",
    "image.jpeg",
    "agenda.doc",
    "*done*",
    "^invitation",
    "^thank you",
    "^fwd:$",
)

# Exact folder names that are not opened. Sent, Inbox, and All Mail stay closed in code.
DEFAULT_MAIL_CLOSED = (
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
)

DEFAULT_EMPLOYER_DIRS = (
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "bower_components",
    "site-packages",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".eggs",
    ".ipynb_checkpoints",
    "htmlcov",
    "cache",
    "caches",
    ".cache",
)
DEFAULT_EMPLOYER_SUFFIXES = (
    ".pkl",
    ".pickle",
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".o",
    ".obj",
    ".a",
    ".lib",
    ".class",
    ".jar",
    ".war",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".eot",
    ".parquet",
    ".feather",
    ".arrow",
    ".npy",
    ".npz",
    ".h5",
    ".hdf5",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".pt",
    ".pth",
    ".ckpt",
    ".onnx",
    ".safetensors",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".iso",
    ".dmg",
    ".zip",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".bmp",
    ".tif",
    ".tiff",
    ".mp4",
    ".mov",
    ".mp3",
    ".wav",
    ".avi",
    ".mkv",
    ".whl",
)
DEFAULT_EMPLOYER_FILES = (
    ".ds_store",
    "thumbs.db",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "cargo.lock",
    "pipfile.lock",
)
DEFAULT_EMPLOYER_ROOTS = ("publications", "events", "projects", "slides")
DEFAULT_EMPLOYER_SLUGS = ("*unsorted", "unsorted", "admin")

DEFAULT_SLACK_ACTIVITY = (
    "gsr_",
    "gfr_",
    "research_",
    "events_",
    "comm_",
    "comms_",
    "academy_",
    "policy",
)
DEFAULT_MEETINGS_DIRS = (
    "metadata",
    "imports",
    "originals",
    "readable",
    ".stfolder",
    ".whispermlx-missing",
)
DEFAULT_MEETINGS_SOLO = ("workshop", "webinar", "teaching", "side_event", "slides")
DEFAULT_APPLICATION_FILES = (".ds_store", "thumbs.db")


def terms(section: str, key: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Built-in phrases, plus ``[section] key`` / ``key_off`` in the local toml."""
    env = f"DOSSIER_{section.upper()}_{key.upper()}"
    return _resolve(env, f"{env}_OFF", section, key, f"{key}_off", default)


def mail_exclude() -> tuple[str, ...]:
    return terms("mail", "exclude", DEFAULT_MAIL_EXCLUDE)


def mail_keep() -> tuple[str, ...]:
    return terms("mail", "keep", DEFAULT_MAIL_KEEP)


def mail_activity() -> tuple[str, ...]:
    return terms("mail", "activity", DEFAULT_MAIL_ACTIVITY)


def mail_signals() -> tuple[str, ...]:
    return terms("mail", "signals", DEFAULT_MAIL_SIGNALS)


# Closed names that are also dropped from the seek. Receipts and newsletters
# stay on the exclude list, so turning that phrase off is enough to seek them.
_SEEK_CLOSED = frozenset(
    {
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


def mail_closed() -> frozenset[str]:
    return _exact(terms("mail", "closed", DEFAULT_MAIL_CLOSED))


def seek_closed() -> frozenset[str]:
    """Folders dropped from the seek. User-added closed names are included."""
    closed = mail_closed()
    added = closed - _exact(DEFAULT_MAIL_CLOSED)
    return (closed & _SEEK_CLOSED) | added


def name_drop() -> tuple[str, ...]:
    return terms("names", "drop", DEFAULT_NAME_DROP)


def name_keep() -> tuple[str, ...]:
    return terms("names", "keep", DEFAULT_NAME_KEEP)


def name_exclude() -> tuple[str, ...]:
    return terms("names", "exclude", DEFAULT_NAME_EXCLUDE)


def employer_dirs() -> frozenset[str]:
    return _exact(terms("employer", "dir_exclude", DEFAULT_EMPLOYER_DIRS))


def employer_suffixes() -> frozenset[str]:
    out: list[str] = []
    for term in terms("employer", "suffix_exclude", DEFAULT_EMPLOYER_SUFFIXES):
        folded = _fold(term)
        if not folded:
            continue
        out.append(folded if folded.startswith(".") else f".{folded}")
    return frozenset(out)


def employer_files() -> frozenset[str]:
    return _exact(terms("employer", "file_exclude", DEFAULT_EMPLOYER_FILES))


def employer_roots() -> frozenset[str]:
    return _exact(terms("employer", "roots", DEFAULT_EMPLOYER_ROOTS))


def employer_slugs() -> frozenset[str]:
    return _exact(terms("employer", "slug_exclude", DEFAULT_EMPLOYER_SLUGS))


def slack_activity() -> tuple[str, ...]:
    return terms("slack", "activity", DEFAULT_SLACK_ACTIVITY)


def slack_exclude() -> tuple[str, ...]:
    return terms("slack", "exclude", ())


def meetings_dirs() -> frozenset[str]:
    return _exact(terms("meetings", "exclude", DEFAULT_MEETINGS_DIRS))


def meetings_solo() -> frozenset[str]:
    return _exact(terms("meetings", "solo", DEFAULT_MEETINGS_SOLO))


def application_files() -> frozenset[str]:
    return _exact(terms("applications", "file_exclude", DEFAULT_APPLICATION_FILES))


def application_dirs() -> frozenset[str]:
    return _exact(terms("applications", "dir_exclude", DEFAULT_EMPLOYER_DIRS))


def excluded(source: str, *parts: str) -> bool:
    """True when ``[source] exclude`` matches. The built-in list for this key is empty."""
    blob = _fold(" ".join(part for part in parts if part))
    if not blob:
        return False
    return _contains(terms(source, "exclude", ()), blob)


def phrase_blocked(phrases: tuple[str, ...], text: str) -> bool:
    return _contains(phrases, _fold(text or ""))


def folder_is_noise(name: str) -> bool:
    """True when a folder phrase is excluded and not kept.

    A closed folder (trash, spam, drafts) is noise even when its name also
    matches a keep phrase. Sent and Inbox are not in that set.
    """
    folded = _fold(name or "")
    if not folded.strip():
        return False
    if folded in seek_closed():
        return True
    if _contains(mail_keep(), folded):
        return False
    return _contains(mail_exclude(), folded)


def folder_is_activity(name: str) -> bool:
    return _contains(mail_activity(), _fold(name or ""))


def name_is_noise(*parts: str) -> bool:
    """True for logistics names. A budget form is kept. A timesheet is not."""
    blob = " ".join(p for p in parts if p).strip()
    if not blob:
        return False
    folded = _fold(blob)
    if _contains(name_drop(), folded):
        return True
    if _contains(name_keep(), folded):
        return False
    return _name_exclude_hit(name_exclude(), folded)


def phrase_pattern(terms: tuple[str, ...]) -> str:
    """Left-bounded alternation for SQL ``regexp_matches`` on a lowercased name.

    ``newsletter`` matches ``newsletters``. ``wip`` does not match ``swipe``.
    """
    parts = [re.escape(_fold(term)) for term in terms if _fold(term)]
    if not parts:
        return _NEVER
    return "(?:^|[^a-z0-9])(?:" + "|".join(parts) + ")"


def _resolve(
    env_add: str,
    env_off: str,
    section: str,
    add_key: str,
    off_key: str,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    kept = tuple(default)
    off = _layer(env_off, section, off_key)
    if off:
        gone = {_fold(item) for item in off}
        kept = tuple(item for item in kept if _fold(item) not in gone)
    extra = _layer(env_add, section, add_key)
    if extra:
        kept = kept + extra
    return kept


def _layer(env_name: str, section: str, key: str) -> tuple[str, ...] | None:
    """None when the user left the key out. Empty when they set an empty list."""
    if env_name in os.environ:
        return _split_csv(os.environ.get(env_name, ""))
    block = _toml_section(section)
    if key not in block:
        return None
    return tuple(_toml_list(section, key))


def _split_csv(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _exact(phrases: tuple[str, ...]) -> frozenset[str]:
    return frozenset(_fold(term) for term in phrases if _fold(term))


def _fold(value: str) -> str:
    text = (value or "").strip().casefold()
    return text.replace("\u2019", "'").replace("`", "'")


def _contains(terms: tuple[str, ...], folded: str) -> bool:
    """True when a phrase starts at a token boundary. A longer token may follow."""
    for term in terms:
        needle = _fold(term)
        if not needle:
            continue
        start = 0
        while True:
            at = folded.find(needle, start)
            if at < 0:
                break
            if at == 0 or not folded[at - 1].isalnum():
                return True
            start = at + 1
    return False


def _name_exclude_hit(terms: tuple[str, ...], folded: str) -> bool:
    for term in terms:
        raw = _fold(term)
        if not raw:
            continue
        if raw.startswith("^") and raw.endswith("$") and len(raw) > 2:
            if folded.strip() == raw[1:-1].strip():
                return True
            continue
        if raw.startswith("^"):
            rest = raw[1:]
            if re.match(rf"{re.escape(rest)}(?:[^a-z0-9]|$)", folded):
                return True
            continue
        if any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789 -'" for ch in raw):
            if raw in folded:
                return True
            continue
        if re.search(rf"(?:^|[^a-z0-9]){re.escape(raw)}(?:[^a-z0-9]|$)", folded):
            return True
    return False
