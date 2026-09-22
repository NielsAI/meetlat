"""Sentence length, reported as a distribution and never as a verdict.

There is no sentence length that is wrong. A legal summary and a message to a
customer have different right answers, and a threshold here would encode one of
them as the truth for both. So this check reports numbers and leaves the judgement
to whoever is comparing two checkpoints (ADR-0002).

What it is for: style drift. A model whose median sentence grew from 12 words to 24
between checkpoints changed something, and the number says so before any reader
notices.
"""

from __future__ import annotations

import re
import statistics
from typing import Final

from meetlat.types import CheckKind, CheckResult

# Split on sentence-final punctuation followed by whitespace. Abbreviations and
# ordinals ("bijv.", "3. ") will over-split; that is acceptable in a statistic and
# would not be in a verdict, which is the reason this check is the kind it is.
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"\w[\w'-]*", re.UNICODE)


class SentenceLength:
    name: Final = "sentence_length"
    kind: CheckKind = "distribution"
    description: Final = "Sentence length distribution, for detecting style drift."

    def run(self, text: str) -> CheckResult:
        lengths = [
            len(_WORD.findall(sentence))
            for sentence in _SENTENCE.split(text.strip())
            if _WORD.search(sentence)
        ]
        if not lengths:
            return CheckResult(check=self.name, kind=self.kind, metrics={"sentences": 0.0})

        ordered = sorted(lengths)
        return CheckResult(
            check=self.name,
            kind=self.kind,
            metrics={
                "sentences": float(len(lengths)),
                "words": float(sum(lengths)),
                "mean": round(statistics.fmean(lengths), 2),
                "median": float(statistics.median(lengths)),
                "p90": float(ordered[min(len(ordered) - 1, int(len(ordered) * 0.9))]),
                "max": float(max(lengths)),
            },
        )


sentence_length = SentenceLength()
