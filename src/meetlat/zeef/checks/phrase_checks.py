"""The two checks that are a phrase list plus a matcher.

They share an implementation because the only thing that differs is which list they
read and what they call the defect. Splitting them into two modules would duplicate
the matching, which is the part with the edge cases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from meetlat.resources import phrase_list
from meetlat.types import CheckKind, CheckResult, Finding, Span


@lru_cache(maxsize=None)
def _pattern_for(list_name: str) -> re.Pattern[str]:
    """Phrases matched longest-first, so an entry containing another reports once."""
    phrases = sorted(phrase_list(list_name), key=len, reverse=True)
    alternatives = "|".join(re.escape(p) for p in phrases)
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PhraseListCheck:
    """Fires on every occurrence of a listed phrase, case-insensitively.

    Matching is whole-word at both ends, so `een diepe duik` does not fire inside
    `een diepe duikboot`.
    """

    name: str
    description: str
    list_name: str
    message_template: str
    kind: CheckKind = "verdict"

    def run(self, text: str) -> CheckResult:
        findings = [
            Finding(
                check=self.name,
                message=self.message_template.format(phrase=match.group(0)),
                span=Span(match.start(), match.end(), match.group(0)),
            )
            for match in _pattern_for(self.list_name).finditer(text)
        ]
        return CheckResult(check=self.name, kind=self.kind, findings=tuple(findings))


translationese = PhraseListCheck(
    name="translationese",
    description="English phrasing carried into Dutch word for word.",
    list_name="translationese",
    message_template="{phrase!r} reads as translated English rather than written Dutch.",
)

meta_commentary = PhraseListCheck(
    name="meta_commentary",
    description="The assistant commenting on being an assistant instead of answering.",
    list_name="meta_commentary",
    message_template="{phrase!r} is meta-commentary, not part of the answer.",
)
