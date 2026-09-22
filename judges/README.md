# judges/

One directory per judge version: `judges/<criterion>/v<n>/`.

Nothing here yet. The schema, the gate and the protocol exist first so the first judge can be
built correctly rather than built and then retrofitted (ADR-0003, ADR-0004).

## What a judge version contains

```text
judges/instruction_compliance/v1/
  prompt.md        the judge prompt, verbatim
  verdicts.jsonl   {"id": "...", "verdict": true} per item of the calibration run
  card.json        what this judge is entitled to claim
```

`card.json`, validated by `meetlat.keuring.JudgeCard`:

```json
{
  "criterion": "instruction_compliance",
  "version": 1,
  "question": "Did the response do what the prompt asked?",
  "model": "qwen3-27b-2026-04-01",
  "temperature": 0.0,
  "prompt_sha256": "<sha256 of prompt.md>",
  "thresholds": { "balanced_accuracy": 0.85, "cohen_kappa": 0.6 },
  "calibration": {
    "date": "2026-10-05",
    "gold_set": "gold/instruction_compliance-v1.jsonl",
    "verdicts": "verdicts.jsonl",
    "annotators": ["niels", "..."],
    "items": 180,
    "balanced_accuracy": 0.88,
    "cohen_kappa": 0.71
  },
  "status": "certified"
}
```

## What the gate will not let you do

`make check-judges`, and the same command in CI:

- **Edit the prompt without recalibrating.** `prompt_sha256` is checked against the file. A judge
  whose prompt changed is a new judge: bump the version and run the protocol again.
- **Claim a number the labels do not give.** Balanced accuracy and kappa are recomputed from the
  reconciled labels and this run's verdicts. The card is checked, not trusted.
- **Certify below threshold.** Kappa 0.6, balanced accuracy 0.85. A judge below either sets
  `status: "withdrawn"` and goes back to prompt revision.
- **Lower a threshold to fit a judge.** The floors live in `meetlat.keuring.card`; a card may hold
  itself to more and never to less.
- **Pin nothing.** A floating model tag is refused: the judge that was calibrated and the judge
  that runs would be two different judges.
- **Calibrate against one interaction type.** A number from a single type says nothing about the
  traffic it will be applied to.

The `/calibrate-judge` skill is the procedure from sampling to a card that passes.
