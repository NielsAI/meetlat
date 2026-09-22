"""Out-of-vocabulary rate against the OpenTaal word list, as a distribution.

ADR-0008 works out why this cannot be a verdict: Dutch forms compounds productively
(*evaluatieharnas*, *woordenlijstcontrole*), so a flat lookup fires on correct Dutch
constantly, which is exactly the false positive ADR-0002 exists to rule out. A
compound splitter fixes that, but only by accepting a wider class than "correct
compound": *evaluatiehuisdier* decomposes exactly as *evaluatieharnas* does, because
both are two known words joined by a legal rule and the difference between them is
meaning, not form. No lexicon can tell them apart, so this check does not try. It
reports how much of a response is outside the list, known compounds included; it
never claims a word is wrong.

**Decomposition**: a word counts as known if it is in the list directly, or if some
split of it into two known parts (optionally joined by one of the Dutch linking
morphemes `""`, `"s"`, `"en"`, `"e"`) is known, recursively. Every part must be at
least 4 characters. The floor is doing real work: the list holds 2,138 entries
shorter than 4 characters, including things like the area code `010`, and without a
floor almost any string can be built from them. 4 rather than 5 is deliberate too;
at 5, *taalmodelbeoordeling* stops decomposing on `taal`. Genuine misspellings
(`onstaan` for `ontstaan`, `teh` for `the`) do not decompose under these rules and
are counted, which is what the metric is for.

**What normal looks like**: 0.00 per 1000 over the 28-paragraph clean corpus (360
words, zero out-of-vocabulary tokens), across all four registers. `words` counts only
tokens carrying a letter, which is why it is 360 here where `anglicism_density`
counts 366: the six numerals in the corpus are not words a word list can adjudicate.

Zero on known-correct Dutch is what makes the number readable, but do not expect it
from generated text. Proper nouns are the reason: people, places, companies and
product names are out of vocabulary by construction and no list will hold them, so a
real response's rate moves with its prompt's domain more than with its spelling
(ADR-0008). This is comparative between checkpoints over a regenerated prompt set,
and it is not a measure of how many words are wrong.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Final

from meetlat.resources import word_set
from meetlat.types import CheckKind, CheckResult

_WORD = re.compile(r"\w[\w'-]*", re.UNICODE)

#: Empty string first: a word can be two known parts with nothing between them.
_LINKERS: Final = ("", "s", "en", "e")

#: See the module docstring: this is what keeps decomposition from accepting nearly
#: everything, given how many short entries the vendored list holds.
_MIN_PART = 4


def _vocabulary() -> frozenset[str]:
    return word_set("opentaal-wordlist")


@lru_cache(maxsize=50_000)
def _known(word: str) -> bool:
    """Whether `word` (already lowercased) is in the list, or decomposes into parts that are.

    Memoized because a response can repeat the same long compound or the same
    misspelling many times, and recursion over every split point is not free.
    Bounded rather than `maxsize=None` like the other resource caches: those cache a
    fixed, finite set of files, and this caches arbitrary words from generated text.
    """
    vocab = _vocabulary()
    if word in vocab:
        return True
    if len(word) < 2 * _MIN_PART:
        return False
    for split in range(_MIN_PART, len(word) - _MIN_PART + 1):
        left = word[:split]
        if left not in vocab:
            continue
        for linker in _LINKERS:
            remainder = word[split:]
            if not remainder.startswith(linker):
                continue
            rest = remainder[len(linker) :]
            if len(rest) >= _MIN_PART and _known(rest):
                return True
    return False


class Spelling:
    name: Final = "spelling"
    kind: CheckKind = "distribution"
    description: Final = "Out-of-vocabulary rate against OpenTaal, with compounds decomposed."

    def run(self, text: str) -> CheckResult:
        # Only tokens carrying a letter, because a word list cannot adjudicate a
        # numeral and whether it holds one is an accident of compilation: `010` is in
        # it because OpenTaal ships area codes, `24` is not. Counting them would make
        # the rate partly a measure of which numbers the list happens to contain,
        # which is the same kind of systematic non-defect decomposition exists to keep
        # out of the count.
        tokens = [token for token in _WORD.findall(text) if any(c.isalpha() for c in token)]
        if not tokens:
            return CheckResult(check=self.name, kind=self.kind, metrics={"words": 0.0})

        out_of_vocabulary = [t.lower() for t in tokens if not _known(t.lower())]
        return CheckResult(
            check=self.name,
            kind=self.kind,
            metrics={
                "words": float(len(tokens)),
                "out_of_vocabulary": float(len(out_of_vocabulary)),
                "distinct": float(len(set(out_of_vocabulary))),
                "per_1000": round(len(out_of_vocabulary) / len(tokens) * 1000, 2),
            },
        )


spelling = Spelling()
