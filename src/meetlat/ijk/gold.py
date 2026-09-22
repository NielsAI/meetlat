"""A gold set on disk: one JSONL file, one hand-labelled item per line.

The labelling protocol in ADR-0004 is a set of rules about people, and people skip
steps on a tired evening. Each rule that can be a field is one:

  * two independent labels, not one, so `labels` needs at least two annotators;
  * a reconciled label, because a disagreement that was never resolved is not a
    ground truth;
  * a written reason wherever the two annotators disagreed, because that reasoning
    is what tells you a criterion is badly defined rather than a rater careless;
  * an interaction type on every item, because a pass rate over mixed traffic hides
    that rewriting works and summarising does not.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GoldItem(BaseModel):
    """One labelled generation. Frozen: these are human minutes and are not edited in code."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    interaction_type: str = Field(min_length=1)
    prompt: str
    response: str
    #: Annotator name to their independent verdict. At least two, labelled blind.
    labels: dict[str, bool] = Field(min_length=2)
    #: The label after reconciliation. This is the ground truth a judge is scored on.
    reconciled: bool
    #: Required where the annotators disagreed. That reasoning is what the protocol
    #: asks for, and the input to deciding a criterion is badly defined.
    note: str = ""

    @model_validator(mode="after")
    def _disagreement_is_explained(self) -> "GoldItem":
        if len(set(self.labels.values())) > 1 and not self.note.strip():
            raise ValueError(
                f"item {self.id!r}: annotators disagreed and no reconciliation note was recorded"
            )
        return self


def load(path: Path) -> list[GoldItem]:
    """Read a JSONL gold set. Raises with the line number on a malformed item."""
    items: list[GoldItem] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            items.append(GoldItem.model_validate(json.loads(line)))
        except Exception as exc:
            raise ValueError(f"{path}:{line_no}: {exc}") from exc
    if len({item.id for item in items}) != len(items):
        raise ValueError(f"{path}: duplicate item ids")
    return items
