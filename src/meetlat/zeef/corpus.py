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
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: The formality a Dutch text is written in. `register_consistency` was narrowed
#: around the informal side, so that is where its false positives would be, and a
#: corpus without it does not test the check where it is weakest.
Register = Literal["informal_je", "formal_u", "business", "plain_language"]

Domain = Literal["administrative", "commercial", "technical", "care", "education", "everyday"]


@dataclass(frozen=True)
class Meaning:
    """What a tag means, and one paragraph that is unmistakably it.

    The example does the work the definition cannot. `business` and `plain_language`
    are both unaddressed prose and the boundary between them is not obvious from two
    words, but nobody mistakes a board's decision for a train's departure time.

    The two addressed registers are about formality, not about the pronoun: "Hierbij
    bevestigen wij de afspraak" is `formal_u` with no `u` in it. The pronoun is the usual
    sign, not the definition.

    Where the unaddressed two are hard to separate, the question is who the text assumes
    as its reader rather than how it is phrased. A passive institutional voice reads as
    business and often is not: "het nieuwe paspoort wordt vandaag in gebruik genomen"
    is written for anybody who owns a passport, in words anybody owns.
    """

    means: str
    like: str


#: Every `Register` value, defined. `make check-zeef` fails if one is missing, because a
#: tag with no definition gets applied differently in the first hour of review than in
#: the third, and 200 paragraphs tagged by a drifting rule are not one corpus.
REGISTER_MEANS: dict[str, Meaning] = {
    "informal_je": Meaning(
        "informal register, usually addressing the reader as je, jij or jouw",
        "Je kunt je bestelling tot 24 uur na plaatsing kosteloos annuleren via je account.",
    ),
    "formal_u": Meaning(
        "formal register, usually addressing the reader as u or uw",
        "U kunt bezwaar maken tegen dit besluit binnen zes weken na de verzenddatum.",
    ),
    "business": Meaning(
        "assumes a working context and uses its vocabulary; addresses nobody",
        "Het bestuur heeft besloten de contributie dit jaar niet te verhogen.",
    ),
    "plain_language": Meaning(
        "an ordinary fact in everyday words, for any reader; addresses nobody",
        "De trein naar Utrecht vertrekt van spoor 5 en heeft ongeveer vijf minuten vertraging.",
    ),
}

#: Every `Domain` value, defined. Same rule, same reason.
DOMAIN_MEANS: dict[str, Meaning] = {
    "administrative": Meaning(
        "dealings with government or an institution: applications, decisions, obligations",
        "U ontvangt binnen vijf werkdagen een bevestiging van uw aanvraag.",
    ),
    "commercial": Meaning(
        "buying and selling: orders, deliveries, prices, invoices",
        "De omzet van de detailhandel lag 3,5 procent hoger dan een jaar eerder.",
    ),
    "technical": Meaning(
        "software, devices, how a thing works or is configured",
        "Deze functie werkt alleen als de server draait met versie 3.2 of hoger.",
    ),
    "care": Meaning(
        "health, wellbeing, treatment and support",
        "De patiënt gaf aan dat de klachten sinds vorige week zijn afgenomen.",
    ),
    "education": Meaning(
        "teaching and learning: lessons, assignments, courses",
        "De leerlingen krijgen volgende week een toets over de Gouden Eeuw.",
    ),
    "everyday": Meaning(
        "ordinary life outside the other five: travel, cooking, household",
        "Voeg twee eetlepels bloem toe en roer tot het mengsel glad is.",
    ),
}

#: How the text got here. `collected` is the only scalable one; `authored` means a
#: named person wrote it for this repository. There is deliberately no third option:
#: model-generated text makes the gate circular (ADR-0007).
Origin = Literal["collected", "authored"]

#: What counts as a paragraph. Below this is a heading, a label or a navigation crumb;
#: above it is usually two paragraphs an extractor failed to split. The exit condition
#: for this corpus is stated in paragraphs, so the floor is written down here where both
#: the collector and the gate read it, rather than being a constant in whichever script
#: happened to need it first.
MIN_CHARS = 80
MAX_CHARS = 400

#: Licences whose text this project may redistribute under CC BY 4.0. CC BY-SA is
#: absent on purpose: share-alike would force this repository's data licence to
#: change, which rules out Dutch Wikipedia and most of what is easy to scrape.
REDISTRIBUTABLE: frozenset[str] = frozenset(
    {"CC0-1.0", "CC-BY-4.0", "CC-BY-3.0", "LicenseRef-PublicDomain"}
)

#: Licences that make naming the creator a condition of passing the text on. CC0 and
#: the public domain waive it, and they are the only reason a collected paragraph is
#: ever allowed to leave `author` empty.
ATTRIBUTION_REQUIRED: frozenset[str] = REDISTRIBUTABLE - {"CC0-1.0", "LicenseRef-PublicDomain"}


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
        #: Who wrote it, which is who a reuser owes credit to. Not the same as `source`:
        #: an index or a platform is where a paragraph was found, and CC BY requires
        #: retaining identification of the creator rather than of the finder.
        author: str = ""
        licence: str = Field(min_length=1)
        #: What was changed and why, for text that is not verbatim at its `url`. Empty
        #: is the normal case and the one a reader should be able to assume, so anything
        #: edited after collection says so here rather than quietly differing from the
        #: page it cites.
        redacted: str = ""
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
            if self.origin == "collected" and self.licence in ATTRIBUTION_REQUIRED:
                if not self.author:
                    raise ValueError(
                        f"{self.id}: {self.licence} requires naming who wrote the text, and "
                        f"the site it was found on is not that"
                    )
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


#: Above this, two paragraphs are the same evidence counted twice. Tuned against the
#: case that prompted it: a statistics office running a monthly series republishes its
#: explanatory paragraphs with only the figures changed.
SIMILARITY = 0.8


def near_duplicate(
    text: str, existing: Iterable[str], *, threshold: float = SIMILARITY
) -> str | None:
    """The paragraph `text` is a near-copy of, or None if it is new.

    An exact repeat is easy and already refused. These are the ones that get through:
    a publisher with a recurring series says the same thing every month with different
    numbers in it. Two of those in the corpus inflate the count without adding evidence,
    and they do it in the one file `self_repetition` is measured against.
    """
    for other in existing:
        # Length alone rules most pairs out, and the ratio is the expensive part.
        if abs(len(text) - len(other)) > max(len(text), len(other), 1) * (1 - threshold):
            continue
        if SequenceMatcher(None, text, other).ratio() >= threshold:
            return other
    return None


def shape(entries: list[CorpusEntry]) -> dict[str, int]:
    """Words, and how many entries are shorter than the paragraphs they are counted as.

    A count of entries is the number that flatters: an exit condition of 200 paragraphs
    met with 200 single sentences is not the evidence it reads as. So the entries below
    `MIN_CHARS` are counted rather than left to pass as paragraphs, by the same floor
    the collector applies when it refuses a string as too short to be one.
    """
    return {
        "words": sum(len(entry.text.split()) for entry in entries),
        "below_floor": sum(1 for entry in entries if len(entry.text) < MIN_CHARS),
        # Printed because "collected" reads as "verbatim", and for these it is not.
        "redacted": sum(1 for entry in entries if entry.redacted),
    }
