---
status: accepted
area: [zeef]
date: 2026-09-22
supersedes: []
amends: []
rule: [AGENTS.md]
enforced_by: [scripts/check_zeef_contract.py, tests/corpora/clean_nl.txt]
---

# ADR 0002: A check is a verdict or a distribution, and it always names its span

## Status

Accepted (2026-09-22).

## Context

Layer 1 is the layer most projects skip, and it catches a large share of what makes Dutch model
output feel wrong to a native reader: register mixing, untranslated English, calques, looping,
meta-commentary leakage.

It is also the layer that fails in a specific, well-known way. A rule-based checker that produces
false positives gets switched off, and a checker that is switched off protects nothing. Dutch has
two obvious candidates for this failure: `de`/`het` article agreement and clause word order. Both
have enough real exceptions that a rule-based checker cries wolf.

There is a second failure that looks like success. Sentence length, passive ratio and similar
numbers are tempting to threshold, and a threshold encodes one register's right answer as the
truth for all of them.

## Decision

**Two kinds of check, and a check declares which it is.**

- A `verdict` check fires only where it is certain. It reports findings and no metrics, and it has
  failed when it has any finding.
- A `distribution` check reports metrics and never findings. It has no threshold and cannot fail.

**Every finding names the span it fired on**, with start, end and the literal text, validated
against the response it came from. A failing score has to be readable back to the words that
caused it, or it is discouraging rather than actionable.

**Deliberately excluded from layer 1**: `de`/`het` agreement and clause word order. They belong to
layer 2 or nowhere.

**Where a check has to choose between coverage and certainty, it chooses certainty.**
`register_consistency` is the worked example. The obvious implementation fires on `u` plus any
`je`, which fires on well-written formal Dutch, because bare `je` has an impersonal reading. So
the check triggers only on a formal marker plus an *unambiguous* informal pronoun, and only then
reports every marker it can find, bare `je` included.

## Consequences

`scripts/check_zeef_contract.py` enforces all of it: a registered check with no fixture fails the
build, a fixture asserts the exact text of every span, and every verdict check runs over
`tests/corpora/clean_nl.txt`, natural Dutch written by a person, where a single firing is a false
positive and a build failure.

The cost is coverage. `anglicism_density` and `spelling` are designed and not built, because both
need a wordlist before they can meet this bar. They are listed in `meetlat.zeef.PLANNED` and shown
by `meetlat checks`, so the gap is a visible empty cell rather than an absence nobody noticed.
