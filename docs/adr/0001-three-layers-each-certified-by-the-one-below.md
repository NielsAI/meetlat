---
status: accepted
area: [architecture]
date: 2026-09-22
supersedes: []
amends: []
rule: [AGENTS.md]
enforced_by: []
---

# ADR 0001: Three layers, each certified by the one below

## Status

Accepted (2026-09-22). The founding decision; everything else in this log refines it.

## Context

Dutch has two serious evaluation suites. [EuroEval](https://euroeval.com/datasets/dutch) scores
classification and extraction against reference answers. [nl-eval](https://github.com/hoeberigs/nl-eval)
scores 1,363 multiple-choice and exact-match items and says in its own tagline that no judge is
required. Both are well built, and both deliberately restrict themselves to questions that have a
right answer. That restriction is what makes them reliable and it is also what leaves the hole.

A chat assistant does not answer multiple-choice questions. It writes an email, rewrites a
paragraph, answers a question in prose. Nothing public measures whether that output is good Dutch,
whether it did what was asked, or whether it reads as translated English.

Measuring that needs a judge. An uncalibrated judge is not a measurement.

## Decision

Three layers, each cheaper to run and less trustworthy than the one below it.

| Layer | Name | Cost per item | Runs on | Size |
| --- | --- | --- | --- | --- |
| 1 | `zeef` | zero, no model call | every generation | unlimited |
| 2 | `keuring` | one model call per criterion | sampled generations per checkpoint | unlimited |
| 3 | `ijk` | human minutes | nothing; it certifies layer 2 | fixed, 150 to 200 items |

The layers carry Dutch names because they are the project's own vocabulary and the project is
about Dutch. Everything else in the code is English, so a contributor who does not read Dutch
learns three words and no more: `zeef` is a sieve, `keuring` is an inspection, `ijk` is
calibration in the weights-and-measures sense.

The only fixed corpus in the system is layer 3, and it is not an evaluation set. It exists to
answer one question: does this judge agree with a human often enough to be believed. Once a judge
passes that gate it scores unlimited output, so the human cost stays flat while coverage grows.

**The integration point is an OpenAI-compatible chat completions endpoint and nothing else.** No
access to weights, training code, logs or internal tooling. That keeps the harness runnable
against any hosted model by anyone, including against a provider's own model without that
provider's cooperation.

## Consequences

Built bottom up, because each layer is useful before the next one exists and none of them depends
on the layers above. Layer 1 needs no model access, no budget and no cooperation from anyone, so
it produces findings on day one.

What this does not measure, stated here so nobody quotes it as if it did: factual accuracy about
the world (that is EuroEval and nl-eval), grammar as a competence score (nl-eval), safety, bias
and refusal behaviour (a separate axis with a separate method), and anything about real user
traffic (ADR-0005 stands in for it, imperfectly and by design).
