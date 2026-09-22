"""Word and phrase lists, loaded as data so a list can grow without a code change."""

from __future__ import annotations

import gzip
from functools import lru_cache
from pathlib import Path

_HERE = Path(__file__).parent


@lru_cache(maxsize=None)
def phrase_pairs(name: str) -> tuple[tuple[str, str], ...]:
    """Read a `left : right` list. The right side documents why the left qualifies.

    Kept separate from `phrase_list` because a list whose entries carry their own
    justification is a different artifact from a bare list of strings, and flattening
    one into the other loses the part a reviewer needs.
    """
    pairs = []
    for line in phrase_list(name):
        left, _, right = line.partition(":")
        if not right.strip():
            raise ValueError(f"{name}.txt: {line!r} has no ` : ` and its equivalent")
        pairs.append((left.strip(), right.strip()))
    return tuple(pairs)


@lru_cache(maxsize=None)
def phrase_list(name: str) -> tuple[str, ...]:
    """Read `<name>.txt`, dropping blank lines and `#` comments.

    Cached because layer 1 runs on every generation and these files never change
    within a process.
    """
    raw = (_HERE / f"{name}.txt").read_text(encoding="utf-8")
    lines = (line.strip() for line in raw.splitlines())
    return tuple(line.lower() for line in lines if line and not line.startswith("#"))


@lru_cache(maxsize=None)
def word_set(name: str) -> frozenset[str]:
    """Read `<name>.txt.gz` into a set, dropping the leading `#` header lines.

    A separate loader rather than a `phrase_list` option: this file is gzipped and
    413,937 entries need set membership, not the ordered tuple the phrase lists
    return. Cached because layer 1 runs on every generation and decompressing this
    file per call would make `spelling` the slowest check by a wide margin.
    """
    with gzip.open(_HERE / f"{name}.txt.gz", "rt", encoding="utf-8") as handle:
        return frozenset(line.strip().lower() for line in handle if not line.startswith("#"))
