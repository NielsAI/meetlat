"""Preparing a gold set: sampling and reconciliation, never labelling.

The tools here exist so a person can label efficiently. What is worth asserting is not
that they read files, but the three rules the protocol is most often broken on: the
sample is stratified and its bias is bounded, an annotator never sees another's labels,
and a disagreement cannot be resolved without a written reason.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import label_gold
import pytest
import sample_gold

from meetlat.runner.run import Response


def _response(index: int, task: str, text: str) -> Response:
    return Response.model_validate(
        {
            "id": f"r-1-{index:04d}",
            "prompt_id": f"p-1-{index:04d}",
            "task": task,
            "register": "formal_u",
            "domain": "administrative",
            "instruction": "Herschrijf de tekst hieronder.",
            "response": text,
            "model": "a-model",
            "temperature": 0.0,
        }
    )


CLEAN = "U kunt uw aanvraag online doorgeven, dat scheelt een gang naar de balie."
FLAGGED = "Laten we erin duiken. Als AI-assistent help ik u graag met dit verzoek."


def _pool(per_task: int = 40) -> list[Response]:
    tasks = ("rewrite", "summarise", "draft", "explain")
    out, n = [], 0
    for task in tasks:
        for i in range(per_task):
            n += 1
            out.append(_response(n, task, FLAGGED if i % 3 == 0 else CLEAN))
    return out


def test_the_sample_is_stratified_across_interaction_types() -> None:
    """A set drawn uniformly is mostly whichever type had most prompts."""
    drawn = sample_gold.draw(_pool(), size=160, failure_share=0.25, seed=0)
    counts = Counter(r.task for r in drawn)
    assert len(counts) == 4
    assert len(set(counts.values())) == 1, counts


def test_the_failure_share_is_respected_and_bounded() -> None:
    """The bias toward layer-1-detectable defects is deliberate, so it must be bounded."""
    drawn = sample_gold.draw(_pool(), size=160, failure_share=0.25, seed=0)
    hits = sum(1 for r in drawn if sample_gold.flagged(r))
    assert 0.15 <= hits / len(drawn) <= 0.35, hits / len(drawn)


def test_a_zero_failure_share_draws_only_what_it_can() -> None:
    """Asking for no flagged items must not silently smuggle them in."""
    drawn = sample_gold.draw(_pool(), size=80, failure_share=0.0, seed=0)
    hits = sum(1 for r in drawn if sample_gold.flagged(r))
    assert hits == 0


def test_the_same_seed_draws_the_same_set() -> None:
    """`whichever 175 came out that afternoon` does not describe a calibration set."""
    first = sample_gold.draw(_pool(), size=160, failure_share=0.25, seed=3)
    again = sample_gold.draw(_pool(), size=160, failure_share=0.25, seed=3)
    assert [r.id for r in first] == [r.id for r in again]


def test_an_annotators_file_is_named_for_them_alone(tmp_path: Path) -> None:
    """Blind means each annotator writes their own file and reads no other."""
    worklist = tmp_path / "register_fit-worklist.jsonl"
    worklist.write_text("", encoding="utf-8")
    mine = tmp_path / "register_fit-niels.jsonl"
    mine.write_text(json.dumps({"id": "re-0001", "label": True}) + "\n", encoding="utf-8")

    assert label_gold.already_done(mine) == {"re-0001"}
    # Another annotator's file is not consulted for what is left to do.
    theirs = tmp_path / "register_fit-sam.jsonl"
    theirs.write_text(json.dumps({"id": "re-0002", "label": False}) + "\n", encoding="utf-8")
    assert label_gold.already_done(mine) == {"re-0001"}


def test_a_disagreement_without_a_note_is_left_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GoldItem refuses one, so writing it would fail later and less clearly."""
    worklist = tmp_path / "register_fit-worklist.jsonl"
    worklist.write_text(
        json.dumps(
            {
                "id": "re-0001",
                "interaction_type": "rewrite",
                "prompt": "Herschrijf dit.",
                "response": CLEAN,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    a = tmp_path / "register_fit-niels.jsonl"
    b = tmp_path / "register_fit-sam.jsonl"
    a.write_text(json.dumps({"id": "re-0001", "label": True}) + "\n", encoding="utf-8")
    b.write_text(json.dumps({"id": "re-0001", "label": False}) + "\n", encoding="utf-8")

    monkeypatch.setattr(label_gold, "key", lambda _options: "y")
    monkeypatch.setattr("builtins.input", lambda *_: "   ")

    out = tmp_path / "gold-candidate.jsonl"
    label_gold.reconcile(worklist, a, b, out)
    assert out.read_text(encoding="utf-8") == ""


def test_agreed_items_need_no_note_and_carry_both_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worklist = tmp_path / "register_fit-worklist.jsonl"
    worklist.write_text(
        json.dumps(
            {
                "id": "re-0001",
                "interaction_type": "rewrite",
                "prompt": "Herschrijf dit.",
                "response": CLEAN,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    a = tmp_path / "register_fit-niels.jsonl"
    b = tmp_path / "register_fit-sam.jsonl"
    for path in (a, b):
        path.write_text(json.dumps({"id": "re-0001", "label": True}) + "\n", encoding="utf-8")

    out = tmp_path / "gold-candidate.jsonl"
    label_gold.reconcile(worklist, a, b, out)

    from meetlat.ijk.gold import load

    items = load(out)
    assert len(items) == 1
    assert items[0].labels == {"niels": True, "sam": True}
    assert items[0].reconciled is True
    assert items[0].note == ""


def test_the_sampler_refuses_a_criterion_nothing_else_uses() -> None:
    """A worklist labelled under a name the project does not use is an evening wasted."""
    assert "register_fit" in sample_gold.CRITERIA
    assert "register-fit" not in sample_gold.CRITERIA
