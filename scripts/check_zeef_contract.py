#!/usr/bin/env python3
"""Hold every check in the zeef to the two rules it was admitted under (ADR-0002).

A check either has no false positives or it reports a distribution rather than a
verdict. And every finding names the span it fired on. Both are prose in an ADR, which
means neither survives contact with a hurried evening unless something checks them.

So this does:

  * **Every registered check has a fixture.** `tests/fixtures/<name>.json`, with
    cases it fires on and cases it must stay silent on. A check with no fixture is a
    claim with no evidence, and it fails the gate rather than joining the registry.
  * **Spans are exact.** A `fires` case lists the literal text of every span, in
    order. This is what makes a finding debuggable rather than discouraging: when a
    span drifts, the fixture says so.
  * **The clean corpus stays clean.** Every verdict check runs over every line of
    `tests/corpora/clean_nl.txt`, natural Dutch written by a person. One firing there
    is a false positive, and a check that cries wolf gets switched off.
  * **Distribution checks report no verdicts** and verdict checks report no metrics,
    so nobody can quietly turn a tunable number into a pass or a fail.
  * **Every wordlist says where it came from.** A vendored list arrives under its own
    licence beside Apache-2.0 code, and one that NOTICE does not name fails the build.

`audit()` takes a repository root so `tests/test_zeef_contract.py` can point it at a
fixture tree. Exits 1 on any finding.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meetlat import console, zeef  # noqa: E402  (needs the sys.path line above)
from meetlat.types import Check, CheckContractError  # noqa: E402
from meetlat.zeef import fixtures  # noqa: E402


@dataclass(frozen=True)
class Finding:
    where: str
    what: str


def corpus_lines(path: Path) -> list[str]:
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _audit_fixture(check: Check, fixture: fixtures.Fixture, where: str, out: list[Finding]) -> None:
    if fixture.kind != check.kind:
        out.append(Finding(where, f"declares kind {fixture.kind!r}, registry says {check.kind!r}"))
    if fixture.check != check.name:
        out.append(Finding(where, f"names check {fixture.check!r}, registered as {check.name!r}"))

    for case in fixture.fires:
        result = check.run(case.text)
        result.validate(case.text)
        actual = [f.span.text for f in result.findings]
        if actual != case.spans:
            out.append(Finding(where, f"spans {actual} != expected {case.spans}"))

    for text in fixture.silent:
        if check.run(text).findings:
            out.append(Finding(where, f"fired on a silent case: {text[:60]!r}"))

    for metrics_case in fixture.metrics:
        result = check.run(metrics_case.text)
        result.validate(metrics_case.text)
        for metric, expected in metrics_case.expect.items():
            actual_value = result.metrics.get(metric)
            if actual_value != expected:
                out.append(Finding(where, f"{metric}={actual_value} != expected {expected}"))


def _audit_resource_licences(repo_root: Path, out: list[Finding]) -> None:
    """Every wordlist says where it came from, and a vendored one is named in NOTICE.

    The `spelling` check needs the OpenTaal wordlist, which arrives under its own
    licence beside Apache-2.0 code. Vendoring a list is a one-line act and attributing
    it is a separate one, which is exactly the pair that comes apart. So the second is
    not remembered: a list declaring `Origin: vendored` that NOTICE does not mention
    fails the build.
    """
    notice = (repo_root / "NOTICE").read_text(encoding="utf-8")
    for path in sorted((repo_root / "src" / "meetlat" / "resources").glob("*.txt")):
        where = f"src/meetlat/resources/{path.name}"
        header = "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()[:5]
            if line.startswith("#")
        )
        if "SPDX-License-Identifier:" not in header:
            out.append(Finding(where, "no `# SPDX-License-Identifier:` in the first lines"))
        if "Origin:" not in header:
            out.append(Finding(where, "no `# Origin:` saying whether this list was vendored"))
        elif "Origin: vendored" in header and path.stem not in notice:
            out.append(Finding(where, f"vendored but {path.stem!r} does not appear in NOTICE"))


def audit(repo_root: Path) -> list[Finding]:
    """Every contract violation across the registry, its fixtures and the clean corpus."""
    out: list[Finding] = []
    fixture_dir = repo_root / "tests" / "fixtures"
    registered = {check.name: check for check in zeef.CHECKS}
    _audit_resource_licences(repo_root, out)

    for name, check in registered.items():
        if not check.description.strip():
            out.append(Finding(name, "has no description; `meetlat checks` would show a blank"))
        if not (type(check).__doc__ or sys.modules[type(check).__module__].__doc__):
            out.append(Finding(name, "has no docstring saying what defect it catches"))

        path = fixture_dir / f"{name}.json"
        if not path.exists():
            out.append(Finding(name, f"no fixture at tests/fixtures/{name}.json"))
            continue
        where = f"tests/fixtures/{name}.json"
        try:
            _audit_fixture(check, fixtures.load(path), where, out)
        except CheckContractError as exc:
            out.append(Finding(where, f"contract violation: {exc}"))
        except ValueError as exc:
            out.append(Finding(where, f"malformed fixture: {exc}"))

    for path in sorted(fixture_dir.glob("*.json")):
        if path.stem not in registered:
            out.append(Finding(f"tests/fixtures/{path.name}", "fixture for no registered check"))

    corpus = repo_root / "tests" / "corpora" / "clean_nl.txt"
    for line_no, line in enumerate(corpus_lines(corpus), start=1):
        for check in zeef.CHECKS:
            if check.kind != "verdict":
                continue
            for finding in check.run(line).findings:
                out.append(
                    Finding(
                        f"tests/corpora/clean_nl.txt:{line_no}",
                        f"false positive in {check.name}: {finding.span.text!r}",
                    )
                )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root to audit")
    args = parser.parse_args(argv)

    findings = audit(args.root)
    if not findings:
        clean = len(corpus_lines(args.root / "tests" / "corpora" / "clean_nl.txt"))
        planned = ", ".join(zeef.PLANNED) or "none"
        console.ok(
            f"zeef contract ok · {len(zeef.CHECKS)} checks · {clean} clean lines · "
            f"planned: {planned}"
        )
        return 0

    console.heading("zeef contract violations (ADR-0002)", stderr=True)
    for finding in findings:
        console.err(f"{console.CE.bold}{finding.where}{console.CE.reset}: {finding.what}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
