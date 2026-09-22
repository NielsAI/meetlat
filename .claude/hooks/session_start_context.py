#!/usr/bin/env python3
"""SessionStart: the branch, the working tree, and how much is actually calibrated.

A session that does not know the tree is dirty proposes work that collides with
whatever is in flight. A session that does not know how many judges are certified
will happily talk about "the pass rate" in a repository that has none yet, which is
the specific confusion this project exists to prevent.

Deliberately small: always-loaded context that grows without limit stops being read.
Read-only and fail-open, so any error starts the session without the context rather
than not at all.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MAX_LINES = 10
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=5, check=False)
    return out.stdout.strip() if out.returncode == 0 else ""


def main() -> None:
    try:
        json.load(sys.stdin)
        # `branch --show-current`, not `rev-parse HEAD`: the latter fails on a branch
        # with no commits yet, which is exactly when a fresh clone starts a session.
        branch = _git("branch", "--show-current")
        status = _git("status", "--short")
    except Exception:
        return
    if not branch:
        return

    lines = [line for line in status.splitlines() if line.strip()]
    if lines:
        more = len(lines) - MAX_LINES
        tree = "\n".join(lines[:MAX_LINES]) + (f"\n… and {more} more" if more > 0 else "")
        body = f"Branch `{branch}`, working tree is dirty:\n{tree}"
    else:
        body = f"Branch `{branch}`, working tree clean."

    certified = len(list((REPO_ROOT / "judges").glob("*/v*/card.json")))
    gold = len(list((REPO_ROOT / "gold").glob("*.jsonl")))
    body += f"\nCalibration: {certified} judge card(s), {gold} gold set(s)."
    if not certified:
        body += " Nothing is calibrated yet, so no pass rate from this repo means anything."

    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": body}}
        )
    )


if __name__ == "__main__":
    main()
