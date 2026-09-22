# meetlat

A calibrated harness for scoring free-form **Dutch** text generation.

Dutch has two serious evaluation suites and neither one scores free generation.
[EuroEval](https://euroeval.com/datasets/dutch) scores classification and extraction against
reference answers. [nl-eval](https://github.com/hoeberigs/nl-eval) scores 1,363 multiple-choice and
exact-match items and says in its own tagline that no judge is required. Both are well built, and
both deliberately restrict themselves to questions that have a right answer. That restriction is
what makes them reliable, and it is also what leaves the hole.

A chat assistant does not answer multiple-choice questions. It writes an email, rewrites a
paragraph, answers a question in prose. Nothing public measures whether that output is good Dutch,
whether it did what was asked, or whether it reads as translated English.

Measuring that needs a judge. **An uncalibrated judge is not a measurement**, so most of this
project is the machinery that makes a judge worth believing.

## Three layers

| Layer | What it is | Cost per item | Status |
| --- | --- | --- | --- |
| **zeef** (sieve) | Deterministic checks, no model call, run on every generation | zero | built |
| **keuring** (inspection) | Calibrated binary judges, one criterion each | one model call per criterion | gate built, runner not |
| **ijk** (calibration) | Hand labels whose only job is certifying a judge | human minutes | maths built, no sets yet |

The only fixed corpus is layer 3, and it is not an evaluation set. It answers one question: does
this judge agree with a person often enough to be believed. Once a judge passes that gate it scores
unlimited output, so the human cost stays flat while coverage grows.

The integration point is an **OpenAI-compatible chat completions endpoint** and nothing else. No
weights, no training code, no logs. That keeps the harness runnable against any hosted model by
anyone, including against a provider's own model without that provider's cooperation.

## Try layer 1 now

It needs no endpoint, no key and no budget.

```bash
pip install -e ".[dev]"

echo "Beste klant, u kunt uw bestelling annuleren. Laten we erin duiken, dan weet jij precies waar je aan toe bent." \
  | meetlat zeef
```

```text
⬢ meetlat · zeef  stdin
  ✘ register_consistency    4 findings
      1:14  'u' is formal, and this response uses both.
        Beste klant, u kunt uw bestelling annu…
                     ^
      1:21  'uw' is formal, and this response uses both.
        Beste klant, u kunt uw bestelling annuleren. L…
                            ^^
      1:77  'jij' is informal, and this response uses both.
        …e erin duiken, dan weet jij precies waar je aan toe…
                                 ^^^
      1:94  'je' is informal, and this response uses both.
        …n weet jij precies waar je aan toe bent.
                                 ^^
  ✘ translationese          1 finding
      1:46  'Laten we erin duiken' reads as translated English rather than written Dutch.
        …w bestelling annuleren. Laten we erin duiken, dan weet jij precies w…
                                 ^^^^^^^^^^^^^^^^^^^^
  ✔ meta_commentary
  ✔ self_repetition
  ◦ sentence_length         sentences 2  words 20  mean 10  median 10  p90 13  max 13
  ◦ anglicism_density       words 20  anglicisms 0  distinct 0  per_1000 0
  ◦ spelling                words 20  out_of_vocabulary 0  distinct 0  per_1000 0

  ✘ zeef failed · 2 of 7 checks · 5 findings
```

`meetlat zeef --json` for the machine-readable form, and `meetlat checks` for what is registered. The command exits non-zero when a verdict check fires, so
it composes into a pipeline.

## What layer 1 checks

Every finding names the span it fired on, so a failing score is debuggable rather than
discouraging.

| Check | Kind | Catches |
| --- | --- | --- |
| `register_consistency` | verdict | `je`/`jij`/`jouw` mixed with `u`/`uw` in one response |
| `translationese` | verdict | Calques: "laten we erin duiken", "ik hoop dat dit helpt" |
| `meta_commentary` | verdict | "Als AI-model kan ik…" and its relatives |
| `self_repetition` | verdict | An eight-word sequence repeated verbatim |
| `sentence_length` | distribution | Style drift between checkpoints. Reports numbers, never a verdict |
| `anglicism_density` | distribution | English where an ordinary Dutch word exists, as a rate per 1000 words |
| `spelling` | distribution | Words outside the OpenTaal list, compounds decomposed first, as a rate per 1000 |

Two design rules make this layer worth running. **A check either has no false positives or it
reports a distribution rather than a verdict**, because a checker that cries wolf gets switched
off. And **coverage never wins over certainty**: `de`/`het` agreement, clause word order and
invented compounds are deliberately excluded, and `spelling` reports a rate rather than a verdict
for the same reason (ADR-0008). All seven designed checks are built; `meetlat checks` shows what
is registered.

CI enforces it: every verdict check runs over a corpus of natural Dutch written by a person, and a
single firing there fails the build.

## What it does not measure

Stated plainly so nobody quotes it as if it did.

- **Factual accuracy about the world.** Faithfulness scoring checks a response against context
  supplied in the prompt. It says nothing about claims made without context. Knowledge belongs to
  EuroEval and nl-eval.
- **Grammar and spelling as a competence score.** Layer 1 flags defects in generated text; it is
  not a substitute for nl-eval's grammar battery.
- **Safety, bias and refusal behaviour.** A separate axis with a separate method.
- **Anything about real user traffic.** Generated prompts stand in for it, imperfectly and by
  design.

And where it can mislead: a judge built on one model family may favour output from that family;
layer 1 thresholds are tunable, which means they are gameable, so publish them with the scores; and
comparative numbers across checkpoints are far more reliable than absolute ones. A pass rate of
0.78 means little on its own. A move from 0.71 to 0.78 on a calibrated judge over a regenerated
prompt set means something.

## Status

Layer 1 is usable. **Nothing is calibrated yet**, so this repository currently publishes no pass
rates at all, which is the honest state for a project whose central claim is that uncalibrated
numbers are not measurements. Build order and progress: [`AGENTS.md`](AGENTS.md).

## Contributing

```bash
make install        # .venv plus dev tools
make install-hooks  # pre-commit gates lint and the offline gates; pre-push runs preflight
make preflight      # everything CI runs
make help           # every target
```

Read [`CONTEXT.md`](CONTEXT.md) for the vocabulary and [`AGENTS.md`](AGENTS.md) for the rules that
bind. Every decision and the reasoning behind it is in [`docs/adr/`](docs/adr/README.md), starting
at ADR-0001.

Two things are worth knowing before you open a PR. A new layer 1 check needs a fixture with the
exact text of every span it produces, plus clean Dutch added to the corpus in the register it
touches. And anything under `gold/` is hand-labelled by two people: it is the instrument everything
else is measured against, it is never generated, and a `PreToolUse` hook refuses writes to `gold/*.jsonl`.

## Licence

The repository is two different kinds of thing, so it carries two licences.

| Part | Licence | |
| --- | --- | --- |
| Code: the checks, the judge harness, the runner | **Apache 2.0** | [LICENSE](LICENSE) |
| Data: hand labels, the taxonomy, the wordlists authored here, the Dutch corpus | **CC BY 4.0** | [LICENSE-DATA](LICENSE-DATA) |

A software licence is written about source code, derivative works and patents, and none
of those land cleanly on a file of 200 sentences a person labelled by hand. Apache 2.0
gives the code an explicit patent grant and a NOTICE mechanism for third-party
attribution; CC BY keeps a name attached to the part that cost human hours.

Vendored wordlists keep their own licence and are recorded in [NOTICE](NOTICE). The
OpenTaal list the `spelling` check uses is dual-licensed BSD-3-Clause or
CC BY 3.0, and this project takes the BSD arm, which sits cleanly beside Apache 2.0
code. `make check-zeef` fails if a vendored list is not named in NOTICE, so attribution
is enforced rather than remembered.
