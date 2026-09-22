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
"""

from __future__ import annotations

import os
import shutil
import sys
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
    cyan: str = ""
    magenta: str = ""

    @staticmethod
    def for_stream(stream: TextIO) -> "Palette":
        if os.environ.get("NO_COLOR") is not None:
            return Palette()
        if not (os.environ.get("FORCE_COLOR") or (hasattr(stream, "isatty") and stream.isatty())):
            return Palette()
        if os.environ.get("TERM") == "dumb":
            return Palette()
        return Palette(
            bold="\033[1m",
            dim="\033[2m",
            reset="\033[0m",
            red="\033[31m",
            green="\033[32m",
            yellow="\033[33m",
            cyan="\033[36m",
            magenta="\033[35m",
        )


C: Final = Palette.for_stream(sys.stdout)
CE: Final = Palette.for_stream(sys.stderr)

INDENT: Final = "  "


def say(text: str = "") -> None:
    print(text)


def heading(text: str, *, stderr: bool = False) -> None:
    """A section title. `stderr=True` keeps it in order with the `err` lines under it."""
    palette, stream = (CE, sys.stderr) if stderr else (C, sys.stdout)
    print(f"\n{palette.bold}{text}{palette.reset}", file=stream)


def ok(text: str) -> None:
    print(f"{INDENT}{C.green}✔{C.reset} {text}")


def bad(text: str) -> None:
    print(f"{INDENT}{C.red}✘{C.reset} {text}")


def warn(text: str) -> None:
    print(f"{INDENT}{C.yellow}▲{C.reset} {text}")


def note(text: str) -> None:
    print(f"{INDENT}{C.dim}{text}{C.reset}")


def line(text: str, *, indent: int = 8) -> None:
    """A continuation line under a status line. Compose colour from `C`, never inline."""
    print(" " * indent + text)


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


def rule(label: str = "") -> None:
    width = min(shutil.get_terminal_size((80, 24)).columns, 80)
    line = "─" * max(0, width - len(label) - (1 if label else 0))
    print(f"{C.dim}{label}{' ' if label else ''}{line}{C.reset}")


def table(rows: Iterable[Sequence[str]], *, indent: str = INDENT) -> None:
    """Left-aligned columns, sized to their content. Plain text, no borders."""
    materialised = [list(row) for row in rows]
    if not materialised:
        return
    widths = [max(len(row[i]) for row in materialised) for i in range(len(materialised[0]))]
    for row in materialised:
        cells = [cell.ljust(widths[i]) for i, cell in enumerate(row)]
        print(indent + "  ".join(cells).rstrip())
