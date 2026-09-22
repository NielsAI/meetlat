---
status: accepted
area: [keuring]
date: 2026-09-22
supersedes: []
amends: []
rule: [AGENTS.md]
enforced_by: [scripts/check_judges.py, src/meetlat/keuring/card.py]
---

# ADR 0003: One binary judge per criterion, versioned as an artifact

## Status

Accepted (2026-09-22).

## Context

A judge asked for a 1 to 5 rating produces numbers that look precise and move for reasons nobody
can name. A judge weighing several properties at once hides which one failed, and a prompt change
meant to fix one criterion silently shifts the others.

Both problems have the same root: the judge's output cannot be compared to a human answering the
same question, so there is nothing to calibrate it against.

## Decision

**One criterion per judge, one binary verdict, no composite score.** Pass rates aggregate
afterwards from the binary verdicts; they are not what a judge produces.

The starting criteria, each a single yes-or-no question:

| Criterion | The question |
| --- | --- |
| `instruction_compliance` | Did the response do what the prompt asked, including constraints on length, format and audience |
| `faithfulness` | Is every factual claim supported by the context supplied in the prompt |
| `register_fit` | Does the formality match what the prompt called for |
| `naturalness` | Would a Dutch native writer have produced this, or does it read as translated English |
| `task_completion` | Is the response finished, or truncated, hedged into uselessness, or a refusal |

**Every score is reported per interaction type.** A pass rate over mixed traffic hides that
rewriting works and summarising does not, so the aggregate is a footnote.

**A judge is a versioned artifact on disk**, at `judges/<criterion>/v<n>/`: a `prompt.md`, and a
`card.json` pinning the model and temperature, carrying the sha256 of the prompt it was calibrated
against, and recording the agreement numbers from that calibration.

**A judge whose prompt changed is a new judge.** It bumps its version and re-enters the gate in
ADR-0004.

## Consequences

The prompt hash is the mechanism, because the rule above is not broken by a decision. It is broken
by a two-word edit to a prompt on an evening when re-running the calibration feels like tomorrow's
problem. `scripts/check_judges.py` refuses a card whose prompt no longer hashes to what it claims,
so that edit fails the build instead of quietly invalidating every number the judge has published.

A floating model tag is refused for the same reason: the judge that was calibrated and the judge
that runs would be different judges.
