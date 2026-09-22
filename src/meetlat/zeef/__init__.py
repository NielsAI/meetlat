"""The zeef (layer 1): deterministic checks, no model call, run on every generation.

Everything a model produces passes through it. It costs nothing, so it runs on all of
it rather than on a sample, and what it catches it catches with certainty.

Adding a check means writing it in `checks/`, registering it here, and giving it a
fixture file under `tests/fixtures/`. `scripts/check_zeef_contract.py` enforces
the third step, so a check cannot enter the registry without evidence that it fires
where it should and stays silent on the clean corpus.

`PLANNED` names the checks the architecture calls for that do not exist yet. It is
there so a gap is a visible empty cell rather than an absence nobody noticed, the
same reason the prompt taxonomy is the maintained artifact rather than the prompts.
"""

from __future__ import annotations

from typing import Final

from meetlat.types import Check, ZeefReport
from meetlat.zeef.checks.anglicism_density import anglicism_density
from meetlat.zeef.checks.phrase_checks import meta_commentary, translationese
from meetlat.zeef.checks.register_consistency import register_consistency
from meetlat.zeef.checks.self_repetition import self_repetition
from meetlat.zeef.checks.sentence_length import sentence_length
from meetlat.zeef.checks.spelling import spelling

CHECKS: Final[tuple[Check, ...]] = (
    register_consistency,
    translationese,
    meta_commentary,
    self_repetition,
    sentence_length,
    anglicism_density,
    spelling,
)

#: Designed in ADR-0001, not yet built. Each line says what it still needs.
PLANNED: Final[dict[str, str]] = {}


def check_by_name(name: str) -> Check:
    for check in CHECKS:
        if check.name == name:
            return check
    raise KeyError(f"no layer 1 check named {name!r}; have {[c.name for c in CHECKS]}")


def run(text: str, *, only: tuple[str, ...] = ()) -> ZeefReport:
    """Run every check (or just `only`) and validate each result against the contract."""
    selected = tuple(check_by_name(n) for n in only) if only else CHECKS
    results = []
    for check in selected:
        result = check.run(text)
        result.validate(text)
        results.append(result)
    return ZeefReport(text=text, results=tuple(results))
