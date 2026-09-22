#!/usr/bin/env python3
"""Keep tool attribution out of the history (ADR-0006).

A commit message records what changed and why. Who or what typed it is not part of
that record. An assistant's default instructions will add a `Co-Authored-By:` trailer
or a "Generated with" footer unless something stops it, and by the time a few commits
carry one the history cannot be cleaned without a rewrite.

**A human co-author trailer is legitimate and is deliberately not matched.** The
patterns below name the assistant and its address specifically, so pair-programming
attribution still works.

Two callers, per ADR-0006:

    --hook <file>   the git commit-msg hook, via .githooks/commit-msg
    --selftest      the recorded behaviour, also run by tests/test_commit_msg.py

Stdlib only on the hook path, so it works in a fresh clone before `make install`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BANNED: list[tuple[re.Pattern[str], str]] = [
    (
        # Scoped to the assistant's names and address: a human trailer must still pass.
        # `[ \t]*` rather than `\s*`: under MULTILINE, `\s` eats the preceding newline,
        # which puts the reported line number one early and quotes a blank line.
        re.compile(
            r"^[ \t]*co-authored-by:.*(claude|anthropic|noreply@anthropic\.com)", re.I | re.M
        ),
        "an assistant co-author trailer",
    ),
    (re.compile(r"generated with.*(claude|anthropic)", re.I), "a 'Generated with' footer"),
    (re.compile("\U0001f916"), "the robot sign-off that footer ships with"),
]


def _comment_char() -> str:
    """Whatever this checkout uses to start a comment line; `auto` means the default."""
    try:
        out = subprocess.run(
            ["git", "config", "--get", "core.commentChar"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
    except Exception:
        return "#"
    return out if out and out != "auto" else "#"


def stored_message(raw: str, comment_char: str = "#") -> str:
    """The message as git will actually store it.

    Two things come off first, or the hook blocks a commit over text that was never
    going to land: comment lines, which git strips after this hook runs, and
    everything below a `--verbose` scissors line, which is the diff.
    """
    scissors = f"{comment_char} ------------------------ >8 ------------------------"
    lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith(scissors):
            break
        if line.startswith(comment_char):
            continue
        lines.append(line)
    return "\n".join(lines)


def violations(message: str) -> list[tuple[int, str, str]]:
    """Every banned construct, as (line number, what it is, the line)."""
    found: list[tuple[int, str, str]] = []
    for pattern, description in BANNED:
        for match in pattern.finditer(message):
            line_no = message.count("\n", 0, match.start()) + 1
            line = message.splitlines()[line_no - 1]
            found.append((line_no, description, line.strip()))
    return sorted(set(found))


#: (message, should be rejected). The passing rows matter as much as the failing ones:
#: a hook that blocks a human co-author, or a commit that merely discusses the rule in
#: a stripped comment, is a hook that gets bypassed until nobody runs it.
SELFTEST: list[tuple[str, bool]] = [
    ("feat: add the register check\n", False),
    ("fix: narrow the trigger\n\nCo-Authored-By: A Colleague <them@example.com>\n", False),
    ("docs: a message generated with care by hand\n", False),
    ("# Co-Authored-By: Claude <noreply@anthropic.com>\nfeat: real subject\n", False),
    (
        "feat: real subject\n"
        "# ------------------------ >8 ------------------------\n"
        "diff --git a/x b/x\n+Generated with Claude Code\n",
        False,
    ),
    ("feat: x\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n", True),
    ("feat: x\n\nco-authored-by: claude <noreply@anthropic.com>\n", True),
    ("feat: x\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n", True),
    ("feat: x\n\nGenerated with Anthropic's assistant\n", True),
    ("feat: x\n\n🤖\n", True),
]


def run_selftest() -> int:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from meetlat import console

    failures = [
        (message, expected)
        for message, expected in SELFTEST
        if bool(violations(stored_message(message))) is not expected
    ]
    for message, expected in failures:
        verb = "should reject" if expected else "should accept"
        console.err(f"{verb}: {message.splitlines()[0]!r}")
    passed = len(SELFTEST) - len(failures)
    if failures:
        console.err(f"commit-msg guard: {passed}/{len(SELFTEST)} recorded cases")
        return 1
    console.ok(f"commit-msg guard ok · {passed} recorded cases")
    return 0


def run_hook(path: Path) -> int:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return 0  # fail open: an unreadable message file is git's problem, not ours
    found = violations(stored_message(raw, _comment_char()))
    if not found:
        return 0

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from meetlat import console

    console.heading("commit blocked · attribution trailer", stderr=True)
    for line_no, description, text in found:
        console.err(f"line {line_no}: {description}")
        console.line(text, indent=6, stderr=True)
    console.say(stderr=True)
    console.note("A commit records what changed and why, not who typed it.", stderr=True)
    console.note("Your message is kept, so nothing is lost. Reopen it with:", stderr=True)
    console.note("  git commit -e -F .git/COMMIT_EDITMSG", stderr=True)
    console.note("A human co-author trailer is fine, and is not matched here.", stderr=True)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--hook", type=Path, metavar="FILE", help="the commit message file")
    group.add_argument("--selftest", action="store_true", help="the recorded behaviour")
    args = parser.parse_args(argv)
    return run_hook(args.hook) if args.hook else run_selftest()


if __name__ == "__main__":
    raise SystemExit(main())
