"""The gold set guard's recorded behaviour.

It is the only fail-closed rule in the repository, so it is the one where being
wrong in either direction costs something: too loose and the instrument gets
overwritten, too tight and it is routed around within a day.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from check_gold_write import SELFTEST, writes_to_gold

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_gold_write.py"


@pytest.mark.parametrize(
    "tool,tool_input,expected", SELFTEST, ids=[f"{t}-{i}" for i, (t, _, _) in enumerate(SELFTEST)]
)
def test_recorded_cases(tool: str, tool_input: dict[str, object], expected: bool) -> None:
    assert writes_to_gold(tool, tool_input) is expected


def test_the_hook_denies_a_write() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--hook"],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": "gold/x.jsonl"}}),
        capture_output=True,
        text=True,
        check=True,
    )
    decision = json.loads(result.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "ADR-0004" in decision["permissionDecisionReason"]


def test_the_hook_fails_open_on_garbage() -> None:
    """A guard that denies everything the moment its input is malformed gets deleted."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--hook"],
        input="not json at all",
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == ""
