#!/usr/bin/env python3
"""PostToolUse: name the gate an edit just put out of date.

Every source of truth in this repository has something derived from it, and the
derived thing is committed. The failure this prevents is not forgetting the rule; it
is finishing a change, pushing, and learning from CI what a one-line command would
have told you immediately.

It points and never runs. Regeneration is slow and side-effecting, and running it
under an agent mid-task is how a diff grows things nobody asked for (ADR-0006).

Advisory, so it fails open on anything unexpected, and it deduplicates per session:
a hook that says the same thing on every edit is a hook people learn to skim.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

#: path fragment -> what to run, and why it matters.
REMINDERS: list[tuple[str, str]] = [
    ("docs/adr/", "`make adr-index` regenerates docs/adr/README.md; CI fails on a stale index"),
    (
        "judges/",
        "`make check-judges`: editing a prompt makes this a new judge, which needs a version "
        "bump and a fresh calibration before it may report numbers (ADR-0003)",
    ),
    (
        "src/meetlat/zeef/",
        "`make check-zeef`: a check needs a fixture with exact spans, and it must stay silent "
        "on tests/corpora/clean_nl.jsonl (ADR-0002, ADR-0007)",
    ),
    (
        "src/meetlat/resources/",
        "`make check-zeef`: a new phrase must not fire on the clean corpus (ADR-0002)",
    ),
    ("Makefile", "`.github/workflows/ci.yml` calls these targets; keep the two in step"),
]


def _already_said(session: str, key: str) -> bool:
    marker = Path(tempfile.gettempdir()) / f"meetlat-hook-{session}-{key.replace('/', '_')}"
    if marker.exists():
        return True
    marker.touch()
    return False


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        path = str((payload.get("tool_input") or {}).get("file_path", ""))
        session = str(payload.get("session_id", "nosession"))
    except Exception:
        return
    if not path:
        return

    relative = os.path.relpath(path, os.environ.get("CLAUDE_PROJECT_DIR", "."))
    for fragment, hint in REMINDERS:
        if fragment in relative and not _already_said(session, fragment):
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PostToolUse",
                            "additionalContext": f"You edited {relative}. {hint}",
                        }
                    }
                )
            )
            return


if __name__ == "__main__":
    main()
