"""The zeef's own gate, run as a test so a failure shows up in `pytest` too."""

from __future__ import annotations

import gzip
from pathlib import Path

import check_zeef_contract
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


def test_a_vendored_resource_is_audited_whatever_its_extension(tmp_path: Path) -> None:
    """ADR-0008 stores the OpenTaal list gzipped, and a `*.txt` glob would not see it."""
    resources = tmp_path / "src" / "meetlat" / "resources"
    resources.mkdir(parents=True)
    (tmp_path / "NOTICE").write_text("nothing vendored here", encoding="utf-8")
    header = "# SPDX-License-Identifier: BSD-3-Clause\n# Origin: vendored\nwoord\n"
    with gzip.open(resources / "opentaal-wordlist.txt.gz", "wt", encoding="utf-8") as handle:
        handle.write(header)

    findings: list[check_zeef_contract.Finding] = []
    check_zeef_contract._audit_resource_licences(tmp_path, findings)

    assert [f.what for f in findings] == [
        "vendored but 'opentaal-wordlist.txt.gz' does not appear in NOTICE"
    ]


def test_a_check_the_corpus_cannot_reach_must_be_covered_by_its_fixture() -> None:
    """Nothing published mixes formal `u` with impersonal `je`, so the fixture carries it."""
    findings: list[check_zeef_contract.Finding] = []
    check_zeef_contract._audit_exercise_coverage(REPO_ROOT, [], findings)
    # Every verdict check is uncovered by an empty corpus, so this passes only because
    # each one's fixture holds a silent case matching what would exercise it.
    assert findings == []


def test_losing_that_silent_case_fails_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    unreachable = check_zeef_contract.Exercise("something no fixture contains", lambda text: False)
    monkeypatch.setitem(check_zeef_contract.EXERCISED_BY, "register_consistency", unreachable)
    findings: list[check_zeef_contract.Finding] = []
    check_zeef_contract._audit_exercise_coverage(REPO_ROOT, [], findings)
    assert [f.where for f in findings] == ["register_consistency"]
    assert "nothing tests it" in findings[0].what
