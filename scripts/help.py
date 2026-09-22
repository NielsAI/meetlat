#!/usr/bin/env python3
"""Render `make help` from the Makefile's own comments, in the CLI's voice.

The targets and their descriptions live in one place, the Makefile, so a target
cannot be added without its help line or keep a description that has gone stale.
A `##` comment after a target is its description; a `#=` line opens a section.

Stdlib only, and it imports nothing from meetlat but `console`, so `make help`
works in a fresh clone before anything is installed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meetlat import console  # noqa: E402  (needs the sys.path line above)
from meetlat.console import C  # noqa: E402

_SECTION = re.compile(r"^#=\s*(?P<title>.+)$")
_TARGET = re.compile(r"^(?P<name>[a-zA-Z][a-zA-Z0-9_-]*):.*?##\s*(?P<help>.+)$")


def main() -> int:
    console.heading("meetlat · make")
    rows: list[tuple[str, str]] = []
    for line in (REPO_ROOT / "Makefile").read_text(encoding="utf-8").splitlines():
        if section := _SECTION.match(line):
            if rows:
                console.table(rows)
                rows = []
            print(f"\n{C.dim}{section.group('title')}{C.reset}")
        elif target := _TARGET.match(line):
            rows.append((f"{C.cyan}{target.group('name')}{C.reset}", target.group("help")))
    console.table(rows)
    console.say()
    console.note("ARGS=… passes arguments through, e.g. make test ARGS=-k agreement")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
