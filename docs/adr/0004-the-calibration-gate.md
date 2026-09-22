---
status: accepted
area: [ijk]
date: 2026-09-22
supersedes: []
amends: []
rule: [AGENTS.md, .claude/skills/calibrate-judge/SKILL.md]
enforced_by: [scripts/check_judges.py, src/meetlat/ijk/gold.py]
---

# ADR 0004: A judge below threshold does not report numbers

## Status

Accepted (2026-09-22).

## Context

The gold set is an instrument, not a benchmark. Hand-labelling is the one cost in this system that
does not scale, so the temptation is to spend it on a small evaluation set and quote the score.
That produces exactly the thing this project exists to argue against: a quality claim measured on
a few dozen prompts, which cannot distinguish a real improvement from noise whatever the number
says.

## Decision

**The gold set's only job is to measure whether a judge agrees with a human.** Roughly 150 to 200
items per criterion. Nothing is scored against it for its own sake.

**The protocol**, in order:

1. Sample responses stratified across interaction types, **including cases expected to fail**. A
   gold set drawn from typical output is all passes and measures nothing.
2. Two people label each item independently, blind to the judge's verdict.
3. Reconcile disagreements and record the reasoning. Where two humans cannot agree, the criterion
   is badly defined and gets rewritten before any judge is built for it.
4. Run the judge over the same items and compute balanced accuracy and Cohen's kappa against the
   reconciled labels.
5. **A judge below threshold does not report numbers.** It goes back to prompt revision.

**The threshold is a policy choice, not a fact.** The starting point is kappa above 0.6 and
balanced accuracy above 0.85, and the number is stated wherever the judge's results are published.
A card may hold itself to more; it may not hold itself to less.

**The numbers are recomputed, not trusted.** `scripts/check_judges.py` reads the gold set's
reconciled labels and the calibration run's verdicts and recomputes both figures. A card claiming
a number its own evidence does not support fails the build.

## Consequences

Plain accuracy is deliberately absent from `meetlat.ijk`. A stratified gold set is never balanced
exactly, and accuracy on a skewed set rewards a judge that always answers with the majority class.
Balanced accuracy and kappa both expose that judge; accuracy flatters it.

Every reported number carries its own error bar. A pass rate from a judge at kappa 0.62 is a
different claim from one at kappa 0.85, and both are different from an uncalibrated score.

Open questions, not yet answered:

- What inter-annotator agreement is achievable on `naturalness`, the most subjective criterion and
  the most Dutch-specific.
- Whether `register_fit` needs separate judges for `je` and `u` contexts rather than one.
- How often a gold set needs refreshing as model output distributions shift.
