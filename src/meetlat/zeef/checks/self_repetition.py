"""A word sequence the response says twice, verbatim.

Looping is what a decoder does when it runs out of things to say, and padded output
repeats a clause to fill space. Both show up as an exact n-gram appearing more than
once. The window is deliberately long: short repeats are ordinary Dutch (fixed
expressions, list scaffolding, a refrain), while an eight-word sequence repeated
word for word inside one response is not something a writer does by accident.

Only the second and later occurrences are reported. The first is where the sentence
was legitimately written; the repeat is the defect.
"""

from __future__ import annotations

import re
from typing import Final

from meetlat.types import CheckKind, CheckResult, Finding, Span

#: Chosen to sit above the longest fixed Dutch expression and below the shortest
#: clause a model loops on. Lowering it is a calibration question, not a taste one:
#: run it over the clean corpus first (tests/corpora/clean_nl.jsonl).
WINDOW: Final = 8

_WORD = re.compile(r"\w[\w'-]*", re.UNICODE)


class SelfRepetition:
    name: Final = "self_repetition"
    kind: CheckKind = "verdict"
    description: Final = f"A sequence of {WINDOW} words the response repeats verbatim."

    def run(self, text: str) -> CheckResult:
        words = list(_WORD.finditer(text))
        if len(words) < WINDOW * 2:
            return CheckResult(check=self.name, kind=self.kind)

        seen: set[str] = set()
        findings: list[Finding] = []
        reported_to = 0
        for i in range(len(words) - WINDOW + 1):
            window = words[i : i + WINDOW]
            key = " ".join(m.group(0).lower() for m in window)
            if key not in seen:
                seen.add(key)
                continue
            start, end = window[0].start(), window[-1].end()
            # Overlapping windows describe one repeat; report it once.
            if start < reported_to:
                continue
            reported_to = end
            findings.append(
                Finding(
                    check=self.name,
                    message=f"{WINDOW} words repeated verbatim from earlier in the response.",
                    span=Span(start, end, text[start:end]),
                )
            )
        return CheckResult(check=self.name, kind=self.kind, findings=tuple(findings))


self_repetition = SelfRepetition()
