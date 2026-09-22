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
  * **The clean corpus stays clean.** Every verdict check runs over every paragraph
    of `tests/corpora/clean_nl.jsonl`, natural Dutch written by a person. One firing
    there is a false positive, and a check that cries wolf gets switched off. Each
    paragraph carries its provenance and licence, and the per-register counts are
    printed so a corpus that covers one register cannot pass for breadth (ADR-0007).
  * **Distribution checks report no verdicts** and verdict checks report no metrics,
    so nobody can quietly turn a tunable number into a pass or a fail.
  * **Every wordlist says where it came from.** A vendored list arrives under its own
    licence beside Apache-2.0 code, and one that NOTICE does not name fails the build.

`audit()` takes a repository root so `tests/test_zeef_contract.py` can point it at a
fixture tree. Exits 1 on any finding.
"""

from __future__ import annotations

import argparse
import gzip
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meetlat import console, zeef  # noqa: E402  (needs the sys.path line above)
from meetlat.types import Check, CheckContractError  # noqa: E402
from meetlat.zeef import corpus, fixtures  # noqa: E402
from meetlat.zeef.checks import register_consistency, self_repetition  # noqa: E402


@dataclass(frozen=True)
class Finding:
    where: str
    what: str


def corpus_path(repo_root: Path) -> Path:
    return repo_root / "tests" / "corpora" / "clean_nl.jsonl"


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


@dataclass(frozen=True)
class Exercise:
    """What a corpus paragraph must contain before it tests a verdict check at all.

    Only verdict checks appear here. A distribution can never fail, so no corpus
    paragraph is evidence about it; a verdict check is the thing the corpus exists to
    keep honest, and a paragraph it cannot reach is not evidence that it stays quiet on
    correct Dutch. It is evidence that the check was never asked.
    """

    needs: str
    holds: Callable[[str], bool]


#: One row per registered verdict check, enforced below the way fixtures are: a check
#: nobody wrote a row for is a check whose coverage silently reads as whatever the
#: others happen to give it.
EXERCISED_BY: dict[str, Exercise] = {
    # Only one near-miss can legitimately sit in a clean corpus. A formal marker beside
    # `jij` or `jullie` is genuinely mixed register, the check fires on it, and an entry
    # like that would fail this very gate. What tests the narrowing is a formal marker
    # beside bare `je`, the impersonal reading the check was narrowed to ignore. The
    # check's own patterns are reused so a marker means the same thing in both places.
    "register_consistency": Exercise(
        "a formal marker beside impersonal `je`, and no `jij` or `jullie`",
        lambda text: bool(
            register_consistency._FORMAL.search(text)
            and register_consistency._ALL_INFORMAL.search(text)
            and not register_consistency._UNAMBIGUOUS.search(text)
        ),
    ),
    # Phrase lookups run over the whole text, so any correct Dutch is evidence that
    # they do not fire on it.
    "translationese": Exercise("any prose", lambda text: bool(text.split())),
    "meta_commentary": Exercise("any prose", lambda text: bool(text.split())),
    "self_repetition": Exercise(
        f"at least {self_repetition.WINDOW * 2} words, or no window can repeat",
        lambda text: len(text.split()) >= self_repetition.WINDOW * 2,
    ),
}


def _audit_tag_definitions(out: list[Finding]) -> None:
    """Every register and domain says what it means.

    A tag with no definition is applied differently in the first hour of review than in
    the third, and the corpus is then tagged by a rule that drifted rather than by one
    rule. The reviewer shows these while you choose, so an undefined tag is also a blank
    line in the only place the choice is made.
    """
    for value in get_args(corpus.Register):
        if value not in corpus.REGISTER_MEANS:
            out.append(
                Finding(f"register {value!r}", "no entry in REGISTER_MEANS saying what it is")
            )
    for value in get_args(corpus.Domain):
        if value not in corpus.DOMAIN_MEANS:
            out.append(Finding(f"domain {value!r}", "no entry in DOMAIN_MEANS saying what it is"))


def _audit_exercise_rows(out: list[Finding]) -> None:
    for check in zeef.CHECKS:
        if check.kind == "verdict" and check.name not in EXERCISED_BY:
            out.append(Finding(check.name, "no EXERCISED_BY row saying what would test it"))


def exercise_counts(entries: list[corpus.CorpusEntry]) -> dict[str, int]:
    return {
        name: sum(1 for entry in entries if rule.holds(entry.text))
        for name, rule in EXERCISED_BY.items()
    }


def _audit_exercise_coverage(
    repo_root: Path, entries: list[corpus.CorpusEntry], out: list[Finding]
) -> None:
    """A verdict check the corpus cannot reach has to be reached by its fixture instead.

    Some near-misses do not occur in published Dutch at all. Nothing edited mixes a
    formal `u` with impersonal `je`: 190 corpus entries and 208 collected candidates
    contain not one, because style guides forbid it and editors remove it. So no corpus
    of collected paragraphs will ever test that narrowing, which makes it a fact about
    the language rather than a gap to keep warning about.

    A warning nobody can clear is the thing this project says a check must never be, so
    the case moves to the fixture, where a constructed silent sentence can do what
    collected text cannot, and it is required there rather than hoped for.
    """
    for name, count in exercise_counts(entries).items():
        if count:
            continue
        try:
            silent = fixtures.load(repo_root / "tests" / "fixtures" / f"{name}.json").silent
        except (OSError, ValueError):
            continue  # the fixture audit above already reported this
        if not any(EXERCISED_BY[name].holds(text) for text in silent):
            out.append(
                Finding(
                    name,
                    f"nothing tests it: no corpus paragraph has {EXERCISED_BY[name].needs}, "
                    f"and neither does any silent case in its fixture",
                )
            )


def _audit_resource_licences(repo_root: Path, out: list[Finding]) -> None:
    """Every wordlist says where it came from, and a vendored one is named in NOTICE.

    The `spelling` check needs the OpenTaal wordlist, which arrives under its own
    licence beside Apache-2.0 code. Vendoring a list is a one-line act and attributing
    it is a separate one, which is exactly the pair that comes apart. So the second is
    not remembered: a list declaring `Origin: vendored` that NOTICE does not mention
    fails the build.
    """
    notice = (repo_root / "NOTICE").read_text(encoding="utf-8")
    for path in sorted((repo_root / "src" / "meetlat" / "resources").iterdir()):
        if path.is_dir() or path.suffix == ".py":
            continue
        where = f"src/meetlat/resources/{path.name}"
        header = _resource_header(path)
        if "SPDX-License-Identifier:" not in header:
            out.append(Finding(where, "no `# SPDX-License-Identifier:` in the first lines"))
        if "Origin:" not in header:
            out.append(Finding(where, "no `# Origin:` saying whether this list was vendored"))
        # The file's own name, not a stem: an upstream project URL contains the stem, so
        # a NOTICE that only links the project would satisfy a looser check by accident.
        elif "Origin: vendored" in header and path.name not in notice:
            out.append(Finding(where, f"vendored but {path.name!r} does not appear in NOTICE"))


def _resource_header(path: Path) -> str:
    """The comment lines a resource opens with, compressed or not.

    ADR-0008 stores the OpenTaal list gzipped, and a gate that only globbed `*.txt`
    would not see the one file that ADR is about: the check would pass by not looking.
    The extension decides how to read a resource, never whether to.
    """
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
            text = handle.read(4096)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")[:4096]
    return "\n".join(line for line in text.splitlines()[:5] if line.startswith("#"))


def audit(repo_root: Path) -> list[Finding]:
    """Every contract violation across the registry, its fixtures and the clean corpus."""
    out: list[Finding] = []
    fixture_dir = repo_root / "tests" / "fixtures"
    registered = {check.name: check for check in zeef.CHECKS}
    _audit_resource_licences(repo_root, out)
    _audit_exercise_rows(out)
    _audit_tag_definitions(out)

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

    try:
        entries = corpus.load(corpus_path(repo_root))
    except (OSError, ValueError) as exc:
        out.append(Finding("tests/corpora/clean_nl.jsonl", str(exc)))
        return out

    _audit_exercise_coverage(repo_root, entries, out)

    for entry in entries:
        for check in zeef.CHECKS:
            if check.kind != "verdict":
                continue
            for finding in check.run(entry.text).findings:
                out.append(
                    Finding(
                        f"tests/corpora/clean_nl.jsonl#{entry.id}",
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
        entries = corpus.load(corpus_path(args.root))
        console.ok(f"zeef contract ok · {len(zeef.CHECKS)} checks · {len(entries)} corpus entries")
        counts = corpus.coverage(entries)
        console.note(
            "corpus by register: "
            + "  ".join(f"{register} {count}" for register, count in counts.items())
        )
        # An entry counted as a paragraph while being shorter than one is how a corpus
        # reads as several times the evidence it is, so the shortfall is printed.
        measured = corpus.shape(entries)
        console.note(
            f"corpus shape: {measured['words']} words, {measured['below_floor']} of "
            f"{len(entries)} below the {corpus.MIN_CHARS}-character paragraph floor, "
            f"{measured['redacted']} edited after collection"
        )
        # A verdict check no paragraph can reach passes this gate without being tested,
        # which reads exactly like passing it. So the reach is printed, not inferred.
        exercised = exercise_counts(entries)
        console.note(
            "corpus exercises: " + "  ".join(f"{name} {count}" for name, count in exercised.items())
        )
        # Reaching here means the audit found a silent fixture case for every check the
        # corpus cannot reach, so this reports where the cover is rather than warning.
        for name, count in exercised.items():
            if count == 0:
                console.note(
                    f"{name}: no corpus paragraph has {EXERCISED_BY[name].needs}, "
                    f"so its fixture carries that case instead"
                )
        # An empty register is named, not left to be inferred from a total (ADR-0007).
        if empty := [register for register, count in counts.items() if count == 0]:
            console.warn(f"no paragraphs for: {', '.join(empty)}")
        if planned := ", ".join(zeef.PLANNED):
            console.note(f"checks designed but not built: {planned}")
        return 0

    console.heading("zeef contract violations (ADR-0002)", stderr=True)
    for finding in findings:
        console.err(f"{console.CE.bold}{finding.where}{console.CE.reset}: {finding.what}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
