"""The zeef's own gate, run as a test so a failure shows up in `pytest` too."""

from __future__ import annotations

import pytest
from check_zeef_contract import REPO_ROOT, audit

from meetlat import zeef
from meetlat.types import CheckContractError, CheckResult, Finding, Span


def test_every_check_satisfies_the_contract() -> None:
    findings = audit(REPO_ROOT)
    assert not findings, "\n".join(f"{f.where}: {f.what}" for f in findings)


def test_planned_checks_are_not_registered() -> None:
    """A planned check is a visible gap, not a check that half exists."""
    assert not set(zeef.PLANNED) & {c.name for c in zeef.CHECKS}


def test_unknown_check_name_is_an_error() -> None:
    with pytest.raises(KeyError):
        zeef.run("tekst", only=("geen_check",))


def test_a_span_that_does_not_resolve_is_refused() -> None:
    text = "Dit is de tekst."
    result = CheckResult(
        check="x",
        kind="verdict",
        findings=(Finding("x", "misplaced", Span(0, 3, "Dat")),),
    )
    with pytest.raises(CheckContractError, match="but the response has"):
        result.validate(text)


def test_a_distribution_check_may_not_report_findings() -> None:
    result = CheckResult(
        check="x",
        kind="distribution",
        findings=(Finding("x", "verdict in disguise", Span(0, 3, "Dit")),),
    )
    with pytest.raises(CheckContractError, match="may not report findings"):
        result.validate("Dit is de tekst.")
