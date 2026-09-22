"""A judge's card: everything that has to be true before it may report a number.

"A judge whose prompt changed is a new judge and re-enters the gate." That sentence
is the whole design of layer 2, and it is unenforceable as prose, because the way it
gets broken is not a decision: it is a two-word edit to a prompt on an evening when
the calibration run feels like tomorrow's problem.

So the card stores the sha256 of the prompt it was calibrated against, and
`scripts/check_judges.py` refuses a card whose prompt no longer hashes to it.
Editing the prompt does not quietly invalidate the numbers; it fails the build.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: The starting policy from ADR-0004. A card may set them higher for a criterion it
#: wants held to more, never lower: a threshold that moves down to meet a judge is
#: not a threshold.
FLOOR_BALANCED_ACCURACY = 0.85
FLOOR_COHEN_KAPPA = 0.6


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Thresholds(_Strict):
    balanced_accuracy: float = Field(default=FLOOR_BALANCED_ACCURACY, ge=0.0, le=1.0)
    cohen_kappa: float = Field(default=FLOOR_COHEN_KAPPA, ge=-1.0, le=1.0)

    @model_validator(mode="after")
    def _not_below_the_floor(self) -> "Thresholds":
        if self.balanced_accuracy < FLOOR_BALANCED_ACCURACY:
            raise ValueError(f"balanced_accuracy floor is {FLOOR_BALANCED_ACCURACY} (ADR-0004)")
        if self.cohen_kappa < FLOOR_COHEN_KAPPA:
            raise ValueError(f"cohen_kappa floor is {FLOOR_COHEN_KAPPA} (ADR-0004)")
        return self


class Calibration(_Strict):
    """The recorded result of one calibration run.

    The numbers here are checked, not trusted: the gate recomputes them from the
    gold set's reconciled labels and this run's verdicts, and a card that disagrees
    with its own evidence fails.
    """

    date: date
    gold_set: str
    verdicts: str
    annotators: list[str] = Field(min_length=2)
    items: int = Field(gt=0)
    balanced_accuracy: float = Field(ge=0.0, le=1.0)
    cohen_kappa: float = Field(ge=-1.0, le=1.0)


class JudgeCard(_Strict):
    """One judge, one criterion, one version. Lives at `judges/<criterion>/v<n>/card.json`."""

    criterion: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    version: int = Field(ge=1)
    question: str = Field(min_length=1)
    #: Pinned exactly. A floating tag means the judge that was calibrated and the
    #: judge that runs are different judges.
    model: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    thresholds: Thresholds = Thresholds()
    calibration: Calibration
    status: Literal["certified", "withdrawn"]

    @model_validator(mode="after")
    def _model_is_pinned(self) -> "JudgeCard":
        if self.model.endswith(("latest", ":latest")):
            raise ValueError(f"model {self.model!r} is a floating tag; pin a version")
        return self

    def meets_thresholds(self) -> bool:
        return (
            self.calibration.balanced_accuracy >= self.thresholds.balanced_accuracy
            and self.calibration.cohen_kappa >= self.thresholds.cohen_kappa
        )


def prompt_digest(prompt_path: Path) -> str:
    """The sha256 a card must carry to claim it was calibrated against this prompt."""
    return hashlib.sha256(prompt_path.read_bytes()).hexdigest()


def load(card_path: Path) -> JudgeCard:
    return JudgeCard.model_validate(json.loads(card_path.read_text(encoding="utf-8")))
