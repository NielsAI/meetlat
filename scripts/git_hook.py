#!/usr/bin/env python3
"""Run a hook's `make` targets, quietly on success and loudly on failure.

The presentation lives here rather than in three shell scripts, so the hooks speak the
same voice as everything else (`meetlat.console`) instead of each re-deriving its own
escape codes.

Two deliberate simplifications against the version this is adapted from, both because
this repository's whole battery runs in about three seconds:

  * **No path scoping.** Deciding which checks a staged change needs is worth it when a
    check costs a Docker spin-up. Here it would cost more to maintain than it saves.
  * **No staged-snapshot isolation.** The checks read the working tree, so formatting a
    file and forgetting to `git add` it passes here and commits the unformatted copy.
    CI is the backstop for that, and the stash-and-restore dance that closes it is a
    hundred lines that can lose uncommitted work when it goes wrong.

Fails **open** when the virtualenv is missing. A hook that blocks committing in a fresh
clone is a hook that gets uninstalled before lunch.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meetlat import console  # noqa: E402  (needs the sys.path line above)
from meetlat.console import C  # noqa: E402

#: hook name -> the make targets it runs, in order.
PLANS: dict[str, tuple[str, ...]] = {
    # Cheap and immediate: the three offline gates plus formatting, so a defect is
    # caught while the change is still in your head.
    "pre-commit": ("lint", "format-check", "check"),
    # Everything CI runs. `make preflight` green means green on push, and this is what
    # makes that a fact rather than a habit.
    "pre-push": ("preflight",),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hook", choices=sorted(PLANS))
    args = parser.parse_args(argv)

    if not (REPO_ROOT / ".venv" / "bin" / "python").exists():
        console.warn(f"{args.hook}: no .venv, skipping. Run `make install` to enable the checks.")
        return 0

    targets = PLANS[args.hook]
    console.banner(args.hook, f"{len(targets)} step{'s' if len(targets) != 1 else ''}")
    started = time.monotonic()

    for index, target in enumerate(targets, start=1):
        label = f"make {target}"
        with console.Spinner(label) as spinner:
            result = subprocess.run(
                ["make", target], cwd=REPO_ROOT, capture_output=True, text=True, check=False
            )
            elapsed = console.duration(spinner.elapsed)

        prefix = f"{console.counter(index, len(targets))} {label}"
        if result.returncode == 0:
            console.ok(f"{prefix}  {C.dim}{elapsed}{C.reset}")
            continue

        console.bad(f"{prefix}  {C.dim}{elapsed}{C.reset}")
        console.box((result.stdout + result.stderr).rstrip(), title=label)
        # Fail fast: the later steps would report the same root cause, and the fix gets
        # applied once rather than after each of them has had its turn.
        skipped = len(targets) - index
        if skipped:
            console.note(f"{skipped} later step(s) not run", stderr=True)
        console.bad(
            f"{args.hook} blocked · fix the above, or bypass with "
            f"{C.bold}--no-verify{C.reset} if you know why"
        )
        return 1

    console.ok(f"{args.hook} ok · {console.duration(time.monotonic() - started)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
