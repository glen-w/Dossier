"""Local text from PDF, Word, and PowerPoint. No CV renderer. No OCR."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree

from dossier.text import TEXT_CAP_OFFICE as TEXT_CAP

MEMBER_CAP = 2_000_000
OFFICE_SUFFIXES = frozenset({".pdf", ".docx", ".pptx"})
INVENTORY_MARK = "Binary body not ingested"

_W_T = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
_A_T = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"


def office_extra_ready() -> bool:
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return False
    return True


def extract_office(path: Path) -> tuple[str, str]:
    """Return (text, reason). A reason means the file stays an inventory line."""
    suffix = path.suffix.lower()
    if suffix not in OFFICE_SUFFIXES:
        return "", "not an office file"
    try:
        if suffix == ".pdf":
            text = _pdf(path)
        elif suffix == ".docx":
            text = _docx(path)
        else:
            text = _pptx(path)
    except Exception as extra:  # inventory line, not a crash
        return "", str(extra) or "could not read office file"
    cleaned = " ".join(text.split())
    if not cleaned:
        return "", "no text in office file"
    return cleaned[:TEXT_CAP], ""


def _pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "office extra not installed (uv sync --extra office)"
        ) from exc
    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _read_zip_member(archive: zipfile.ZipFile, name: str) -> bytes:
    info = archive.getinfo(name)
    if info.file_size > MEMBER_CAP:
        raise RuntimeError("office zip member exceeds size cap")
    data = archive.read(name)
    if len(data) > MEMBER_CAP:
        raise RuntimeError("office zip member exceeds size cap")
    return data


def _docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = _read_zip_member(archive, "word/document.xml")
    root = ElementTree.fromstring(xml)
    return " ".join(node.text or "" for node in root.iter(_W_T))


def _pptx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        chunks: list[str] = []
        for name in names:
            root = ElementTree.fromstring(_read_zip_member(archive, name))
            chunks.append(" ".join(node.text or "" for node in root.iter(_A_T)))
    return "\n".join(chunks)
