"""Local paths. Corpus and warehouse stay off git."""

from __future__ import annotations

import os
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
    return os.environ.get("DOSSIER_PUBS_URL", DEFAULT_PUBS_URL).rstrip("/")


def mail_root() -> Path:
    if raw := os.environ.get("DOSSIER_MAIL_ROOT"):
        return Path(raw).expanduser()
    return DEFAULT_MAIL_ROOT
