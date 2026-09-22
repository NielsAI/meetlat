"""Expand the taxonomy into a prompt set for one release (ADR-0005).

Templates and a seed, not a model. Three reasons, in order of weight. A model-written
prompt set would need its own calibration before anything measured with it meant
anything, which is the problem this repository already has one layer of. It would also
put one model's idea of a task at the centre of a harness meant to compare models. And
`meetlat.zeef` runs with no endpoint, no key and no budget, which is worth keeping true
of everything a person needs before they have an API account.

The contamination argument in ADR-0005 survives this. What is published here is the
template space, not the prompts: the specific wording of release *n* is drawn from a
seed and did not exist before that release, so it cannot have been trained on. A seed
also makes a release reproducible, which a model would not be.

**The bias this does not fix**, stated because it is the cost of the method: generated
prompts are not what users send. A checkpoint can score well on tasks phrased the way
this file phrases them and badly on the messy ones. ADR-0005's mitigation is to read
every number as comparative between checkpoints rather than as absolute quality, and
nothing here changes that.
"""

from __future__ import annotations

import json
import random
import warnings
from pathlib import Path
from typing import Final, get_args

from pydantic import BaseModel, ConfigDict, Field

from meetlat.taxonomy import (
    NEEDS_CONTEXT,
    Cell,
    Domain,
    Register,
    Task,
    cells,
)

#: How a template asks for each register. The output register is the axis being varied,
#: so the instruction names it: a prompt that only implies the register measures whether
#: the model guessed right, which is a different question from whether it can hold one.
_REGISTER_ASK: Final[dict[str, tuple[str, ...]]] = {
    "informal_je": (
        "Spreek de lezer aan met `je`.",
        "Schrijf informeel, met `je` en `jouw`.",
        "Gebruik een informele toon en spreek de lezer aan met `je`.",
    ),
    "formal_u": (
        "Spreek de lezer aan met `u`.",
        "Schrijf formeel, met `u` en `uw`.",
        "Houd een formele toon aan en spreek de lezer aan met `u`.",
    ),
    "business": (
        "Schrijf zakelijk, zonder de lezer aan te spreken.",
        "Gebruik zakelijk Nederlands en richt je tot niemand in het bijzonder.",
        "Houd een zakelijke toon aan en spreek niemand rechtstreeks aan.",
    ),
    "plain_language": (
        "Schrijf in eenvoudig Nederlands voor een algemene lezer.",
        "Gebruik gewone woorden, zonder de lezer aan te spreken.",
        "Schrijf op B1-niveau, begrijpelijk voor iedereen.",
    ),
}

#: What a `draft` or `explain` prompt is about, per domain. These two tasks get no
#: document, so the subject has to come from somewhere, and a bank per domain is the
#: smallest thing that keeps the domain axis real rather than decorative.
_SUBJECTS: Final[dict[str, tuple[str, ...]]] = {
    "administrative": (
        "het verzetten van een afspraak bij de gemeente",
        "het aanvragen van een uittreksel uit de basisregistratie",
        "bezwaar maken tegen een besluit",
        "het doorgeven van een verhuizing",
    ),
    "commercial": (
        "een bestelling die later wordt bezorgd dan beloofd",
        "het terugsturen van een artikel binnen de bedenktijd",
        "een factuur die niet klopt",
        "de garantie op een apparaat dat kapot is gegaan",
    ),
    "technical": (
        "het instellen van tweefactorauthenticatie",
        "waarom een update soms opnieuw opstarten vereist",
        "het verschil tussen een open en een gesloten standaard",
        "het maken van een back-up van je bestanden",
    ),
    "care": (
        "het aanvragen van hulp bij het huishouden",
        "wat een mantelzorger wel en niet mag regelen",
        "het voorbereiden van een gesprek met de huisarts",
        "hoe een indicatie voor zorg tot stand komt",
    ),
    "education": (
        "het kiezen van een profiel in de bovenbouw",
        "hoe een ouderavond wordt voorbereid",
        "het inhalen van een gemiste toets",
        "waarom lezen buiten school het leren helpt",
    ),
    "everyday": (
        "het bewaren van restjes zodat ze veilig blijven",
        "wat je meeneemt op reis naar het buitenland",
        "het scheiden van afval in huis",
        "het verzorgen van een huisdier tijdens de vakantie",
    ),
}

