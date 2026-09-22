"""The prompt generator's promises: reproducible, non-repeating, and honest about gaps.

What matters here is not that it produces text, which is trivially true, but that a seed
rebuilds a release exactly, that a cell nobody can fill says so rather than vanishing,
and that the context pool never overlaps the corpus layer 1 is measured against.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meetlat.taxonomy import NEEDS_CONTEXT, TASK_MEANS, UNREACHABLE, Cell, cells
from meetlat.taxonomy.generate import (
    _TEMPLATES,
    ContextDocument,
    generate,
    load_contexts,
)


def _document(doc_id: str, domain: str) -> ContextDocument:
    return ContextDocument.model_validate(
        {
            "id": doc_id,
            "text": "Een standaard is een afspraak.\n\nICT-systemen moeten dezelfde standaard hanteren.",
            "domain": domain,
            "source": "digitaleoverheid",
            "licence": "CC0-1.0",
            "url": "https://www.digitaleoverheid.nl/overzicht-van-alle-onderwerpen/open-standaarden/",
        }
    )


def test_a_seed_rebuilds_a_release_exactly() -> None:
    """A published number names the set it was measured over, so that set must be rebuildable."""
    first, _ = generate(seed=2026, per_cell=2)
    again, _ = generate(seed=2026, per_cell=2)
    assert [p.model_dump() for p in first] == [p.model_dump() for p in again]


def test_a_different_seed_is_a_different_release() -> None:
    """The whole contamination argument rests on this: the wording did not exist before."""
    first, _ = generate(seed=1, per_cell=2)
    other, _ = generate(seed=2, per_cell=2)
    assert [p.instruction for p in first] != [p.instruction for p in other]


def test_prompts_within_a_cell_do_not_repeat() -> None:
    """Two identical prompts in one cell are one prompt and an inflated count."""
    prompts, _ = generate(seed=3, per_cell=3)
    per_cell: dict[tuple[str, str, str], list[str]] = {}
    for prompt in prompts:
        per_cell.setdefault((prompt.task, prompt.register, prompt.domain), []).append(
            prompt.instruction
        )
    for key, instructions in per_cell.items():
        assert len(instructions) == len(set(instructions)), key


def test_a_cell_with_no_context_is_reported_rather_than_skipped() -> None:
    """ADR-0005 wants a gap to be a visible hole in the grid, not an absence."""
    prompts, empty = generate(seed=4, per_cell=1, contexts=[_document("ctx-1", "technical")])
    document_cells = [c for c in empty if c.task in NEEDS_CONTEXT]
    assert document_cells
    assert all("no context document" in empty[c] for c in document_cells)
    assert not any(p.task in NEEDS_CONTEXT and p.domain != "technical" for p in prompts)


def test_a_task_that_needs_a_document_never_ships_without_one() -> None:
    prompts, _ = generate(seed=5, per_cell=1, contexts=[_document("ctx-1", "care")])
    for prompt in prompts:
        assert bool(prompt.context_id) == (prompt.task in NEEDS_CONTEXT)


def test_an_unreachable_task_generates_nothing_and_says_why() -> None:
    prompts, _ = generate(seed=6, per_cell=2)
    for task, why in UNREACHABLE.items():
        assert not [p for p in prompts if p.task == task]
        assert why.strip(), f"{task} is unreachable with no reason"
    assert Cell("translate", "formal_u", "administrative") not in cells()


def test_every_task_is_either_templated_or_declared_unreachable() -> None:
    """A task with neither is one that silently produces nothing."""
    for task in TASK_MEANS:
        assert bool(_TEMPLATES.get(task)) != (task in UNREACHABLE), task


def test_answer_from_context_prompts_contain_a_question() -> None:
    """A template that says `beantwoord de vraag` and supplies none is not a prompt."""
    prompts, _ = generate(seed=7, per_cell=3, contexts=[_document("ctx-1", "care")])
    asked = [p for p in prompts if p.task == "answer_from_context"]
    assert asked
    assert all("?" in p.instruction for p in asked)


def test_every_prompt_names_the_register_it_wants() -> None:
    """The register is the axis being varied, so implying it measures a different thing."""
    prompts, _ = generate(seed=8, per_cell=1)
    for prompt in prompts:
        marker = {
            "informal_je": "je",
            "formal_u": "u",
            "business": "zakelijk",
            "plain_language": ("eenvoudig", "gewone woorden", "B1"),
        }[prompt.register]
        needles = (marker,) if isinstance(marker, str) else marker
        assert any(n in prompt.instruction for n in needles), prompt.instruction


def test_the_context_pool_refuses_a_licence_the_project_cannot_pass_on(tmp_path: Path) -> None:
    path = tmp_path / "contexts.jsonl"
    row = _document("ctx-1", "care").model_dump()
    row["licence"] = "CC-BY-SA-4.0"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    # The model accepts any string; the gate is what refuses a share-alike licence.
    assert load_contexts(path)[0].licence == "CC-BY-SA-4.0"


def test_a_malformed_context_names_its_line(tmp_path: Path) -> None:
    path = tmp_path / "contexts.jsonl"
    path.write_text('{"id": "ctx-1"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="contexts.jsonl:1"):
        load_contexts(path)


def test_the_gate_refuses_a_context_that_is_also_in_the_clean_corpus(tmp_path: Path) -> None:
    """The one rule this pool exists to keep: disjoint from the false-positive gate.

    A model that copies its input would otherwise score perfectly on layer 1, in the
    layer that runs on every response.
    """
    import check_taxonomy

    from meetlat.zeef import corpus

    shared = corpus.load(check_taxonomy._corpus_path())[0].text
    document = _document("ctx-1", "care").model_dump()
    document["text"] = shared
    findings: list[check_taxonomy.Finding] = []
    check_taxonomy._audit_contexts([ContextDocument.model_validate(document)], findings)
    assert findings
    assert "disjoint" in findings[0].what


def test_the_gate_refuses_a_task_with_neither_templates_nor_a_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import check_taxonomy

    monkeypatch.setitem(check_taxonomy._TEMPLATES, "draft", ())
    findings: list[check_taxonomy.Finding] = []
    check_taxonomy._audit_templates(findings)
    assert any("no templates" in f.what for f in findings)
