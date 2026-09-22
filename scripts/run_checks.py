#!/usr/bin/env python3
"""Run a named plan of `make` targets, quietly on success and loudly on failure.

Three callers share it: the `pre-commit` and `pre-push` hooks, and `make preflight`.
The presentation lives here rather than in each of them, so every way of running the
battery speaks the same voice (`meetlat.console`) instead of re-deriving its own escape
codes, and a passing run is a few lines rather than four tools\' worth of chatter.

One deliberate simplification against the version this is adapted from, and one
deliberate omission.

**No path scoping.** Deciding which checks a staged change needs is worth it when a
check costs a Docker spin-up. The whole battery here takes about three seconds, so
scoping would cost more to maintain than it saves. A step is skipped only when the
tool it needs is absent, which is a fact about the machine rather than about the diff.

**No staged-snapshot isolation.** The checks read the working tree, so formatting a
file and forgetting to `git add` it passes here and commits the unformatted copy. CI
is the backstop, and the stash-and-restore dance that closes it is a hundred lines
that can lose uncommitted work when it goes wrong.

Fails **open** when the virtualenv is missing. A hook that blocks committing in a
fresh clone is a hook that gets uninstalled before lunch.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meetlat import console  # noqa: E402  (needs the sys.path line above)
from meetlat.console import C  # noqa: E402


@dataclass(frozen=True)
class Step:
    """One `make` target, with what to tell the reader while it runs."""

    target: str
    #: The dim column after the label: what this step actually does.
    detail: str
    #: An executable that must be on PATH, or the step is skipped rather than failed.
    #: Only for tools outside the Python dev dependencies, which `make install` covers.
    requires: str = ""
    #: Print this step's output even when it passes. For the steps that report a
    #: measurement rather than a verdict: the corpus coverage is the thing worth seeing
    #: on a green run, and hiding it is how nobody notices a register stuck at six.
    speak: bool = False

    def unavailable(self) -> str:
        if self.requires and shutil.which(self.requires) is None:
            return f"skipped, {self.requires} not installed"
        return ""


PLANS: dict[str, tuple[Step, ...]] = {
    # Cheap and immediate, so a defect is caught while the change is still in your head.
    "pre-commit": (
        Step("lint", "ruff"),
        Step("format-check", "ruff format"),
        Step("check", "zeef, judges, guards"),
    ),
    # Everything CI runs, plus the secret scan. This is the last point before the work
    # leaves the machine, which is the only place scanning for a committed secret still
    # prevents a disclosure rather than merely reporting one.
    "pre-push": (
        Step("preflight", "lint, types, tests, gates"),
        Step("secrets", "gitleaks, full history", requires="gitleaks"),
    ),
    # Everything CI runs. Not a hook, but the same battery and the same reporting, so
    # `make preflight` and a blocked push tell you the same thing the same way.
    "preflight": (
        Step("lint", "ruff"),
        Step("format-check", "ruff format"),
        Step("typecheck", "mypy"),
        Step("test", "pytest"),
        Step("check", "zeef, judges, guards", speak=True),
        Step("check-adrs", "the ADR index matches the ADRs"),
    ),
}


@dataclass(frozen=True)
class Columns:
    """Widths measured from the steps themselves, so nothing collides at any length."""

    label: int
    detail: int

    @staticmethod
    def measure(steps: tuple[Step, ...]) -> "Columns":
        return Columns(
            label=max(len(step.target) for step in steps),
            detail=max(len(step.detail) for step in steps) + 2,
        )


def _run(step: Step, index: int, total: int, columns: Columns) -> subprocess.CompletedProcess[str]:
    with console.Spinner(f"make {step.target}") as spinner:
        result = subprocess.run(
            # --no-print-directory: a nested make announces every entry and exit, which
            # is four lines of noise around one line of result.
            ["make", "--no-print-directory", step.target],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        elapsed = console.duration(spinner.elapsed)

    glyph = f"{C.green}✔{C.reset}" if result.returncode == 0 else f"{C.red}✘{C.reset}"
    print(
        f"{C.dim}[{index}/{total}]{C.reset} {glyph} {step.target.ljust(columns.label)}  "
        f"{C.dim}{step.detail.ljust(columns.detail)}{elapsed}{C.reset}"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", choices=sorted(PLANS))
    args = parser.parse_args(argv)

    if not (REPO_ROOT / ".venv" / "bin" / "python").exists():
        console.warn(f"{args.plan}: no .venv, skipping. Run `make install` to enable the checks.")
        return 0

    planned = PLANS[args.plan]
    runnable = [step for step in planned if not step.unavailable()]
    columns = Columns.measure(planned)

    console.banner(f"meetlat · {args.plan}", f"{len(runnable)} check(s) to run")
    console.rule()
    for step in planned:
        if reason := step.unavailable():
            console.skip(step.target, reason, width=columns.label)

    started = time.monotonic()
    for index, step in enumerate(runnable, start=1):
        result = _run(step, index, len(runnable), columns)
        if result.returncode == 0:
            if step.speak and (spoken := result.stdout.rstrip()):
                print(spoken)
            continue

        console.box((result.stdout + result.stderr).rstrip(), title=f"make {step.target}")
        # Fail fast: the later steps would report the same root cause, and the fix gets
        # applied once rather than after each of them has had its turn.
        if remaining := len(runnable) - index:
            console.note(f"{remaining} later check(s) not run")
        console.rule()
        console.verdict(False, f"{args.plan} blocked")
        if args.plan != "preflight":
            console.note("Fix the above, or bypass with --no-verify if you know why.")
        return 1

    console.rule()
    elapsed = console.duration(time.monotonic() - started)
    skipped = len(planned) - len(runnable)
    tail = f" · {skipped} skipped" if skipped else ""
    console.verdict(True, f"All checks passed  in {elapsed} · {len(runnable)} run{tail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
