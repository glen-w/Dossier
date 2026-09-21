"""Adapter protocol. Shape borrowed from data_dumps Source. Not a second warehouse."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dossier.store import Corpus


@runtime_checkable
class Source(Protocol):
    """One evidence source. Append it on CONTRIBUTIONS when it exists."""

    name: str

    def detect(self, path: Path) -> bool:
        """Return True if this adapter owns the given file or directory."""
        ...

    def load(self, path: Path, corpus: Corpus) -> None:
        """Read into the local gitignored corpus. Do not commit the bytes."""
        ...

    def tables(self) -> list[str]:
        """Record names this source provides."""
        ...
