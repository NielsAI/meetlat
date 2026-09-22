"""How much untranslated English a Dutch response carries, as a rate.

A distribution check, not a verdict, and the reason is in the architecture's own
description of it: "wordlist lookup, **tunable threshold**". A threshold somebody can
tune is a threshold somebody can tune until the numbers look right, which ADR-0002
forbids a verdict check from having. So this reports a rate and never fails.

It is also the right shape for the underlying fact. Anglicism density is genuinely
different per domain: a technical text carries English that a letter from a
municipality would not, and neither is wrong. A single number that called both a
defect would be measuring the domain rather than the writing.

The cost is that a distribution check reports no findings, so this cannot point at
the words it counted (ADR-0002 reserves spans for verdicts). `src/meetlat/resources/
anglicisms.txt` is the whole vocabulary, so a reader who wants the words has them.

**What normal looks like**: 0.00 per 1000 over the 196-paragraph clean corpus (5,544
words, zero hits), across all four registers. It held at zero as the corpus grew from 28
hand-written paragraphs to 196 collected ones, which is the evidence that the two filters
on the wordlist are strict enough: naturalised loanwords and Dutch homographs would both
have fired by now. That is the number a checkpoint's score
is read against, and it says the wordlist is conservative enough to be silent on
human Dutch rather than that Dutch contains no English.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Final

from meetlat.resources import phrase_pairs
from meetlat.types import CheckKind, CheckResult


@lru_cache(maxsize=None)
def _pattern() -> re.Pattern[str]:
    words = sorted((english for english, _ in phrase_pairs("anglicisms")), key=len, reverse=True)
    return re.compile(rf"(?<!\w)(?:{'|'.join(re.escape(w) for w in words)})(?!\w)", re.IGNORECASE)


_WORD = re.compile(r"\w[\w'-]*", re.UNICODE)


class AnglicismDensity:
    name: Final = "anglicism_density"
    kind: CheckKind = "distribution"
    description: Final = "Untranslated English per 1000 words, where ordinary Dutch exists."

    def run(self, text: str) -> CheckResult:
        words = len(_WORD.findall(text))
        if not words:
            return CheckResult(check=self.name, kind=self.kind, metrics={"words": 0.0})

        hits = [match.group(0).lower() for match in _pattern().finditer(text)]
        return CheckResult(
            check=self.name,
            kind=self.kind,
            metrics={
                "words": float(words),
                "anglicisms": float(len(hits)),
                "distinct": float(len(set(hits))),
                "per_1000": round(len(hits) / words * 1000, 2),
            },
        )


anglicism_density = AnglicismDensity()