#: One template per phrasing, per task. `{ask}` takes the register sentence, `{subject}`
#: a line from `_SUBJECTS`, and a document task says where the text is instead.
_TEMPLATES: Final[dict[str, tuple[str, ...]]] = {
    "rewrite": (
        "Herschrijf de tekst hieronder. {ask}",
        "Schrijf de onderstaande tekst opnieuw en houd de inhoud gelijk. {ask}",
        "Pas de tekst hieronder aan zodat hij beter leest. {ask}",
    ),
    "summarise": (
        "Vat de tekst hieronder samen in maximaal drie zinnen. {ask}",
        "Geef de kern van de onderstaande tekst weer. {ask}",
        "Maak een korte samenvatting van de tekst hieronder. {ask}",
    ),
    # These carry the question themselves. A template that says "beantwoord de vraag"
    # and supplies no question is not a prompt, and the first draft of this file shipped
    # three of them. The questions are generic on purpose: they have to be answerable
    # from any institutional document without a model inventing one per context, and
    # what is being measured is whether the answer stays inside the document.
    "answer_from_context": (
        "Wat moet iemand volgens de tekst hieronder doen, en binnen welke termijn? "
        "Gebruik alleen wat er staat. {ask}",
        "Voor wie geldt wat in de tekst hieronder staat, en welke voorwaarden worden "
        "genoemd? Gebruik uitsluitend de tekst. {ask}",
        "Welke verplichtingen of uitzonderingen noemt de tekst hieronder? Baseer je "
        "antwoord alleen op die tekst. {ask}",
    ),
    "extract": (
        "Haal de gevraagde gegevens uit de tekst hieronder en noem ze. {ask}",
        "Noem welke feiten in de onderstaande tekst staan over data, bedragen en termijnen. {ask}",
        "Zet de concrete gegevens uit de tekst hieronder op een rij. {ask}",
    ),
    "draft": (
        "Schrijf een kort bericht over {subject}. {ask}",
        "Stel een korte tekst op over {subject}. {ask}",
        "Schrijf een alinea over {subject}. {ask}",
    ),
    "explain": (
        "Leg uit wat er komt kijken bij {subject}. {ask}",
        "Geef uitleg over {subject}. {ask}",
        "Beschrijf in het kort wat iemand moet weten over {subject}. {ask}",
    ),
}


