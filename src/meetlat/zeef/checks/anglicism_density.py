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

**What normal looks like**: 0.23 per 1000 over the 302-entry clean corpus (8812 words,
2 hits, 1 distinct). That is the number a checkpoint's score is read against.

It was 0.00 while the corpus was 190 paragraphs, and this docstring used the zero as
evidence that the two filters on the list were strict enough. The corpus outgrew that
argument, so it is recorded here rather than quietly replaced. Both hits are the word
`Information`, inside `Network and Information Security directive` (the EU directive's
own name) and `Chief Information Officer` (a job title). Neither is English used where
ordinary Dutch exists, which is what this check is for.

So they are a **third way to be wrong that neither filter covers**: English inside a
proper name. Naturalised loanwords and Dutch homographs were both anticipated; a name
that happens to contain a counted word was not. Whether `anglicisms.txt` should gain a
proper-noun guard, or whether a rate this low is simply the floor and the honest thing
is to stop claiming silence, is an open decision. Until it is made, read the baseline
as what a corpus of institutional Dutch produces, not as proof the list never fires on
correct Dutch.
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
