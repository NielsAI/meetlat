"""The vocabulary the three layers share: spans, findings, and the result of one check.

Two rules from the architecture are encoded here rather than left to reviewers
(ADR-0002). A check is either a `verdict` check, which may only fire where it is
certain, or a `distribution` check, which reports numbers and never a pass or
fail. And every finding carries the span it fired on, so a failing score can be
read back to the words that caused it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Protocol

CheckKind = Literal["verdict", "distribution"]


class CheckContractError(AssertionError):
    """A check produced output that violates the contract in ADR-0002.

    Raised at run time rather than reported as a finding: a span that does not
    resolve is a bug in the check, and a harness that quietly tolerates one
    publishes numbers nobody can audit back to the text.
    """


@dataclass(frozen=True, slots=True)
class Span:
    """A half-open character range into the response being checked."""

    start: int
    end: int
    text: str

    def validate(self, source: str) -> None:
        if self.start < 0 or self.end <= self.start:
            raise CheckContractError(f"span {self.start}:{self.end} is not a forward range")
        if self.end > len(source):
            raise CheckContractError(f"span {self.start}:{self.end} runs past the response")
        if source[self.start : self.end] != self.text:
            raise CheckContractError(
                f"span {self.start}:{self.end} says {self.text!r} "
                f"but the response has {source[self.start : self.end]!r}"
            )


@dataclass(frozen=True, slots=True)
class Finding:
    """One defect, located. `message` is written for the person reading the report."""

    check: str
    message: str
    span: Span


@dataclass(frozen=True, slots=True)
class CheckResult:
    """What one check says about one response.

    A `verdict` check reports findings and leaves `metrics` empty; it has failed
    when `findings` is non-empty. A `distribution` check reports metrics and
    never findings, because it has no threshold to fail against.
    """

    check: str
    kind: CheckKind
    findings: tuple[Finding, ...] = ()
    metrics: Mapping[str, float] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.kind == "verdict" and bool(self.findings)

    def validate(self, source: str) -> None:
        if self.kind == "distribution" and self.findings:
            raise CheckContractError(
                f"{self.check} is a distribution check and may not report findings"
            )
        if self.kind == "verdict" and self.metrics:
            raise CheckContractError(f"{self.check} is a verdict check and may not report metrics")
        for finding in self.findings:
            if finding.check != self.check:
                raise CheckContractError(
                    f"{self.check} emitted a finding attributed to {finding.check}"
                )
            finding.span.validate(source)


class Check(Protocol):
    """One check in the zeef: pure, offline, cheap enough to run on every generation.

    Implementations are module-level singletons registered in `meetlat.zeef`. The
    three attributes are properties rather than plain annotations so a check can be
    a frozen dataclass: a check that can be reconfigured after registration is a
    check whose fixtures no longer describe it.
    """

    @property
    def name(self) -> str: ...

    @property
    def kind(self) -> CheckKind: ...

    @property
    def description(self) -> str:
        """One line, shown in `meetlat checks` and used as the finding's headline."""
        ...

    def run(self, text: str) -> CheckResult: ...


@dataclass(frozen=True, slots=True)
class ZeefReport:
    """Every check's verdict on one response, the zeef's output for one generation."""

    text: str
    results: tuple[CheckResult, ...]

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(f for r in self.results for f in r.findings)

    @property
    def failed_checks(self) -> tuple[str, ...]:
        return tuple(r.check for r in self.results if r.failed)

    @property
    def passed(self) -> bool:
        return not self.failed_checks