class ContextDocument(BaseModel):
    """A document handed to the model for a task that needs one.

    Deliberately not `tests/corpora/clean_nl.jsonl`. That corpus is *selected* for the
    property that no layer 1 check fires on it, so using it here would mean a model that
    copies its input scores perfectly on layer 1, in the one layer that runs on every
    response. The false-positive gate and the evaluation input stay disjoint.

    Carries its licence and url for the same reason a corpus entry does: this text gets
    published with the prompt set, so it has to be text this project may pass on.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    domain: Domain
    source: str = Field(min_length=1)
    licence: str = Field(min_length=1)
    author: str = ""
    url: str = ""


# `register` is this project's vocabulary and the axis this whole file varies, so the
# field keeps the name. Same shadow of `ABCMeta.register` that `zeef.corpus` silences,
# for the same reason and with the same narrow filter.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message='Field name "register"', category=UserWarning)

    class Prompt(BaseModel):
        """One generated evaluation prompt, and the cell it came from."""

        model_config = ConfigDict(extra="forbid", frozen=True)

        id: str = Field(min_length=1)
        task: Task
        register: Register
        domain: Domain
        instruction: str = Field(min_length=1)
        #: The document this prompt hands the model, for a task in `NEEDS_CONTEXT`.
        #: Empty for `draft` and `explain`, the tasks that take no source text.
        context_id: str = ""
        #: The seed this prompt was drawn with, so a published number can name the set
        #: it was measured over and that set can be rebuilt exactly.
        seed: int


def load_contexts(path: Path) -> list[ContextDocument]:
    """Read the context pool. Raises with the line number on a malformed document."""
    documents: list[ContextDocument] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        try:
            documents.append(ContextDocument.model_validate(json.loads(line)))
        except Exception as exc:
            raise ValueError(f"{path.name}:{line_no}: {exc}") from exc
    if len({document.id for document in documents}) != len(documents):
        raise ValueError(f"{path.name}: duplicate document ids")
    return documents


def for_cell(
    cell: Cell, rng: random.Random, seed: int, index: int, contexts: list[ContextDocument]
) -> Prompt | None:
    """One prompt for one cell, or None when the cell has no context document to use.

    Returning None rather than raising: a thin context pool is a gap to be reported per
    cell, which is what ADR-0005 wants a gap to look like, not a crash halfway through
    generating a release.
    """
    ask = rng.choice(_REGISTER_ASK[cell.register])
    template = rng.choice(_TEMPLATES[cell.task])

    context_id = ""
    if cell.task in NEEDS_CONTEXT:
        usable = [document for document in contexts if document.domain == cell.domain]
        if not usable:
            return None
        context_id = rng.choice(usable).id

    instruction = template.format(ask=ask, subject=rng.choice(_SUBJECTS[cell.domain]))
    return Prompt(
        id=f"p-{seed}-{index:04d}",
        task=cell.task,
        register=cell.register,
        domain=cell.domain,
        instruction=instruction,
        context_id=context_id,
        seed=seed,
    )


def generate(
    *, seed: int, per_cell: int = 1, contexts: list[ContextDocument] | None = None
) -> tuple[list[Prompt], dict[Cell, str]]:
    """A prompt set for one release, and the cells that stayed empty with the reason.

    Seeded per cell rather than once for the whole run, so adding a task or a domain
    does not reshuffle the prompts in every other cell. A release should differ from the
    last one because the seed changed, not because the grid grew.

    Within a cell the draws are distinct: two identical prompts in one cell are one
    prompt and an inflated count, which is the same way a corpus grows a number without
    growing evidence. A cell whose template space is smaller than `per_cell` yields what
    it has and says so, rather than padding with repeats.
    """
    pool = contexts or []
    prompts: list[Prompt] = []
    empty: dict[Cell, str] = {}
    index = 0

    for cell in cells():
        seen: set[str] = set()
        for draw in range(per_cell):
            rng = random.Random(f"{seed}/{cell}/{draw}")
            prompt = for_cell(cell, rng, seed, index + 1, pool)
            if prompt is None:
                empty[cell] = f"no context document tagged {cell.domain}"
                break
            # Redraw rather than accept a repeat. Bounded because the template space is
            # small and a bound that is reached is reported as a thin cell, not retried
            # forever.
            for attempt in range(1, 12):
                if prompt is not None and prompt.instruction not in seen:
                    break
                rng = random.Random(f"{seed}/{cell}/{draw}/{attempt}")
                prompt = for_cell(cell, rng, seed, index + 1, pool)
            if prompt is None or prompt.instruction in seen:
                empty.setdefault(cell, f"only {len(seen)} distinct prompts available")
                break
            seen.add(prompt.instruction)
            index += 1
            prompts.append(prompt)

    return prompts, empty


def coverage(prompts: list[Prompt]) -> dict[str, int]:
    """Prompts per task, including the tasks with none, for the same reason as registers."""
    counted = {task: 0 for task in get_args(Task)}
    for prompt in prompts:
        counted[prompt.task] += 1
    return counted
