# gold/

Hand-labelled items, one JSONL file per criterion version: `gold/<criterion>-v<n>.jsonl`.

Nothing here yet.

## Read this before touching anything in this directory

These files are the **instrument**, not a benchmark. Nothing is scored against them for their own
sake. Their only job is measuring whether a judge agrees with a person often enough to be believed,
and every number this project publishes is calibrated against them (ADR-0004).

They are also the only artifact in the repository that is neither reproducible nor recoverable.
Regenerating one does not fail loudly: the judges keep reporting, the numbers keep looking
plausible, and they mean nothing. That is why `scripts/check_gold_write.py` refuses writes to
`gold/*.jsonl` from an agent, fail-closed, while leaving reads and this file alone. **Labels are
added by a person.**

## The format

One item per line, validated by `meetlat.ijk.GoldItem`:

```json
{
  "id": "ic-0042",
  "interaction_type": "rewrite",
  "prompt": "Herschrijf deze alinea in eenvoudig Nederlands, maximaal 60 woorden.",
  "response": "…",
  "labels": { "niels": true, "annotator-2": false },
  "reconciled": false,
  "note": "Tweede annotator las de lengte-eis als richtlijn; bij herlezing is 74 woorden een overschrijding."
}
```

Each field is a rule from the protocol that can be enforced:

- **`labels` needs at least two annotators.** One person labelling is not a ground truth.
- **`reconciled`** is the label they agreed on afterwards, and it is what a judge is scored
  against, not either individual label.
- **`note` is required wherever the annotators disagreed.** That reasoning is the most valuable
  output of the whole protocol: disagreements that share a shape mean the *criterion* is badly
  defined, and the fix is rewriting it before any judge is built for it.
- **`interaction_type`** is required on every item, because a pass rate over mixed traffic hides
  that rewriting works and summarising does not.

## Sampling

Stratified across interaction types, and **including cases you expect to fail**. A set sampled from
typical output is all passes, and a judge that always answers "yes" would score perfectly on it.
`make check-judges` refuses a set whose reconciled labels are all one class, because there is
nothing there to measure.

Target 150 to 200 items per criterion. That cost is fixed while coverage is unlimited: 200 labels
certify a judge that then scores thousands of generations.

## Licence

The labels in this directory are data, not code: CC BY 4.0, see `LICENSE-DATA`. Attribution keeps
the author's name attached to labels that cost human hours to produce.
