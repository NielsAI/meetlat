# CONTEXT.md

The vocabulary. Use these exact words in code, commits, issues, and anything the project
publishes: a criterion described two ways becomes two criteria within a month.

## The layers

Three Dutch words, and the only Dutch in the codebase outside the Dutch text itself (ADR-0001).

| Term | Layer | Literally | Here |
| --- | --- | --- | --- |
| **zeef** | 1 | sieve | The deterministic checks. Everything a model produces passes through it; it costs nothing, so it runs on all output rather than a sample |
| **keuring** | 2 | inspection | The judges. One criterion, one binary verdict, one model call per item |
| **ijk** | 3 | calibration, in the weights-and-measures sense | Certifying a judge against hand labels. It scores nothing itself |

## Everything else

**check** — one rule in the zeef. Either a **verdict check**, which fires only where it is certain,
or a **distribution check**, which reports numbers and can never fail (ADR-0002).

**finding** — one defect, located. Always carries a **span**.

**span** — a start offset, an end offset, and the literal text at those offsets in the response.
Validated against the response, so a score can always be read back to the words that caused it.

**judge** — a layer 2 evaluator: one criterion, one yes-or-no question, one binary verdict. A
versioned artifact under `judges/<criterion>/v<n>/`, with its model and temperature pinned. A judge
whose prompt changed is a different judge (ADR-0003).

**card** — `card.json`: what a judge is entitled to claim. Model, temperature, the sha256 of the
prompt it was calibrated against, its thresholds, and the agreement figures from its last
calibration.

**criterion** — one property a judge asks about: `instruction_compliance`, `faithfulness`,
`register_fit`, `naturalness`, `task_completion`. One criterion per judge, always.

**gold set** — the hand-labelled items under `gold/`. An *instrument*, not a benchmark: nothing is
scored against it for its own sake, and its only job is measuring whether a judge agrees with a
person. Fixed size, 150 to 200 items per criterion.

**reconciled label** — the label two annotators agreed on after discussing a disagreement, with the
reasoning written down. This, not either individual label, is the ground truth a judge is scored
against.

**the gate** — the threshold a judge passes before it may report numbers: kappa above 0.6, balanced
accuracy above 0.85 (ADR-0004). "Through the gate" means calibrated and certified.

**interaction type** — what the prompt asked for: rewrite, summarise, answer from context, draft,
translate, explain, extract. Every score is reported per interaction type, because a pass rate over
mixed traffic hides that rewriting works and summarising does not.

**taxonomy** — the three axes evaluation prompts are generated from: task × register × domain. The
taxonomy is maintained; the prompts are disposable (ADR-0005).

**register** — the formality a Dutch text is written in: informal `je`, formal `u`, business, plain
language. Mixing two in one response is a defect, which is what `register_consistency` catches.

The four are defined with an example each in `REGISTER_MEANS`, and the six **domains** in
`DOMAIN_MEANS`, both in `src/meetlat/zeef/corpus.py`. They live in code rather than here because
`make review` shows them while you tag a paragraph, and `make check-zeef` fails if a register or
domain has no definition: a tag defined nowhere gets applied one way in the first hour of review
and another way in the third.

The pair worth knowing: `business` and `plain_language` both address nobody. Business is
professional or organisational prose (*"Het bestuur heeft besloten de contributie niet te
verhogen"*); plain language is an ordinary fact for a general reader with no professional setting
behind it (*"De trein naar Utrecht vertrekt van spoor 5"*).

**translationese** — English phrasing carried into Dutch word for word. A calque, not a borrowing:
`"laten we erin duiken"` is translationese, `"de computer"` is not.

## Words to avoid

**benchmark**, for the gold set. It is an instrument. Calling it a benchmark invites someone to
report a score against it, which is the one thing it is not for.

**accuracy**, unqualified. Say **balanced accuracy**: a stratified set is never balanced exactly,
and plain accuracy on a skewed set flatters a judge that always answers with the majority class.

**pass rate**, without the kappa it was measured at. A pass rate from a judge at kappa 0.62 is a
different claim from one at kappa 0.85.
