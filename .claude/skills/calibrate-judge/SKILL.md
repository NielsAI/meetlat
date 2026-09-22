---
name: calibrate-judge
description: Run the calibration protocol for one judge, from sampling and labelling through to a card that passes the gate. Use when adding a judge for a new criterion, when a judge's prompt has changed and it needs to re-enter the gate, or when the user asks whether a judge can be trusted, wants to recalibrate, or asks what its kappa is. Not for running a calibrated judge over output; that is the runner.
---

# calibrate-judge

The protocol from ADR-0004, as the sequence you actually execute. It is written down because it is
the part of this project that resists compression: labelling is human time, two annotators means
finding a second person, and every shortcut here is invisible in the resulting number.

**The protocol is written before the judge, not after.** A judge built without knowing how it will
be validated tends to be built in a way that cannot be validated.

## Before anything

Read `docs/adr/0004-the-calibration-gate.md` and `docs/adr/0003-one-binary-judge-per-criterion.md`.
Then state, in one sentence, the yes-or-no question this judge answers. If that sentence contains
"and", stop: it is two criteria, and it needs two judges.

## 1. Sample, stratified

Draw responses across interaction types, **including cases you expect to fail**. A set sampled
from typical output is all passes and measures nothing: a judge that always answers "yes" would
score perfectly on it, which is the exact failure balanced accuracy exists to expose.

Target 150 to 200 items. Both classes must be present, and `make check-judges` refuses the set if
only one is.

## 2. Two people label, independently and blind

Blind means: before either annotator has seen the judge's verdict on that item. This is the step
most often skipped, and skipping it turns the whole exercise into measuring the judge's agreement
with itself.

You are not an annotator. If the user asks you to label the set, say plainly that a judge
calibrated against labels from the same model family it will evaluate measures very little, and
offer to prepare the items for a person instead.

## 3. Reconcile, and write down why

For every disagreement, record the reasoning in the item's `note`. `gold/` refuses an item where
the annotators disagreed and no note was written.

**Read the notes as a set before going further.** If the disagreements share a shape, the criterion
is badly defined, not the raters careless. Rewrite the criterion and go back to step 1. This is the
most valuable output of the whole protocol and the one people skip past.

## 4. Run the judge and record its verdicts

Over the same items, at the pinned model and temperature. Write `judges/<criterion>/v<n>/`:

```
prompt.md        the judge prompt, verbatim
verdicts.jsonl   {"id": "...", "verdict": true} per item
card.json        model, temperature, prompt_sha256, thresholds, calibration
```

Compute the hash with `python -c "from meetlat.keuring import prompt_digest; from pathlib import Path; print(prompt_digest(Path('judges/<criterion>/v<n>/prompt.md')))"`.
Do not hand-write the agreement figures: compute them with `meetlat.ijk.score` over the reconciled
labels and the verdicts, and put those numbers on the card. The gate recomputes them and a
mismatch fails the build.

## 5. The gate decides, not you

```bash
make check-judges
```

Kappa above 0.6 and balanced accuracy above 0.85. **Below either, the judge does not report
numbers.** Set `status: "withdrawn"`, revise the prompt, bump the version, and go back to step 4
with the same labelled set. Revising the prompt against the set is legitimate; revising the
threshold to fit the judge is not.

## When it passes

Say the numbers whenever the judge's results are quoted, including the threshold in force. A pass
rate from a judge at kappa 0.62 is a different claim from one at kappa 0.85, and both are
different from an uncalibrated score.
