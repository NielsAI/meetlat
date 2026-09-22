# AGENTS.md

Canonical orientation for anyone, human or agent, working in this repository. Read by
Claude Code via `CLAUDE.md`, and natively by other AGENTS.md-aware tools. Keep it under
~150 lines: detail lives in the linked documents.

## What this is

A harness for measuring the quality of free-form **Dutch** text produced by language models, and
for making the automated judges that do the measuring trustworthy enough to act on.

The argument the whole repository rests on: **an uncalibrated judge is not a measurement.** A
quality claim measured on a few dozen prompts by an uncalibrated judge cannot distinguish a real
improvement from noise, whatever the number says. If you are about to make this repository produce
a number, that number has to survive that sentence.

Full reasoning lives in [`docs/adr/`](docs/adr/README.md), one decision per file. ADR-0001 is the
founding one and the rest refine it; nothing else in this repository is a design document, so there
is nothing to drift from.

## The three layers

Each is cheaper to run and less trustworthy than the one below it. They carry Dutch names because
they are this project's own vocabulary; everything else in the code is English (ADR-0001).

| Layer | Package | What it is | Cost per item | State |
| --- | --- | --- | --- | --- |
| 1 | `meetlat.zeef` | Deterministic checks, no model call | zero | **built**, 7 checks |
| 2 | `meetlat.keuring` | Calibrated binary judges, one criterion each | one model call per criterion | card + gate built, runner not |
| 3 | `meetlat.ijk` | Hand labels that certify a layer-2 judge | human minutes | maths + gate built, no sets yet |

Nothing is calibrated yet. **No pass rate from this repository means anything until a judge card
exists and passes `make check-judges`.** Do not write copy that implies otherwise.

## Where to put information

| You produced… | Put it in | Notes |
| --- | --- | --- |
| A decision or tradeoff | `docs/adr/NNNN-*.md` | Only if hard to reverse, contested, or cross-cutting. Otherwise it is a line in this file. Every ADR declares `rule:` or `enforced_by:` saying where it landed (ADR-0006). Use the `adr-author` agent, then `make adr-index` |
| A rule an agent must follow while editing | this file | Imperative, current, citing the ADR behind it |
| A new deterministic check | `src/meetlat/zeef/checks/` plus a fixture | The `/add-zeef-check` skill and the `check-author` agent |
| A phrase that marks translationese or meta-commentary | `src/meetlat/resources/*.txt` | Never inline in code. A rejected phrase goes in that file's rejected block with the reason |
| A judge prompt or card | `judges/<criterion>/v<n>/` | Versioned. A changed prompt is a new judge (ADR-0003) |
| Hand labels | `gold/<criterion>-v<n>.jsonl` | **By a person, never by an agent.** A fail-closed guard enforces it |
| A paragraph of clean Dutch | `tests/corpora/clean_nl.jsonl` | With its provenance, licence and register (ADR-0007). Collected by an agent, **never written by one**: that would make the false-positive gate circular. `scripts/collect_corpus.py` fetches candidates. Where the licence asks for credit, `author` names who wrote it and `source` only says where it was found (ADR-0009) |
| An explanation of why code is the way it is | a docstring in that code | Not a narration of the edit; the history covers that |
| Domain vocabulary | `CONTEXT.md` | Use its exact words everywhere |

## The rules that bind

**Layer 1: a check is a verdict or a distribution** (ADR-0002). A verdict check fires only where it
is certain and reports findings; a distribution check reports numbers and can never fail. Every
finding carries the span it fired on, validated against the response. A verdict check that fires
once on `tests/corpora/clean_nl.jsonl` does not ship. Where coverage and certainty conflict, choose
certainty: `de`/`het` agreement, clause word order and invented compounds are excluded for this
reason (ADR-0008 for the last).

**Layer 2: one criterion per judge, one binary verdict** (ADR-0003). No composite scores, no 1-to-5
scales. Every score is reported per interaction type; the aggregate is a footnote. A judge is a
versioned artifact with its model and temperature pinned and the sha256 of its calibrated prompt on
its card. **A judge whose prompt changed is a new judge** and re-enters the gate.

**Layer 3: a judge below threshold reports nothing** (ADR-0004). Kappa above 0.6 and balanced
accuracy above 0.85, recomputed by CI from the reconciled labels rather than trusted from the card.
Revising a prompt to meet a threshold is legitimate; revising a threshold to meet a judge is not.
The `/calibrate-judge` skill is the protocol.

**Prompts are generated from a taxonomy, not maintained** (ADR-0005). Not built yet.

**Enforcement is a `scripts/check_*.py` with three callers** (ADR-0006): a `make` target, a CI job,
and where instant feedback earns it, a hook. The hook is a caller, never the logic. Two kinds of
hook call the same scripts: `.githooks/` for a person using git, `.claude/hooks/` for an agent
using a tool.

**User-facing output goes through `meetlat.console`.** One palette, one set of glyphs, one voice,
and no escape sequence ever written into a pipe or a log. Do not hand-roll colour, and do not print
a status line without a glyph from that module. `bad` and `err` are not interchangeable: a failing
check is a result and goes to stdout; the run going wrong goes to stderr.

**Two licences, and which one applies depends on what you wrote** (`LICENSE`, `LICENSE-DATA`,
`NOTICE`). Code is Apache 2.0. Data is CC BY 4.0: hand labels, the taxonomy, the wordlists authored
here, and the Dutch corpus. A **vendored** wordlist keeps its own licence, declares it in an
`# SPDX-License-Identifier:` and `# Origin: vendored` header, and is named in `NOTICE`, which
`make check-zeef` enforces. Never relicense a vendored list by copying its contents into an
authored file.

**Comments explain a non-obvious why**, a workaround with its cause, or a subtle invariant. Never
what the line plainly does, never a narration of the edit.

## Commands

```bash
make install        # .venv plus the package and its dev tools
make install-hooks  # enable .githooks: commit-msg, pre-commit, pre-push
make help           # every target, generated from the Makefile itself

make zeef ARGS=response.txt   # run layer 1 over a file
make checks                   # what is registered, and what is designed but unbuilt

make check          # every offline gate (check-zeef, check-judges)
make corpus-sources # the declared sources the corpus may be collected from
make review ARGS=batch.jsonl  # review candidates and append the accepted ones
make preflight      # everything CI runs: lint, format, types, tests, gates
make adr-index      # regenerate docs/adr/README.md after adding an ADR

make test ARGS="-k agreement"   # filter
```

`make preflight` green means CI green: the workflow calls the same targets.

## Build order

Bottom up, because each layer is useful before the next exists (ADR-0001).

| Step | Output | Done |
| --- | --- | --- |
| 1 | Layer 1 as a package: checks, wordlists, fixtures, contract gate | ◐ all 7 checks built, but the corpus is 28 entries against an exit condition of 200 paragraphs, 17 of them below the 80-character floor for what counts as one |
| 2 | Taxonomy plus prompt generator | ✘ ADR-0005 records the decision; no code |
| 3 | A hand-labelled set for one criterion, two annotators | ✘ schema and guard exist, no labels |
| 4 | First calibrated judge plus the written protocol | ◐ protocol and gate exist, no judge |
| 5 | Runner: endpoint to prompts to layers 1 and 2 to report | ✘ |
| 6 | Remaining judges, each through the same gate | ✘ |

The protocol was written before the first judge on purpose: a judge built without knowing how it
will be validated tends to be built in a way that cannot be validated.

## Version control

Commits and pushes are the author's call. Leave work in the working tree and say what changed.
