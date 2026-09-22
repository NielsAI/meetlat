"""The ijk (layer 3): does a judge agree with a human often enough to be believed.

The gold set is not a benchmark and nothing is scored against it for its own sake.
It is hand-labelled, fixed in size, and it exists to answer one question about one
judge. Two numbers answer it, and both are computed here rather than kept in a
spreadsheet, because a number nobody can recompute is a number nobody can check.
"""

from __future__ import annotations

from meetlat.ijk.agreement import Agreement, balanced_accuracy, cohen_kappa, score
from meetlat.ijk.gold import GoldItem

__all__ = ["Agreement", "GoldItem", "balanced_accuracy", "cohen_kappa", "score"]
