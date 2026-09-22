"""Informal `je/jij/jouw` mixed with formal `u/uw` inside one response.

The defect is real and common, but the obvious implementation has a false positive
that would sink the check. Bare `je` has an impersonal reading (`je kunt hier
parkeren`, roughly English generic `you`) that Dutch writers use inside otherwise
formal text without it reading as a register slip. A check that fires on `u` plus
any `je` therefore fires on well-written formal prose, and a check that cries wolf
gets switched off (ADR-0002).

So the trigger is narrower than the report. The response is only called mixed when
it contains a formal marker AND an *unambiguous* informal pronoun, one with no
impersonal reading. Once that is established, every marker of both families is
reported, bare `je` included, because by then the mixing is a fact and the reader
wants all of it located.
"""

from __future__ import annotations

import re
from typing import Final, Literal, NamedTuple

from meetlat.types import CheckKind, CheckResult, Finding, Span

#: No impersonal reading. `jij` is emphatic, the rest are its case and plural forms.
UNAMBIGUOUS_INFORMAL: Final = ("jij", "jou", "jouw", "jouwe", "jullie", "jezelf")

#: Has an impersonal reading, so it is evidence only once mixing is established.
AMBIGUOUS_INFORMAL: Final = ("je",)

FORMAL: Final = ("u", "uw", "uzelf")


def _word_pattern(words: tuple[str, ...]) -> re.Pattern[str]:
    # Longest-first so `jouw` is not matched as `jou` followed by a stray `w`.
    alternatives = "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True))
    # The trailing hyphen exclusion keeps compounds out, where the letters are not a
    # pronoun at all: `u-bocht`, `je-vorm`.
    return re.compile(rf"(?<!\w)(?:{alternatives})(?![\w-])", re.IGNORECASE)


_UNAMBIGUOUS = _word_pattern(UNAMBIGUOUS_INFORMAL)
_ALL_INFORMAL = _word_pattern(UNAMBIGUOUS_INFORMAL + AMBIGUOUS_INFORMAL)
_FORMAL = _word_pattern(FORMAL)


#: Which family a marker belongs to. `impersonal` is bare `je`, kept apart from the
#: rest because its impersonal reading is the entire reason this check is narrow: it
#: is the one marker whose presence settles nothing.
MarkerKind = Literal["formal", "informal", "impersonal"]


class Marker(NamedTuple):
    """One register marker, located and named. Carries no verdict."""

    start: int
    end: int
    text: str
    kind: MarkerKind


def markers(text: str) -> list[Marker]:
    """Every register marker in `text`, tagged by family, in the order they appear.

    `run` deliberately reports nothing until mixing is established, which is correct for
    a verdict and useless to a person deciding which register a paragraph is written in.
    This locates the same markers unconditionally, so a reader can see the evidence the
    check declined to draw a conclusion from, and keeps the three families apart because
    telling impersonal `je` from informal `je` is the judgement being made.

    Shares its patterns with `run` rather than restating them: a reviewer shown a
    different set of markers than the check acts on would be reading the wrong evidence.
    """
    found = [Marker(m.start(), m.end(), m.group(0), "formal") for m in _FORMAL.finditer(text)]
    for m in _ALL_INFORMAL.finditer(text):
        kind: MarkerKind = "informal" if _UNAMBIGUOUS.fullmatch(m.group(0)) else "impersonal"
        found.append(Marker(m.start(), m.end(), m.group(0), kind))
    return sorted(found, key=lambda marker: marker.start)


class RegisterConsistency:
    name: Final = "register_consistency"
    kind: CheckKind = "verdict"
    description: Final = "Informal je/jij/jouw mixed with formal u/uw inside one response."

    def run(self, text: str) -> CheckResult:
        formal = list(_FORMAL.finditer(text))
        if not formal or not _UNAMBIGUOUS.search(text):
            return CheckResult(check=self.name, kind=self.kind)

        matches = sorted(formal + list(_ALL_INFORMAL.finditer(text)), key=lambda m: m.start())
        findings = tuple(
            Finding(
                check=self.name,
                message=(
                    f"{m.group(0)!r} is "
                    f"{'formal' if _FORMAL.fullmatch(m.group(0)) else 'informal'}, "
                    "and this response uses both."
                ),
                span=Span(m.start(), m.end(), m.group(0)),
            )
            for m in matches
        )
        return CheckResult(check=self.name, kind=self.kind, findings=findings)


register_consistency = RegisterConsistency()
