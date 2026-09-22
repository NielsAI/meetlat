"""The commit-message guard's recorded behaviour.

The rows that accept matter as much as the rows that reject. A guard that blocks a
human co-author trailer, or a commit whose stripped comment lines merely quote the
banned text, is a guard that gets bypassed until nobody runs it at all.
"""

from __future__ import annotations

import pytest
from check_commit_msg import SELFTEST, stored_message, violations


@pytest.mark.parametrize(
    "message,rejected", SELFTEST, ids=[m.splitlines()[0][:40] for m, _ in SELFTEST]
)
def test_recorded_cases(message: str, rejected: bool) -> None:
    assert bool(violations(stored_message(message))) is rejected


def test_a_human_co_author_is_never_matched() -> None:
    message = "feat: x\n\nCo-Authored-By: Iemand Anders <iemand@example.nl>\n"
    assert violations(stored_message(message)) == []


def test_the_reported_line_number_is_the_stored_one() -> None:
    """Comments are stripped before matching, so a line number has to survive that."""
    message = (
        "# a comment git will remove\nfeat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n"
    )
    found = violations(stored_message(message))
    assert len(found) == 1
    line_no, _, line = found[0]
    assert line_no == 3
    assert line.startswith("Co-Authored-By:")
