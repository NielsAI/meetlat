"""The three axes evaluation prompts are generated from (ADR-0005).

The prompts are disposable and this is not. A fixed public prompt set ages out of
usefulness the moment it is popular enough to matter, because anything published gets
scraped into someone's next fine-tune. So what is maintained here is a small description
of *what to ask for*, and the specific wording is regenerated per release from a seed.

Three axes, and a cell is one combination of them:

    task      what the prompt asks for      7 values
    register  the formality to write in     4 values, from `meetlat.zeef.corpus`
    domain    the subject matter            6 values, from `meetlat.zeef.corpus`

`register` and `domain` are imported rather than restated. They are defined in
`zeef.corpus` because `make review` shows those definitions while a person tags a
paragraph and `make check-zeef` fails on a tag defined nowhere (CONTEXT.md). One
vocabulary across the project was the point of choosing the same axes in the first
place, and two copies of it would end that within a release.

**A cell can be empty, and an empty cell is the output.** ADR-0005 wants a gap to be a
visible hole in a grid rather than an absence nobody noticed, which is the same
reasoning as `zeef.PLANNED`. `UNREACHABLE` records which cells cannot be filled yet and
why, so the generator reports them rather than quietly producing 6 tasks and calling it
7.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

from meetlat.zeef.corpus import DOMAIN_MEANS, REGISTER_MEANS, Domain, Meaning, Register

__all__ = [
    "Cell",
    "DOMAIN_MEANS",
    "Domain",
    "NEEDS_CONTEXT",
    "REGISTER_MEANS",
    "Register",
    "TASK_MEANS",
    "Task",
    "UNREACHABLE",
    "cells",
    "reachable",
]

#: What the prompt asks for. These are CONTEXT.md's **interaction types**, and the name
#: is load-bearing: ADR-0003 reports every score per interaction type, because a pass
#: rate over mixed traffic hides that rewriting works and summarising does not. The
#: taxonomy axis and the reporting axis have to be the same list or the report cannot be
#: cut by it.
Task = Literal[
    "rewrite",
    "summarise",
    "answer_from_context",
    "draft",
    "translate",
    "explain",
    "extract",
]

#: Every `Task`, defined, with one instruction that is unmistakably it. Same contract as
#: `REGISTER_MEANS`: `make check-taxonomy` fails if a value has no definition, because a
#: task meaning one thing in the generator and another in the report is two tasks.
TASK_MEANS: dict[str, Meaning] = {
    "rewrite": Meaning(
        "restate a given text differently while keeping what it says",
        "Herschrijf deze brief zodat een lezer zonder voorkennis hem begrijpt.",
    ),
    "summarise": Meaning(
        "shorten a given text to its essentials",
        "Vat dit bericht samen in drie zinnen.",
    ),
    "answer_from_context": Meaning(
        "answer a question using only a supplied document",
        "Beantwoord op basis van de tekst hieronder: binnen welke termijn moet het formulier terug?",
    ),
    "draft": Meaning(
        "produce a new text from a description, with no source document",
        "Schrijf een korte e-mail waarin je een afspraak verzet naar volgende week.",
    ),
    "translate": Meaning(
        "render a text written in another language into Dutch",
        "Vertaal de volgende Engelse passage naar natuurlijk Nederlands.",
    ),
    "explain": Meaning(
        "make a concept understandable, with no source document",
        "Leg uit wat een persoonsgebonden budget is en voor wie het bedoeld is.",
    ),
    "extract": Meaning(
        "pull specific fields out of a given text",
        "Haal uit de tekst hieronder de datum, het bedrag en de contactpersoon.",
    ),
}

#: Tasks that hand the model a document. The runner has to supply one for these, and a
#: prompt without it is not a prompt; `draft`, `explain` and `translate` are the ones
#: that do not take a Dutch source document. `translate` is absent for the opposite
#: reason to the other two: it needs a source in *another* language, which is why it is
#: in `UNREACHABLE` rather than here.
NEEDS_CONTEXT: frozenset[str] = frozenset(
    {"rewrite", "summarise", "answer_from_context", "extract", "translate"}
)


@dataclass(frozen=True)
class Cell:
    """One combination of the three axes. The unit coverage is counted in."""

    task: Task
    register: Register
    domain: Domain

    def __str__(self) -> str:
        return f"{self.task}/{self.register}/{self.domain}"


#: Cells that cannot be generated yet, and the reason, printed by the generator instead
#: of being silently skipped. The key is a `Task`; a reason here rules out that task in
#: every register and domain.
#:
#: Empty, and worth keeping rather than deleting. `translate` lived here until an English
#: source under a licence permitting adaptation was found, and the mechanism is what made
#: that gap visible every run instead of looking like a task nobody had got to.
UNREACHABLE: dict[str, str] = {}


def cells(*, include_unreachable: bool = False) -> list[Cell]:
    """Every cell in the grid, in a stable order.

    Stable because a seed has to reproduce a release exactly, and a set iteration order
    that drifts between Python versions would quietly make the same seed a different
    prompt set.
    """
    return [
        Cell(task, register, domain)
        for task in get_args(Task)
        if include_unreachable or task not in UNREACHABLE
        for register in get_args(Register)
        for domain in get_args(Domain)
    ]


def reachable(cell: Cell) -> str:
    """Empty if the cell can be generated, otherwise why it cannot."""
    return UNREACHABLE.get(cell.task, "")
