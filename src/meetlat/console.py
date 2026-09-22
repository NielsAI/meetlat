"""The presentation layer: one palette, one set of glyphs, one voice.

Ported from the shared `lib/cli.sh` design system in the author's Hub repository,
because the rule it exists to enforce travels: anything a person runs directly
speaks through one module, so a second command does not invent a second dialect of
green. Here that module is Python rather than bash, and the CLI and the gates in
`scripts/` both import it.

Colour is emitted only when the stream is an interactive terminal that advertises
it, and `NO_COLOR` turns it off everywhere (https://no-color.org). Everything below
renders as clean text in a pipe, in CI, or in a log, so nothing ever writes an
escape sequence into a file someone later has to read.

Glyphs, two-space indented so they nest under a heading:

    ok    ✔ green    something succeeded
    bad   ✘ red      something failed, on stdout
    skip  ○ dim      did not run, and why
    warn  ▲ yellow   a caveat that is not fatal
    note    dim      secondary detail, a hint, context
    line             a continuation under one of the above, no glyph
    stat  ◦ dim      a number that is not a verdict (ADR-0002)
    err   ✘ red      a problem, to stderr, without exiting
    fail  ✘ red      err, then exit 1. The only one that terminates.

`bad` and `err` look identical and are not interchangeable. A check that found a
defect is the answer the command was asked for, so it goes to stdout and survives
`meetlat zeef response.txt > report.txt`. `err` is for the run itself going wrong,
which belongs on stderr where it will not be mistaken for a result.

For a run with several phases:

    banner   ⬢ accent    the opening line: what is running, and how much of it
    Spinner    cyan      a braille frame and elapsed time while a step runs
    counter    dim       the `[n/N]` prefix on a step's verdict line
    step     ▰▱ green    a phase heading with a filled progress bar
    box      ┌─ red      a failing command's own output, fenced as quoted
    rule       dim       a horizontal divider, closing off a block of steps
    verdict  ✔✘ bold     the whole run's outcome, at column 0 rather than indented
    duration             `0.4s`, `1m12s`

`verdict` is the one line that is not indented. Everything else nests under a banner;
the verdict is what the banner was leading to, so it sits level with it.

`accent` is the project colour and is only ever branding. Status keeps the four
that mean something, because a reader who has learned that green is a pass should
not have to work out what the accent is claiming.

Animation is gated on `animated`, which is true only for a real terminal, never for
`FORCE_COLOR` alone. That variable is set to capture colour *into a file*, where a
redrawn line leaves a smear of escapes rather than a spinner.
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from typing import Final, Iterable, Sequence, TextIO


@dataclass(frozen=True, slots=True)
class Palette:
    bold: str = ""
    dim: str = ""
    reset: str = ""
    red: str = ""
    green: str = ""
    yellow: str = ""
    blue: str = ""
    cyan: str = ""
    magenta: str = ""
    #: The project accent, for banners and branding. Never for status: a reader who
    #: has learned that green means pass should not have to wonder what accent means.
    accent: str = ""
    #: True when the stream can be redrawn: `\r`, cursor moves, a spinner. Separate
    #: from colour because a terminal can have one without the other being wanted.
    animated: bool = False

    @staticmethod
    def for_stream(stream: TextIO) -> "Palette":
        if os.environ.get("NO_COLOR") is not None:
            return Palette()
        forced = bool(os.environ.get("FORCE_COLOR"))
        tty = hasattr(stream, "isatty") and stream.isatty()
        if not (forced or tty) or os.environ.get("TERM") == "dumb":
            return Palette()
        # 256 colours get a truer accent; 8-colour terminals fall back to cyan rather
        # than emitting a code that renders as garbage.
        rich = "256color" in os.environ.get("TERM", "") or bool(os.environ.get("COLORTERM"))
        return Palette(
            bold="\033[1m",
            dim="\033[2m",
            reset="\033[0m",
            red="\033[31m",
            green="\033[32m",
            yellow="\033[33m",
            blue="\033[34m",
            cyan="\033[36m",
            magenta="\033[35m",
            accent="\033[38;5;39m" if rich else "\033[36m",
            # Only a real terminal, never FORCE_COLOR alone: that is set to capture
            # colour into a file, where a redrawn line becomes a smear of escapes.
            animated=tty,
        )


C: Final = Palette.for_stream(sys.stdout)
CE: Final = Palette.for_stream(sys.stderr)

INDENT: Final = "  "

#: The mark a multi-step run opens with.
GLYPH: Final = "⬢"


def say(text: str = "", *, stderr: bool = False) -> None:
    print(text, file=sys.stderr if stderr else sys.stdout)


def heading(text: str, *, stderr: bool = False) -> None:
    """A section title. `stderr=True` keeps it in order with the `err` lines under it."""
    palette, stream = (CE, sys.stderr) if stderr else (C, sys.stdout)
    print(f"\n{palette.bold}{text}{palette.reset}", file=stream)


def ok(text: str) -> None:
    print(f"{INDENT}{C.green}✔{C.reset} {text}")


def bad(text: str) -> None:
    print(f"{INDENT}{C.red}✘{C.reset} {text}")


def skip(label: str, reason: str, *, width: int = 0) -> None:
    """A step that did not run, and why. Not a pass: a reader must be able to tell."""
    print(f"{INDENT}{C.dim}○ {label.ljust(width)}  {reason}{C.reset}")


def warn(text: str) -> None:
    print(f"{INDENT}{C.yellow}▲{C.reset} {text}")


def note(text: str, *, stderr: bool = False) -> None:
    palette, stream = (CE, sys.stderr) if stderr else (C, sys.stdout)
    print(f"{INDENT}{palette.dim}{text}{palette.reset}", file=stream)


def line(text: str, *, indent: int = 8, stderr: bool = False) -> None:
    """A continuation line under a status line. Compose colour from `C`, never inline."""
    print(" " * indent + text, file=sys.stderr if stderr else sys.stdout)


def stat(text: str) -> None:
    """A measurement, marked as one. A distribution check has no verdict to report."""
    print(f"{INDENT}{C.dim}◦ {text}{C.reset}")


def err(text: str) -> None:
    print(f"{INDENT}{CE.red}✘{CE.reset} {text}", file=sys.stderr)


def fail(text: str) -> None:
    err(text)
    raise SystemExit(1)


def step(index: int, total: int, title: str) -> None:
    """A phase of a multi-step flow, with the [n/N] counter and a ▰▱ bar."""
    bar = f"{C.green}{'▰' * index}{C.reset}{C.dim}{'▱' * max(0, total - index)}{C.reset}"
    print(f"\n{C.bold}{C.cyan}[{index}/{total}]{C.reset} {bar}  {C.bold}{title}{C.reset}")


def counter(index: int, total: int) -> str:
    """The `[n/N]` prefix, for a caller composing its own status line."""
    return f"{C.dim}[{index}/{total}]{C.reset}"


def banner(name: str, detail: str = "") -> None:
    """The opening line of a multi-step run: `⬢ name  detail`."""
    tail = f"  {C.dim}{detail}{C.reset}" if detail else ""
    print(f"\n{C.bold}{C.accent}{GLYPH} {name}{C.reset}{tail}")


def verdict(passed: bool, text: str) -> None:
    """The whole run's outcome, at column 0 because it answers the banner."""
    glyph = f"{C.green}✔{C.reset}" if passed else f"{C.red}✘{C.reset}"
    print(f"{glyph} {C.bold}{text}{C.reset}")


