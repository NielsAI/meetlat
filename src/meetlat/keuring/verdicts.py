"""What a judge answered on each item of a gold set during a calibration run."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    verdict: bool


def load(path: Path) -> dict[str, bool]:
    """Read a JSONL verdict log into `{item id: verdict}`."""
    verdicts: dict[str, bool] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = Verdict.model_validate(json.loads(line))
        except Exception as exc:
            raise ValueError(f"{path}:{line_no}: {exc}") from exc
        if entry.id in verdicts:
            raise ValueError(f"{path}:{line_no}: duplicate verdict for item {entry.id!r}")
        verdicts[entry.id] = entry.verdict
    return verdicts
