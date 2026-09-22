#!/usr/bin/env python3
"""The taxonomy says what it generates, and generates what it says (ADR-0005, ADR-0006).

Three things a prompt set can be wrong about, all of which look like working code:

1. **A tag with no definition.** Same failure `make check-zeef` catches for registers and
   domains, and the same reason: a task meaning one thing in the generator and another in
   the report is two tasks, and every score is reported per interaction type (ADR-0003).
2. **A cell that is empty without saying so.** ADR-0005 wants a gap to be a visible hole
   in a grid rather than an absence nobody noticed. An unbuildable cell must be either in
   `UNREACHABLE` with a reason or reported as thin at generation time, never just absent.
3. **A context document the project may not redistribute.** The pool gets published with
   the prompt set, so it is under the same licence rule as the corpus, and the two must
   stay disjoint or layer 1 flatters a model that copies its input.

Run by `make check-taxonomy`, by CI, and by `make check`.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meetlat import console  # noqa: E402
from meetlat.taxonomy import (  # noqa: E402
    DOMAIN_MEANS,
    REGISTER_MEANS,
    TASK_MEANS,
    UNREACHABLE,
    Domain,
    Register,
    Task,
    cells,
)
from meetlat.taxonomy.generate import (  # noqa: E402
    _TEMPLATES,
    ContextDocument,
    generate,
    load_contexts,
)
from meetlat.zeef import corpus  # noqa: E402

#: The seed the gate generates with. Fixed, because the gate is checking the machinery
#: rather than sampling it: a gate that used a different seed each run would fail on
#: Tuesday for a reason nobody could reproduce on Wednesday.
GATE_SEED = 0


@dataclass(frozen=True)
class Finding:
    where: str
    what: str


def contexts_path(repo_root: Path = REPO_ROOT) -> Path:
    return repo_root / "prompts" / "contexts.jsonl"


def _audit_definitions(out: list[Finding]) -> None:
    for name, values, defined in (
        ("task", get_args(Task), TASK_MEANS),
        ("register", get_args(Register), REGISTER_MEANS),
        ("domain", get_args(Domain), DOMAIN_MEANS),
    ):
        for value in values:
            if value not in defined:
                out.append(Finding(f"taxonomy/{name}", f"{value!r} has no definition"))
        for value in defined:
            if value not in values:
                out.append(Finding(f"taxonomy/{name}", f"{value!r} is defined but not a value"))


def _audit_templates(out: list[Finding]) -> None:
    """Every reachable task needs templates, and an unreachable one needs a reason."""
    for task in get_args(Task):
        if task in UNREACHABLE:
            if not UNREACHABLE[task].strip():
                out.append(Finding(f"taxonomy/{task}", "is unreachable with no reason given"))
            continue
        if not _TEMPLATES.get(task):
            out.append(
                Finding(
                    f"taxonomy/{task}",
                    "is reachable but has no templates; either write them or record why "
                    "the task cannot be generated in UNREACHABLE",
                )
            )


def _audit_contexts(documents: list[ContextDocument], out: list[Finding]) -> None:
    """The pool is redistributable, and disjoint from the false-positive gate."""
    in_corpus = {entry.text for entry in corpus.load(_corpus_path())}
    for document in documents:
        if document.licence not in corpus.REDISTRIBUTABLE:
            out.append(
                Finding(
                    f"prompts/contexts.jsonl#{document.id}",
                    f"licence {document.licence!r} is not one this project can redistribute",
                )
            )
        if document.licence in corpus.ATTRIBUTION_REQUIRED and not document.author:
            out.append(
                Finding(
                    f"prompts/contexts.jsonl#{document.id}",
                    f"{document.licence} requires naming who wrote the text",
                )
            )
        for paragraph in document.text.split("\n\n"):
            if paragraph in in_corpus:
                out.append(
                    Finding(
                        f"prompts/contexts.jsonl#{document.id}",
                        "is also in tests/corpora/clean_nl.jsonl; the false-positive gate "
                        "and the evaluation input must stay disjoint, or a model that "
                        "copies its input scores perfectly on layer 1",
                    )
                )
                break


def _corpus_path() -> Path:
    return REPO_ROOT / "tests" / "corpora" / "clean_nl.jsonl"


def audit(repo_root: Path = REPO_ROOT) -> tuple[list[Finding], list[ContextDocument]]:
    out: list[Finding] = []
    _audit_definitions(out)
    _audit_templates(out)

    path = contexts_path(repo_root)
    documents = load_contexts(path) if path.exists() else []
    _audit_contexts(documents, out)
    return out, documents


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root to audit")
    args = parser.parse_args(argv)

    findings, documents = audit(args.root)
    if findings:
        console.heading("taxonomy violations (ADR-0005)", stderr=True)
        for finding in findings:
            console.err(f"{console.CE.bold}{finding.where}{console.CE.reset}: {finding.what}")
        return 1

    prompts, empty = generate(seed=GATE_SEED, per_cell=1, contexts=documents)
    grid = cells()
    console.ok(
        f"taxonomy ok · {len(get_args(Task))} tasks · {len(grid)} cells · "
        f"{len(documents)} context documents"
    )
    console.stat(
        "   ".join(
            (
                console.field("cells filled", len(grid) - len(empty)),
                console.field("of", len(grid)),
                console.field("prompts at 1 per cell", len(prompts)),
            )
        )
    )

    # An unreachable task is named every run. It is the one kind of gap that will not
    # close by itself, and ADR-0005 wants it visible rather than inferred from a total.
    for task, why in UNREACHABLE.items():
        console.wrap(f"{task}: {why}")

    if empty:
        missing = sorted({why for why in empty.values()})
        for why in missing:
            console.wrap(f"{len([c for c, w in empty.items() if w == why])} cells empty: {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