def rule(label: str = "") -> None:
    width = min(shutil.get_terminal_size((80, 24)).columns, 72)
    line = "─" * max(0, width - len(label) - (1 if label else 0))
    print(f"{C.dim}{label}{' ' if label else ''}{line}{C.reset}")


def duration(seconds: float) -> str:
    """`0.4s` or `1m12s`. Sub-minute keeps a decimal; past that it stops mattering."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"


def box(text: str, *, title: str = "output", stderr: bool = False) -> None:
    """A failing command's output, fenced so it reads as quoted rather than as ours.

    Defaults to stdout: inside a run report the quoted output is part of the report,
    and splitting it from the step lines above it reorders the two in any pipe.
    """
    palette, stream = (CE, sys.stderr) if stderr else (C, sys.stdout)
    width = min(shutil.get_terminal_size((80, 24)).columns, 72)
    head = f"┌─ {title} "
    print(f"{palette.red}{head}{'─' * max(0, width - len(head))}{palette.reset}", file=stream)
    for text_line in text.splitlines():
        print(f"  {text_line}", file=stream)
    print(f"{palette.red}└{'─' * max(0, width - 1)}{palette.reset}", file=stream)


class Spinner:
    """A braille spinner with elapsed time, on a terminal and nowhere else.

    It owns one line and clears it on the way out, so the caller prints the verdict
    afterwards and the transient frames leave nothing behind. On anything that is not
    an interactive terminal it does nothing at all: a log full of `\\r⠋⠙⠹` is worse
    than no progress indication, and CI logs are read far more often than they are
    watched.

        with Spinner("make preflight"):
            subprocess.run(...)
    """

    FRAMES: Final = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    INTERVAL: Final = 0.08

    def __init__(self, label: str, *, stream: TextIO | None = None) -> None:
        self._label = label
        self._stream = stream if stream is not None else sys.stdout
        self._palette = CE if self._stream is sys.stderr else C
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.started = 0.0

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def __enter__(self) -> "Spinner":
        self.started = time.monotonic()
        if self._palette.animated:
            self._thread = threading.Thread(target=self._draw, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            # Hide-cursor is undone here as well as in the loop: an exception inside
            # the `with` body must never leave the terminal without a cursor.
            self._write("\r\033[2K\033[?25h")

    def _write(self, text: str) -> None:
        try:
            self._stream.write(text)
            self._stream.flush()
        except (OSError, ValueError):
            self._stop.set()

    def _draw(self) -> None:
        p = self._palette
        self._write("\033[?25l")
        frame = 0
        while not self._stop.wait(self.INTERVAL):
            glyph = self.FRAMES[frame % len(self.FRAMES)]
            frame += 1
            self._write(
                f"\r{INDENT}{p.cyan}{glyph}{p.reset} {self._label} "
                f"{p.dim}({duration(self.elapsed)}){p.reset}\033[K"
            )
        self._write("\033[?25h")


def table(rows: Iterable[Sequence[str]], *, indent: str = INDENT) -> None:
    """Left-aligned columns, sized to their content. Plain text, no borders."""
    materialised = [list(row) for row in rows]
    if not materialised:
        return
    widths = [max(len(row[i]) for row in materialised) for i in range(len(materialised[0]))]
    for row in materialised:
        cells = [cell.ljust(widths[i]) for i, cell in enumerate(row)]
        print(indent + "  ".join(cells).rstrip())
