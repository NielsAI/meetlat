"""Balanced accuracy and Cohen's kappa over binary labels.

Both are computed here, from the reconciled human labels and the judge's verdicts,
rather than being carried as numbers in a card. A calibration figure that only
exists as a literal in a JSON file is a claim; one that CI recomputes from the raw
labels on every push is a measurement, which is the distinction the whole project is
about.

Plain accuracy is deliberately absent. A gold set is stratified to include cases
expected to fail, but it is never balanced exactly, and accuracy on a skewed set
rewards a judge that always answers with the majority class.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


class NotEnoughEvidence(ValueError):
    """The labels cannot support an agreement figure, so none is produced.

    Raised rather than returning a number, because the failure mode being guarded
    against is a confident-looking statistic computed from nothing.
    """


@dataclass(frozen=True, slots=True)
class Agreement:
    items: int
    balanced_accuracy: float
    cohen_kappa: float

    def meets(self, *, min_balanced_accuracy: float, min_cohen_kappa: float) -> bool:
        return (
            self.balanced_accuracy >= min_balanced_accuracy and self.cohen_kappa >= min_cohen_kappa
        )


def _confusion(human: Sequence[bool], judge: Sequence[bool]) -> tuple[int, int, int, int]:
    """True positives, true negatives, false positives, false negatives."""
    if len(human) != len(judge):
        raise NotEnoughEvidence(f"{len(human)} human labels against {len(judge)} verdicts")
    if not human:
        raise NotEnoughEvidence("no labels")
    tp = tn = fp = fn = 0
    for actual, predicted in zip(human, judge, strict=True):
        if actual and predicted:
            tp += 1
        elif not actual and not predicted:
            tn += 1
        elif predicted:
            fp += 1
        else:
            fn += 1
    return tp, tn, fp, fn


def balanced_accuracy(human: Sequence[bool], judge: Sequence[bool]) -> float:
    """Mean of sensitivity and specificity: each class counts the same regardless of size."""
    tp, tn, fp, fn = _confusion(human, judge)
    if tp + fn == 0 or tn + fp == 0:
        raise NotEnoughEvidence(
            "the human labels are all one class, so the judge cannot be told from a "
            "constant answer; the gold set needs cases expected to fail"
        )
    return (tp / (tp + fn) + tn / (tn + fp)) / 2


def cohen_kappa(human: Sequence[bool], judge: Sequence[bool]) -> float:
    """Agreement above what two raters would reach by chance alone.

    Returns 1.0 for perfect agreement when chance agreement is also total, which is
    the degenerate case `balanced_accuracy` already refuses; callers compute both.
    """
    tp, tn, fp, fn = _confusion(human, judge)
    n = tp + tn + fp + fn
    observed = (tp + tn) / n
    expected = ((tp + fn) * (tp + fp) + (tn + fp) * (tn + fn)) / (n * n)
    if expected == 1.0:
        return 1.0
    return (observed - expected) / (1 - expected)


def score(human: Sequence[bool], judge: Sequence[bool]) -> Agreement:
    return Agreement(
        items=len(human),
        balanced_accuracy=round(balanced_accuracy(human, judge), 4),
        cohen_kappa=round(cohen_kappa(human, judge), 4),
    )
