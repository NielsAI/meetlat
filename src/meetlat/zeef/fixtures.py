"""The schema of a check's fixture file, and the loader the contract gate uses.

A fixture is the evidence that a check does what it claims, so it is read through a
model rather than as a dict: a fixture with a misspelled key should fail saying
which key, at the file, not silently assert nothing and let the check into the
registry unexamined.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from meetlat.types import CheckKind


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FiresCase(_Strict):
    """Text the check must fire on, with the literal text of every span it must return."""

    text: str = Field(min_length=1)
    spans: list[str] = Field(min_length=1)


class MetricsCase(_Strict):
    """Text a distribution check is run over, with the metrics it must report.

    `expect` is a subset: naming every metric in every case would turn a new metric
    into an edit of every fixture, and the gate would be maintained rather than read.
    """

    text: str
    expect: dict[str, float]


class Fixture(_Strict):
    check: str
    kind: CheckKind
    fires: list[FiresCase] = []
    silent: list[str] = []
    metrics: list[MetricsCase] = []

    @model_validator(mode="after")
    def _shape_matches_kind(self) -> "Fixture":
        if self.kind == "verdict":
            if not self.fires or not self.silent:
                raise ValueError("a verdict check needs at least one 'fires' and one 'silent' case")
            if self.metrics:
                raise ValueError("a verdict check has no metrics to assert")
        else:
            if not self.metrics:
                raise ValueError("a distribution check needs at least one 'metrics' case")
            if self.fires or self.silent:
                raise ValueError("a distribution check reports numbers, not verdicts")
        return self


def load(path: Path) -> Fixture:
    return Fixture.model_validate(json.loads(path.read_text(encoding="utf-8")))
