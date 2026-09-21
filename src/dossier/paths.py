"""Local paths. Corpus and warehouse stay off git."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

DEFAULT_WAREHOUSE = (
    Path.home() / "Documents" / "data_dumps_raw" / "warehouse" / "catalog.duckdb"
)
DEFAULT_APPLICATIONS = Path.home() / "Documents" / "job applications"
DEFAULT_CURSOR_PROJECTS = Path.home() / ".cursor" / "projects"
DEFAULT_GROK_BLOBS = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Grok Bot"
    / "sand-client-persistence"
)
DEFAULT_PUBS_URL = "http://127.0.0.1:8012"
DEFAULT_MAIL_ROOT = Path.home() / "email"


def data_dir() -> Path:
    if raw := os.environ.get("DOSSIER_DATA"):
        return Path(raw).expanduser()
    return Path.home() / "Documents" / "Dossier" / "data"


def evidence_db(root: Path | None = None) -> Path:
    return (root or data_dir()) / "evidence.db"


def warehouse_db() -> Path:
    if raw := os.environ.get("DATA_DUMPS_WAREHOUSE"):
        return Path(raw).expanduser()
    if root := os.environ.get("DATA_DUMPS_ROOT"):
        return Path(root).expanduser() / "warehouse" / "catalog.duckdb"
    return DEFAULT_WAREHOUSE


def applications_dir() -> Path:
    if raw := os.environ.get("DOSSIER_APPLICATIONS"):
        return Path(raw).expanduser()
    return DEFAULT_APPLICATIONS


def cursor_projects_root() -> Path:
    if raw := os.environ.get("DOSSIER_CURSOR_PROJECTS"):
        return Path(raw).expanduser()
    return DEFAULT_CURSOR_PROJECTS


def grok_blobs_dir() -> Path:
    if raw := os.environ.get("DOSSIER_GROK_BLOBS"):
        return Path(raw).expanduser()
    return DEFAULT_GROK_BLOBS


def pubs_url() -> str:
    if raw := os.environ.get("DOSSIER_PUBS_URL", "").strip():
        return raw.rstrip("/")
    if raw := _toml_str("pubs", "url"):
        return raw.rstrip("/")
    return DEFAULT_PUBS_URL


def pubs_seed() -> str:
    if raw := os.environ.get("DOSSIER_PUBS_SEED", "").strip():
        return raw
    return _toml_str("pubs", "seed") or "publications"


def pubs_top_k() -> int:
    raw = os.environ.get("DOSSIER_PUBS_TOP_K", "").strip() or _toml_str("pubs", "top_k") or "50"
    try:
        return max(1, int(raw))
    except ValueError:
        return 50


def pubs_collection() -> str:
    return _toml_str("pubs", "collection")


def zotero_db() -> Path:
    if raw := os.environ.get("ZOTERO_DB", "").strip():
        return Path(raw).expanduser()
    if raw := _toml_str("pubs", "zotero_db"):
        return Path(raw).expanduser()
    return Path.home() / "Zotero" / "zotero.sqlite"


def mail_root() -> Path:
    if raw := os.environ.get("DOSSIER_MAIL_ROOT"):
        return Path(raw).expanduser()
    return DEFAULT_MAIL_ROOT


def transcriptx_library() -> Path:
    if raw := os.environ.get("DOSSIER_TRANSCRIPTX"):
        return Path(raw).expanduser()
    if raw := os.environ.get("TRANSCRIPTX_TRANSCRIPTS_DIR"):
        return Path(raw).expanduser()
    return Path.home() / "Documents" / "transcripts"


def chatgpt_export() -> Path | None:
    raw = os.environ.get("DOSSIER_CHATGPT_EXPORT", "").strip()
    return Path(raw).expanduser() if raw else None


def slack_export() -> Path | None:
    raw = os.environ.get("DOSSIER_SLACK_EXPORT", "").strip()
    return Path(raw).expanduser() if raw else None


def employer_paths() -> tuple[Path, ...]:
    """Allowlisted folders. The home Documents directory is never included."""
    raw = os.environ.get("DOSSIER_EMPLOYER_PATHS", "").strip()
    parts = _split_env_paths(raw) if raw else _toml_list("employer", "paths")
    out: list[Path] = []
    for part in parts:
        if (path := _kept_path(part)) is not None:
            out.append(path)
    return tuple(out)


def git_user() -> str:
    """Author fragment. Matched against name and email. Empty means every author."""
    if raw := os.environ.get("DOSSIER_GIT_USER", "").strip():
        return raw
    return _toml_str("git", "user")


def git_paths() -> tuple[Path, ...]:
    """Repos named in config. This does not scan the home directory."""
    raw = os.environ.get("DOSSIER_GIT_PATHS", "").strip()
    parts = _split_env_paths(raw) if raw else _toml_list("git", "paths")
    out: list[Path] = []
    for part in parts:
        path = Path(part).expanduser()
        if _is_documents_root(path):
            continue
        out.append(path)
    return tuple(out)


def _kept_path(part: str) -> Path | None:
    path = Path(part).expanduser()
    if _is_documents_root(path):
        return None
    return path


def _split_env_paths(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _is_documents_root(path: Path) -> bool:
    try:
        return path.resolve() == (Path.home() / "Documents").resolve()
    except OSError:
        return False


def _local_toml() -> dict:
    path = data_dir() / "dossier.toml"
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _toml_section(name: str) -> dict:
    block = _local_toml().get(name)
    return block if isinstance(block, dict) else {}


def _toml_str(section: str, key: str) -> str:
    value = _toml_section(section).get(key)
    if value is None:
        return ""
    return str(value).strip()


def _toml_list(section: str, key: str) -> list[str]:
    value = _toml_section(section).get(key) or []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []
