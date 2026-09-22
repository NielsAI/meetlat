"""The two numbers layer 3 publishes, against cases worked out by hand."""

from __future__ import annotations

import pytest

from meetlat.ijk import agreement


def test_perfect_agreement() -> None:
    human = [True, False, True, False]
    assert agreement.score(human, human) == agreement.Agreement(4, 1.0, 1.0)


def test_a_judge_that_always_says_yes_scores_zero_kappa() -> None:
    """The failure balanced accuracy exists to expose: confident, useless, and 50% accurate."""
    human = [True, True, False, False]
    result = agreement.score(human, [True] * 4)
    assert result.balanced_accuracy == 0.5
    assert result.cohen_kappa == 0.0


def test_one_miss_in_ten() -> None:
    human = [True] * 5 + [False] * 5
    judge = [True] * 5 + [False] * 4 + [True]
    result = agreement.score(human, judge)
    assert result.balanced_accuracy == 0.9
    assert result.cohen_kappa == 0.8


def test_a_single_class_gold_set_yields_no_number() -> None:
    """Stratification is not a nicety: without both classes there is nothing to measure."""
    with pytest.raises(agreement.NotEnoughEvidence, match="cases expected to fail"):
        agreement.balanced_accuracy([True] * 6, [True] * 6)


def test_mismatched_lengths_are_refused() -> None:
    with pytest.raises(agreement.NotEnoughEvidence):
        agreement.score([True, False], [True])


@pytest.mark.parametrize("threshold_kappa,expected", [(0.6, True), (0.9, False)])
def test_meets_reads_the_policy_from_its_caller(threshold_kappa: float, expected: bool) -> None:
    result = agreement.Agreement(items=10, balanced_accuracy=0.9, cohen_kappa=0.8)
    assert result.meets(min_balanced_accuracy=0.85, min_cohen_kappa=threshold_kappa) is expected
