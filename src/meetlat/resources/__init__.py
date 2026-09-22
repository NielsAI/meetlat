"""Word and phrase lists, loaded as data so a list can grow without a code change."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_HERE = Path(__file__).parent


@lru_cache(maxsize=None)
def phrase_list(name: str) -> tuple[str, ...]:
    """Read `<name>.txt`, dropping blank lines and `#` comments.

    Cached because layer 1 runs on every generation and these files never change
    within a process.
    """
    raw = (_HERE / f"{name}.txt").read_text(encoding="utf-8")
    lines = (line.strip() for line in raw.splitlines())
    return tuple(line.lower() for line in lines if line and not line.startswith("#"))
