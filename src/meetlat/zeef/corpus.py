"""The clean Dutch corpus: what a paragraph must carry to count as evidence (ADR-0007).

This is the false-positive gate from ADR-0002, and it is the only thing standing
between a plausible-looking check and one that fires on correct Dutch. A corpus that
cannot say where its text came from, or that covers one register while looking large,
reads as evidence without being any.

The axes are deliberately the same ones the prompt taxonomy uses in ADR-0005, so
coverage is described in one vocabulary across the project rather than two.
"""

from __future__ import annotations

import json
import warnings
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: The formality a Dutch text is written in. `register_consistency` was narrowed
#: around the informal side, so that is where its false positives would be, and a
#: corpus without it does not test the check where it is weakest.
Register = Literal["informal_je", "formal_u", "business", "plain_language"]

Domain = Literal["administrative", "commercial", "technical", "care", "education", "everyday"]

#: How the text got here. `collected` is the only scalable one; `authored` means a
#: named person wrote it for this repository. There is deliberately no third option:
#: model-generated text makes the gate circular (ADR-0007).
Origin = Literal["collected", "authored"]

#: Licences whose text this project may redistribute under CC BY 4.0. CC BY-SA is
#: absent on purpose: share-alike would force this repository's data licence to
#: change, which rules out Dutch Wikipedia and most of what is easy to scrape.
REDISTRIBUTABLE: frozenset[str] = frozenset(
    {"CC0-1.0", "CC-BY-4.0", "CC-BY-3.0", "LicenseRef-PublicDomain"}
)


# `register` is this project's vocabulary (CONTEXT.md) and the key the corpus file
# uses, so the field keeps the name. It shadows `ABCMeta.register`, which pydantic
# warns about and which this model never calls; the warning is silenced here rather
# than globally so a future shadow of something that does matter still surfaces.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message='Field name "register"', category=UserWarning)

    class CorpusEntry(BaseModel):
        """One paragraph of Dutch written by a person, with everything needed to trust it."""

        model_config = ConfigDict(extra="forbid", frozen=True)

        id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9-]*$")
        text: str = Field(min_length=1)
        register: Register
        domain: Domain
        origin: Origin
        #: Human-readable name of where this came from: a site, a publication, a person.
        source: str = Field(min_length=1)
        licence: str = Field(min_length=1)
        #: Resolvable by a reader who wants to check the quote. Required for collected
        #: text; an authored paragraph has nowhere to point.
        url: str = ""
        retrieved: date | None = None

        @model_validator(mode="after")
        def _is_redistributable_and_traceable(self) -> "CorpusEntry":
            if self.licence not in REDISTRIBUTABLE:
                raise ValueError(
                    f"{self.id}: licence {self.licence!r} is not one this project can "
                    f"redistribute under CC BY 4.0; allowed: {sorted(REDISTRIBUTABLE)}"
                )
            if self.origin == "collected" and not (self.url and self.retrieved):
                raise ValueError(f"{self.id}: collected text needs a url and a retrieved date")
            return self


def load(path: Path) -> list[CorpusEntry]:
    """Read the corpus. Raises with the line number on a malformed entry."""
    entries: list[CorpusEntry] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        try:
            entries.append(CorpusEntry.model_validate(json.loads(line)))
        except Exception as exc:
            raise ValueError(f"{path.name}:{line_no}: {exc}") from exc
    if len({entry.id for entry in entries}) != len(entries):
        raise ValueError(f"{path.name}: duplicate entry ids")
    return entries


def coverage(entries: list[CorpusEntry]) -> dict[Register, int]:
    """Paragraphs per register, including the registers with none.

    Every register appears whether or not it has entries, because the point is to
    show the empty ones. A total of 200 spread over one register is not breadth.
    """
    counted = Counter(entry.register for entry in entries)
    return {register: counted.get(register, 0) for register in get_args(Register)}
