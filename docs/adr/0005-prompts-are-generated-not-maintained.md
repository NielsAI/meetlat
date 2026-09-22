---
status: accepted
area: [taxonomy]
date: 2026-09-22
supersedes: []
amends: []
rule: [AGENTS.md]
enforced_by: []
---

# ADR 0005: Prompts are generated from a taxonomy, not maintained as a set

## Status

Accepted (2026-09-22). Not yet built: this is build step 2, and the decision is recorded before
the code so the code is built to fit it.

## Context

Anything published gets scraped into someone's next fine-tune. A fixed public prompt set ages out
of usefulness the moment it is popular enough to matter.

A separate problem: a provider that promises never to train on or mine user conversations has
closed off the usual source of evaluation data. There is no corpus of real prompts to draw from
without breaking that promise.

## Decision

Evaluation prompts are not a file anyone curates. They are **generated per release** from a seed
taxonomy with three axes:

- **Task**: rewrite, summarise, answer from context, draft, translate, explain, extract
- **Register**: informal `je`, formal `u`, business, plain language
- **Domain**: administrative, commercial, technical, care, education, everyday

A generator walks the cells and produces prompts per cell, with the context documents that
faithfulness scoring needs. **The taxonomy is the maintained artifact and it is small. The prompts
are disposable.**

## Consequences

Contamination stops mattering: a regenerated set cannot have been trained on, because the specific
prompts did not exist when the model was trained.

Coverage becomes visible: a gap is an empty cell in the taxonomy rather than an absence nobody
noticed. This is the same reasoning as `meetlat.zeef.PLANNED` in ADR-0002.

It works where user data cannot be touched, which is the only scalable path that keeps a
no-training-on-user-data promise intact.

The cost is realism, and it is real. Generated prompts are not what users actually send, and a
model can score well on synthetic tasks it handles cleanly while failing the messy ones. Two
mitigations: seed the taxonomy from observed task categories rather than from imagination, and
treat every number as comparative between checkpoints rather than as absolute quality. A pass rate
of 0.78 means little on its own; a move from 0.71 to 0.78 on a calibrated judge over a regenerated
prompt set means something.
