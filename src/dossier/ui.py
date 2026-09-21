"""Terminal colour and progress for interactive CLI feedback.

No third-party deps. Respects NO_COLOR / FORCE_COLOR and non-TTY streams.
Progress bars write to stderr so stdout stays a clean log of results.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import TextIO


_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_MAGENTA = "\033[35m"
_BLUE = "\033[34m"


def colour_enabled(stream: TextIO | None = None) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    target = stream if stream is not None else sys.stderr
    return hasattr(target, "isatty") and bool(target.isatty())


def paint(text: str, *codes: str, stream: TextIO | None = None) -> str:
    if not codes or not colour_enabled(stream):
        return text
    return f"{''.join(codes)}{text}{_RESET}"


def stage(title: str, detail: str = "", *, stream: TextIO | None = None) -> None:
    """Print a phase banner, e.g. ◆ extract  llm=on · 180 to draft."""
    out = stream if stream is not None else sys.stderr
    mark = paint("◆", _CYAN, _BOLD, stream=out)
    name = paint(title, _BOLD, _CYAN, stream=out)
    line = f"{mark} {name}"
    if detail:
        line = f"{line}  {paint(detail, _DIM, stream=out)}"
    print(line, file=out, flush=True)


def note(text: str, *, stream: TextIO | None = None) -> None:
    out = stream if stream is not None else sys.stderr
    print(paint(text, _DIM, stream=out), file=out, flush=True)


def ok(text: str, *, stream: TextIO | None = None) -> None:
    out = stream if stream is not None else sys.stderr
    print(f"{paint('✓', _GREEN, _BOLD, stream=out)} {text}", file=out, flush=True)


def warn(text: str, *, stream: TextIO | None = None) -> None:
    out = stream if stream is not None else sys.stderr
    print(f"{paint('!', _YELLOW, _BOLD, stream=out)} {text}", file=out, flush=True)


def trunc(text: str, width: int = 36) -> str:
    raw = " ".join(str(text).split())
    if len(raw) <= width:
        return raw
    if width <= 1:
        return "…"
    return raw[: width - 1] + "…"


@dataclass
class Progress:
    """Single-line progress bar with optional keyed counters."""

    total: int
    label: str = ""
    stream: TextIO | None = None
    width: int = 24

    def __post_init__(self) -> None:
        self.done = 0
        self._stats: dict[str, int | str] = {}
        self._status = ""
        self._out = self.stream if self.stream is not None else sys.stderr
        self._tty = hasattr(self._out, "isatty") and bool(self._out.isatty())
        self._colour = colour_enabled(self._out)
        self._last_plain = ""

    def status(self, text: str) -> None:
        self._status = text
        self._render()

    def tick(self, n: int = 1, **stats: int | str) -> None:
        self.done = min(self.done + max(0, n), max(self.total, self.done + n))
        self._stats.update(stats)
        self._status = ""
        self._render()

    def set_total(self, total: int) -> None:
        self.total = max(0, int(total))
        self._render()

    def finish(self, **stats: int | str) -> None:
        self._stats.update(stats)
        if self.total > 0:
            self.done = self.total
        self._status = ""
        self._render(final=True)

    def _render(self, *, final: bool = False) -> None:
        total = max(self.total, 1) if self.total > 0 else max(self.done, 1)
        done = self.done if self.total > 0 else self.done
        frac = 1.0 if self.total == 0 and final else min(1.0, done / total)
        filled = int(round(self.width * frac))
        empty = max(0, self.width - filled)
        if self._colour:
            bar = (
                f"{_MAGENTA}{'█' * filled}{_RESET}"
                f"{_DIM}{'░' * empty}{_RESET}"
            )
        else:
            bar = f"{'#' * filled}{'-' * empty}"
        counts = f"{done}/{self.total}" if self.total > 0 else f"{done}"
        bits = [f"{k}={v}" for k, v in self._stats.items()]
        suffix = "  ".join(bits)
        label = f"{self.label}  " if self.label else ""
        status = f"  {self._status}" if self._status else ""
        line = f"{label}[{bar}]  {counts}"
        if suffix:
            line = f"{line}  {suffix}"
        line = f"{line}{status}"
        if self._tty:
            pad = max(0, len(self._last_plain) - len(_plain(line)))
            self._out.write("\r" + line + (" " * pad))
            if final:
                self._out.write("\n")
            self._out.flush()
            self._last_plain = _plain(line)
            return
        # Non-TTY: print sparingly (every ~10% or on finish).
        step = max(1, self.total // 10) if self.total else 1
        if final or self.done == 1 or (self.total and self.done % step == 0):
            print(line, file=self._out, flush=True)


def _plain(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "\033":
            j = text.find("m", i)
            if j == -1:
                break
            i = j + 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


# Re-export hue constants for rare call sites that need a one-off paint.
HUES = {
    "cyan": _CYAN,
    "green": _GREEN,
    "yellow": _YELLOW,
    "magenta": _MAGENTA,
    "blue": _BLUE,
    "dim": _DIM,
    "bold": _BOLD,
}
