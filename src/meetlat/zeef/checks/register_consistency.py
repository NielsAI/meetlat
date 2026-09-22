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
from typing import Final

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
