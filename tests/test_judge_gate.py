"""Build a judge that passes the gate, then break it one way at a time.

The gate in `scripts/check_judges.py` is the only thing standing between an edited
prompt and a published number that no longer describes the judge that produced it.
A gate nobody tests is a gate that rots, so every way a card can end up lying has a
row here, and each row asserts the gate says so.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

import pytest
from check_judges import audit

PROMPT = "Beantwoord met ja of nee: deed het antwoord wat er gevraagd werd?\n"

#: Five items, two interaction types, both classes present, one disagreement that is
#: explained. The judge gets four right and one wrong.
GOLD = [
    ("i1", "rewrite", True, {"a": True, "b": True}, ""),
    ("i2", "rewrite", False, {"a": False, "b": False}, ""),
    ("i3", "summarise", True, {"a": True, "b": True}, ""),
    ("i4", "summarise", False, {"a": False, "b": True}, "b read the length constraint as advisory"),
    ("i5", "rewrite", False, {"a": False, "b": False}, ""),
]
VERDICTS = {"i1": True, "i2": False, "i3": True, "i4": True, "i5": False}

# Sensitivity 2/2, specificity 2/3. The numbers below are what the gate recomputes;
# they are not hand-derived, because a hand-derived figure is the thing being guarded against.
EXPECTED_BALANCED_ACCURACY = 0.8333
EXPECTED_KAPPA = 0.6154


def _build(root: Path) -> Path:
    """A complete, internally consistent judge. Returns its directory."""
    (root / "gold").mkdir(parents=True)
    gold_path = root / "gold" / "instruction_compliance-v1.jsonl"
    gold_path.write_text(
        "".join(
            json.dumps(
                {
                    "id": item_id,
                    "interaction_type": kind,
                    "prompt": "…",
                    "response": "…",
                    "labels": labels,
                    "reconciled": reconciled,
                    "note": note,
                },
                ensure_ascii=False,
            )
            + "\n"
            for item_id, kind, reconciled, labels, note in GOLD
        ),
        encoding="utf-8",
    )

    judge_dir = root / "judges" / "instruction_compliance" / "v1"
    judge_dir.mkdir(parents=True)
    (judge_dir / "prompt.md").write_text(PROMPT, encoding="utf-8")
    (judge_dir / "verdicts.jsonl").write_text(
        "".join(json.dumps({"id": k, "verdict": v}) + "\n" for k, v in VERDICTS.items()),
        encoding="utf-8",
    )
    _write_card(
        judge_dir,
        balanced_accuracy=EXPECTED_BALANCED_ACCURACY,
        cohen_kappa=EXPECTED_KAPPA,
    )
    return judge_dir


def _write_card(judge_dir: Path, **overrides: object) -> None:
    calibration = {
        "date": "2026-10-05",
        "gold_set": "gold/instruction_compliance-v1.jsonl",
        "verdicts": "verdicts.jsonl",
        "annotators": ["a", "b"],
        "items": 5,
        "balanced_accuracy": EXPECTED_BALANCED_ACCURACY,
        "cohen_kappa": EXPECTED_KAPPA,
    }
    card: dict[str, object] = {
        "criterion": "instruction_compliance",
        "version": 1,
        "question": "Did the response do what the prompt asked?",
        "model": "qwen3-27b-2026-04-01",
        "temperature": 0.0,
        "prompt_sha256": hashlib.sha256((judge_dir / "prompt.md").read_bytes()).hexdigest(),
        "thresholds": {"balanced_accuracy": 0.85, "cohen_kappa": 0.6},
        "calibration": calibration,
        "status": "certified",
    }
    for key, value in overrides.items():
        if key in calibration:
            calibration[key] = value
        else:
            card[key] = value
    (judge_dir / "card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")


def test_an_empty_repository_passes(tmp_path: Path) -> None:
    """Nothing calibrated yet is an honest state, and the one this repo starts in."""
    (tmp_path / "judges").mkdir()
    assert audit(tmp_path) == []


def test_a_consistent_judge_passes(tmp_path: Path) -> None:
    judge_dir = _build(tmp_path)
    # Certified at 0.833 balanced accuracy, below the 0.85 threshold, so the fixture
    # is honest about it: it is recorded as withdrawn.
    _write_card(judge_dir, status="withdrawn")
    assert audit(tmp_path) == []


def _edit_prompt(judge_dir: Path) -> None:
    (judge_dir / "prompt.md").write_text(PROMPT + "Wees streng.\n", encoding="utf-8")


def _claim_a_better_number(judge_dir: Path) -> None:
    _write_card(judge_dir, balanced_accuracy=0.95)


def _certify_below_threshold(judge_dir: Path) -> None:
    _write_card(judge_dir, status="certified")


def _float_the_model(judge_dir: Path) -> None:
    _write_card(judge_dir, model="qwen3:latest", status="withdrawn")


def _lower_the_threshold(judge_dir: Path) -> None:
    _write_card(judge_dir, thresholds={"balanced_accuracy": 0.5, "cohen_kappa": 0.1})


def _drop_an_annotator(judge_dir: Path) -> None:
    _write_card(judge_dir, annotators=["a"], status="withdrawn")


def _unexplain_a_disagreement(judge_dir: Path) -> None:
    path = judge_dir.parent.parent.parent / "gold" / "instruction_compliance-v1.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    item = json.loads(lines[3])
    item["note"] = ""
    lines[3] = json.dumps(item)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _collapse_to_one_interaction_type(judge_dir: Path) -> None:
    path = judge_dir.parent.parent.parent / "gold" / "instruction_compliance-v1.jsonl"
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        item["interaction_type"] = "rewrite"
        lines.append(json.dumps(item, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _write_card(judge_dir, status="withdrawn")


def _lose_the_verdicts(judge_dir: Path) -> None:
    (judge_dir / "verdicts.jsonl").unlink()


@pytest.mark.parametrize(
    "break_it,expected",
    [
        (_edit_prompt, "this is a new judge"),
        (_claim_a_better_number, "the labels give"),
        (_certify_below_threshold, "certified below threshold"),
        (_float_the_model, "floating tag"),
        (_lower_the_threshold, "floor is"),
        (_drop_an_annotator, "at least 2 items"),
        (_unexplain_a_disagreement, "no reconciliation note"),
        (_collapse_to_one_interaction_type, "one interaction type"),
        (_lose_the_verdicts, "unreadable"),
    ],
    ids=lambda f: f.__name__.lstrip("_") if callable(f) else f,
)
def test_the_gate_catches(tmp_path: Path, break_it: Callable[[Path], None], expected: str) -> None:
    judge_dir = _build(tmp_path)
    break_it(judge_dir)
    findings = audit(tmp_path)
    assert findings, f"{break_it.__name__} went undetected"
    assert any(expected in f.what for f in findings), [f.what for f in findings]
