"""Terminal colour and progress for interactive CLI feedback.

No third-party deps. Respects NO_COLOR / FORCE_COLOR and non-TTY streams.
Progress bars write to stderr so stdout stays a clean log of results.

On a TTY, :class:`Progress` pins one line at the bottom (like Rich Progress in
paperful): scrollable logs print above, the bar redraws on the last row.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TextIO


_RESET = "\033[0m"
_ProgressSink = Callable[[dict[str, Any]], None]
_progress_sink: _ProgressSink | None = None
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_MAGENTA = "\033[35m"
_BLUE = "\033[34m"

_ACTIVE: "BottomBar | None" = None
_ACTIVE_STACK: list[BottomBar] = []


def set_progress_sink(sink: _ProgressSink | None) -> _ProgressSink | None:
    """Install a structured progress sink (used by the workbench job runner).

    Returns the previous sink so callers can restore it.
    """
    global _progress_sink
    previous = _progress_sink
    _progress_sink = sink
    return previous


def _emit(kind: str, **payload: Any) -> None:
    if _progress_sink is None:
        return
    event = {"kind": kind, **payload}
    try:
        _progress_sink(event)
    except Exception:  # noqa: BLE001 — never break CLI on a bad sink
        pass


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


def _log_line(text: str, *, stream: TextIO | None = None, flush: bool = True) -> None:
    out = stream if stream is not None else sys.stderr
    if _ACTIVE is not None and _ACTIVE.owns(out):
        _ACTIVE.clear_for_log()
    print(text, file=out, flush=flush)
    if _ACTIVE is not None and _ACTIVE.owns(out):
        _ACTIVE.redraw()


def stage(title: str, detail: str = "", *, stream: TextIO | None = None) -> None:
    """Print a phase banner, e.g. ◆ extract  llm=on · 180 to draft."""
    out = stream if stream is not None else sys.stderr
    mark = paint("◆", _CYAN, _BOLD, stream=out)
    name = paint(title, _BOLD, _CYAN, stream=out)
    line = f"{mark} {name}"
    if detail:
        line = f"{line}  {paint(detail, _DIM, stream=out)}"
    _log_line(line, stream=out)
    _emit("stage", title=title, detail=detail, line=_plain(line) if detail else title)


def note(text: str, *, stream: TextIO | None = None) -> None:
    out = stream if stream is not None else sys.stderr
    _log_line(paint(text, _DIM, stream=out), stream=out)
    _emit("note", text=text, line=text)


def ok(text: str, *, stream: TextIO | None = None) -> None:
    out = stream if stream is not None else sys.stderr
    _log_line(
        f"{paint('✓', _GREEN, _BOLD, stream=out)} {text}",
        stream=out,
    )
    _emit("ok", text=text, line=text)


def warn(text: str, *, stream: TextIO | None = None) -> None:
    out = stream if stream is not None else sys.stderr
    _log_line(
        f"{paint('!', _YELLOW, _BOLD, stream=out)} {text}",
        stream=out,
    )
    _emit("warn", text=text, line=text)


def trunc(text: str, width: int = 36) -> str:
    raw = " ".join(str(text).split())
    if len(raw) <= width:
        return raw
    if width <= 1:
        return "…"
    return raw[: width - 1] + "…"


class BottomBar:
    """One pinned footer line. Only one instance is active per process."""

    def __init__(self, stream: TextIO | None = None, *, width: int = 24) -> None:
        self.stream = stream if stream is not None else sys.stderr
        self.width = width
        self._tty = hasattr(self.stream, "isatty") and bool(self.stream.isatty())
        self._colour = colour_enabled(self.stream)
        self._last_plain = ""
        self._active = False

    def owns(self, stream: TextIO) -> bool:
        return stream is self.stream

    def __enter__(self) -> BottomBar:
        global _ACTIVE
        if self._tty:
            if _ACTIVE is not None:
                _ACTIVE.clear_for_log()
                _ACTIVE_STACK.append(_ACTIVE)
            _ACTIVE = self
            self._active = True
        return self

    def __exit__(self, *exc: object) -> None:
        global _ACTIVE
        if self._active:
            self.clear_for_log()
            if _ACTIVE_STACK:
                _ACTIVE = _ACTIVE_STACK.pop()
                _ACTIVE.redraw()
            else:
                _ACTIVE = None
            self._active = False

    def clear_for_log(self) -> None:
        if not self._tty or not self._last_plain:
            return
        self.stream.write("\r\033[K")
        self.stream.flush()
        self._last_plain = ""

    def write(self, line: str, *, final: bool = False) -> None:
        if self._tty:
            pad = max(0, len(self._last_plain) - len(_plain(line)))
            self.stream.write("\r" + line + (" " * pad))
            if final:
                self.stream.write("\n")
            self.stream.flush()
            self._last_plain = "" if final else _plain(line)
            return
        print(line, file=self.stream, flush=True)

    def redraw(self) -> None:
        if self._tty and self._last_plain:
            self.write(self._rendered_line, final=False)

    @property
    def _rendered_line(self) -> str:
        return getattr(self, "_line_cache", "")

    def set_line(self, line: str, *, final: bool = False) -> None:
        self._line_cache = line
        self.write(line, final=final)


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
        self._bar: BottomBar | None = None
        self._last_plain = ""

    def __enter__(self) -> Progress:
        if self._tty:
            self._bar = BottomBar(self._out, width=self.width)
            self._bar.__enter__()
            self._render()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._bar is not None:
            self._bar.__exit__(*exc)
            self._bar = None

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
        line = self._format_line()
        plain = _plain(line)
        _emit(
            "progress",
            label=self.label,
            done=self.done,
            total=self.total,
            status=self._status,
            stats=dict(self._stats),
            line=plain,
            final=final,
        )
        if self._bar is not None:
            self._bar.set_line(line, final=final)
            self._last_plain = plain
            return
        if self._tty:
            pad = max(0, len(self._last_plain) - len(plain))
            self._out.write("\r" + line + (" " * pad))
            if final:
                self._out.write("\n")
            self._out.flush()
            self._last_plain = plain if not final else ""
            return
        step = max(1, self.total // 10) if self.total else 50
        if final or self.done == 1 or self.done % step == 0:
            print(line, file=self._out, flush=True)

    def _format_line(self) -> str:
        total = max(self.total, 1) if self.total > 0 else max(self.done, 1)
        done = self.done if self.total > 0 else self.done
        frac = 1.0 if self.total == 0 and self.done > 0 else min(1.0, done / total)
        if self.total > 0 and self.done >= self.total:
            frac = 1.0
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
        return f"{line}{status}"


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
