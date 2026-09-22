#!/usr/bin/env python3
"""Refuse a write to `gold/*.jsonl` that did not come from a person (ADR-0004, ADR-0006).

A gold set is hand-labelled by two people, and it is the only thing in this system
that is not reproducible. Every number the harness publishes is calibrated against
it. An agent that helpfully regenerates, reformats or "fixes" one of those files
destroys the instrument, silently, and nothing downstream can tell: the judges keep
reporting, the numbers keep looking plausible, and they now mean nothing.

That is the one failure here worth failing closed over. Everything else this
repository guards is recoverable from git or recomputable from source.

Three callers, per ADR-0006:

    --hook       a Claude Code PreToolUse hook on Write/Edit/Bash
    --command    ask about one shell command, for any other tool
    --selftest   the recorded behaviour, also run by tests/test_gold_guard.py

Fails closed on its decision and open on unreadable input: a guard that denies every
call the moment its own payload is malformed gets deleted within a day, and a deleted
guard protects nothing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: The label files themselves, not the directory. `gold/README.md` documents this very
#: rule, and a guard that refuses to let anyone write its own documentation is a guard
#: that gets switched off. The instrument is the JSONL.
GUARDED = r"gold/[^\s'\"]*\.jsonl"

REASON = (
    "gold/*.jsonl holds hand-labelled calibration data: two annotators, reconciled by hand, "
    "and the instrument every published number is measured against (ADR-0004). It is not "
    "generated and not reformatted. Add labels by hand, or ask the user to. If you need "
    "to read it, read it; only writes are refused."
)

#: Shell constructs that write. Matched per line, so a pipeline or an `&&` chain is
#: caught by the half that writes and not by the half that reads.
_WRITING_SHELL = re.compile(
    rf"""
    (>{{1,2}}\s*[^|&;\n]*{GUARDED})             # redirection into a label file
  | (\b(rm|mv|cp|truncate|shred)\b[^|&;\n]*\b{GUARDED})
  | (\b(sed|perl)\b[^|&;\n]*-i[^|&;\n]*{GUARDED})
  | (\btee\b[^|&;\n]*{GUARDED})
  | (\bdd\b[^|&;\n]*of=[^|&;\n]*{GUARDED})
    """,
    re.VERBOSE,
)

_GUARDED_PATH = re.compile(rf"(\A|/){GUARDED}\Z")

#: `cmd <<'TAG' … TAG`. A heredoc body is data on its way somewhere else, not the
#: command. Without this, writing any document that quotes a guarded path is refused,
#: which is a real regression: it blocked writing this repository's own hook
#: documentation. A guard that blocks talking *about* the rule gets routed around.
#: The body starts on the line *after* the opener, so `rest` is kept: a redirection
#: written after the `<<TAG` on the same line is part of the command, not the body.
_HEREDOC = re.compile(
    r"<<-?\s*(['\"]?)(?P<tag>[A-Za-z_][A-Za-z0-9_]*)\1(?P<rest>[^\n]*)\n.*?^(?P=tag)$",
    re.DOTALL | re.MULTILINE,
)


def _without_heredoc_bodies(command: str) -> str:
    """The command with every heredoc body removed, keeping the line that opened it."""
    return _HEREDOC.sub(lambda m: f"<<{m.group('tag')}{m.group('rest')}", command)


def writes_to_gold(tool_name: str, tool_input: dict[str, object]) -> bool:
    """True when this tool call would modify a hand-labelled set."""
    if tool_name in {"Write", "Edit", "NotebookEdit"}:
        return bool(_GUARDED_PATH.search(str(tool_input.get("file_path", "")).lstrip("./")))
    if tool_name == "Bash":
        return bool(
            _WRITING_SHELL.search(_without_heredoc_bodies(str(tool_input.get("command", ""))))
        )
    return False


def _deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def run_hook() -> int:
    try:
        payload = json.load(sys.stdin)
        tool_name = str(payload.get("tool_name", ""))
        tool_input = payload.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            return 0
    except Exception:
        return 0  # fail open on unreadable input
    if writes_to_gold(tool_name, tool_input):
        _deny(REASON)
    return 0


#: (tool, input, should be denied). Rows 5 to 8 are the ones worth keeping: a guard
#: that also blocks reading, or a path that merely mentions the word, is a guard people
#: route around.
SELFTEST: list[tuple[str, dict[str, object], bool]] = [
    ("Write", {"file_path": "gold/faithfulness-v1.jsonl"}, True),
    ("Write", {"file_path": "./gold/faithfulness-v1.jsonl"}, True),
    ("Edit", {"file_path": "/home/x/meetlat/gold/naturalness-v2.jsonl"}, True),
    ("Bash", {"command": "echo '{}' >> gold/faithfulness-v1.jsonl"}, True),
    ("Bash", {"command": "sed -i 's/a/b/' gold/x.jsonl"}, True),
    ("Bash", {"command": "rm gold/x.jsonl"}, True),
    ("Bash", {"command": "wc -l gold/*.jsonl"}, False),
    ("Bash", {"command": "cat gold/faithfulness-v1.jsonl | head -3"}, False),
    ("Read", {"file_path": "gold/faithfulness-v1.jsonl"}, False),
    ("Write", {"file_path": "judges/faithfulness/v1/prompt.md"}, False),
    ("Write", {"file_path": "docs/goldilocks.md"}, False),
    ("Bash", {"command": "make check-judges"}, False),
    # Row 13 is the regression this guard caused on its own documentation: a heredoc
    # body that merely quotes the guarded path is not a write to it. Row 14 is the
    # case row 13 must not swallow.
    ("Bash", {"command": "cat > docs/rules.md <<'EOF'\nnever write to gold/\nEOF"}, False),
    ("Bash", {"command": "cat <<'EOF' > gold/faithfulness-v1.jsonl\n{}\nEOF"}, True),
    # Rows 15 and 16: the guarded thing is the labels, not the folder. Documentation
    # about this rule lives in gold/README.md and has to be writable.
    ("Write", {"file_path": "gold/README.md"}, False),
    ("Bash", {"command": "cat > gold/README.md <<'EOF'\nthe format\nEOF"}, False),
]


def run_selftest() -> int:
    # Imported here, not at module scope: the hook path above stays pure stdlib so it
    # cannot fail to load in a checkout where nothing is installed yet.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from meetlat import console

    failures = [
        (tool, tool_input, expected)
        for tool, tool_input, expected in SELFTEST
        if writes_to_gold(tool, tool_input) is not expected
    ]
    for tool, tool_input, expected in failures:
        verb = "should deny" if expected else "should allow"
        console.err(f"{verb}: {tool} {tool_input}")
    passed = len(SELFTEST) - len(failures)
    if failures:
        console.err(f"gold guard: {passed}/{len(SELFTEST)} recorded cases")
        return 1
    console.ok(f"gold guard ok · {passed} recorded cases")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--hook", action="store_true", help="read a PreToolUse payload on stdin")
    group.add_argument("--command", metavar="CMD", help="ask about one shell command")
    group.add_argument("--selftest", action="store_true", help="the recorded behaviour")
    args = parser.parse_args(argv)

    if args.hook:
        return run_hook()
    if args.selftest:
        return run_selftest()
    if writes_to_gold("Bash", {"command": args.command}):
        print(REASON, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
