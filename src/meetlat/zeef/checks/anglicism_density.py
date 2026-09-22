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

**What normal looks like**: 0.00 per 1000 over the 272-entry clean corpus (8249 words,
zero counted, 2 skipped as names). That is the number a checkpoint's score is read
against.

**How that zero survived, which matters for how much it is worth.** It was a natural
0.00 while the corpus was 190 hand-checked and collected paragraphs, and this docstring
used that as evidence the wordlist's two filters were strict enough. Growing the corpus
into Dutch government IT prose broke it: the rate went to 0.24, on two occurrences of
`Information`, inside `Network and Information Security directive` (an EU directive's
legal name) and `Chief Information Officer` (a job title). Neither is English standing
in where a Dutch word exists, which is the only thing this counts.

That was a **third way to be wrong neither filter covered**: English inside a proper
name. Naturalised loanwords and Dutch homographs were anticipated, a name that happens
to contain a counted word was not. `_inside_a_name` now skips a counted word that sits
in a run of two or more capitalised words, and those skips are reported as `in_names`
rather than dropped, because a filter nobody can see is a filter nobody can argue with.

So read the zero as weaker evidence than the old one. It is no longer the wordlist
being silent unaided; it is the wordlist plus a heuristic this project wrote after
seeing the counter-examples, and a heuristic tuned against the cases that embarrassed
it is exactly the shape of thing that looks better than it is. What keeps it honest is
that `in_names` is published beside the rate, so a reader can see how much work the
guard is doing: here, two words out of 8249. If that number ever grows large, the guard
has stopped being a correction and started being the measurement.
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

#: Between two words of one name there is whitespace, a hyphen or a joiner. Any of these
#: ends the name instead, so `in Nederland. Information is...` is not read as one.
_BREAKS = re.compile(r"[.!?:;\n•()\[\]]")


def _capitalised(word: str) -> bool:
    return word[:1].isupper()


def _adjacent(text: str, left: tuple[int, int], right: tuple[int, int]) -> bool:
    """Whether two word spans sit in one phrase, with nothing sentence-ending between."""
    return not _BREAKS.search(text[left[1] : right[0]])


def _inside_a_name(text: str, spans: list[tuple[int, int]], index: int) -> bool:
    """Whether the word at `spans[index]` is part of a run of capitalised words.

    A proper name is the third way this check can be wrong, after the naturalised
    loanwords and Dutch homographs the wordlist already filters for. `Chief Information
    Officer` is a job title and `Network and Information Security directive` is what an
    EU directive is called; neither is English standing in for a Dutch word, which is
    the only thing this check is counting.

    Two capitalised words in a row rather than one, deliberately. A lone capital is
    ambiguous because a sentence starts with one, so skipping on it would stop counting
    `Deadline` at the start of a sentence, which is a real anglicism and the exact thing
    this exists to see. Two in a row is a name in Dutch, which capitalises far less than
    English does.
    """
    start, end = spans[index]
    if not _capitalised(text[start:end]):
        return False
    before = spans[index - 1] if index else None
    after = spans[index + 1] if index + 1 < len(spans) else None
    if (
        before
        and _capitalised(text[before[0] : before[1]])
        and _adjacent(text, before, spans[index])
    ):
        return True
    return bool(
        after and _capitalised(text[after[0] : after[1]]) and _adjacent(text, spans[index], after)
    )


class AnglicismDensity:
    name: Final = "anglicism_density"
    kind: CheckKind = "distribution"
    description: Final = "Untranslated English per 1000 words, where ordinary Dutch exists."

    def run(self, text: str) -> CheckResult:
        words = len(_WORD.findall(text))
        if not words:
            return CheckResult(check=self.name, kind=self.kind, metrics={"words": 0.0})

        spans = [m.span() for m in _WORD.finditer(text)]
        index_of = {span[0]: i for i, span in enumerate(spans)}

        hits, in_names = [], 0
        for match in _pattern().finditer(text):
            index = index_of.get(match.start())
            if index is not None and _inside_a_name(text, spans, index):
                in_names += 1
                continue
            hits.append(match.group(0).lower())

        return CheckResult(
            check=self.name,
            kind=self.kind,
            metrics={
                "words": float(words),
                "anglicisms": float(len(hits)),
                "distinct": float(len(set(hits))),
                # Reported rather than silently dropped: a filter nobody can see is a
                # filter nobody can argue with, and this one is a heuristic.
                "in_names": float(in_names),
                "per_1000": round(len(hits) / words * 1000, 2),
            },
        )


anglicism_density = AnglicismDensity()
