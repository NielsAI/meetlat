---
status: accepted
area: [zeef, infra]
date: 2026-09-22
supersedes: []
amends: [2]
rule: [AGENTS.md]
enforced_by: [scripts/check_zeef_contract.py, src/meetlat/zeef/corpus.py]
---

# ADR 0007: The clean corpus carries provenance and a register, per paragraph

## Status

Accepted (2026-09-22). **Amends [ADR-0002](0002-a-check-is-a-verdict-or-a-distribution.md)**, which
named the clean corpus as the false-positive gate without saying what a corpus entry has to be.

## Context

ADR-0002 made a corpus of natural Dutch the thing that decides whether a verdict check ships. It
started as 28 hand-written lines in a text file, which was enough to build the gate against and is
not enough to be evidence. The build plan's exit condition for layer 1 is 200 paragraphs of
known-good Dutch prose with near-zero false positives; 28 sentences demonstrate only that those 28
sentences do not fire.

Growing it to 200 surfaces three problems the text file cannot answer.

**Where did a paragraph come from.** The corpus is redistributed with the repository. Text scraped
from a source whose licence is unrecorded is a licensing defect that is invisible until someone
asks, and by then it is in the git history.

**Which licence it arrives under.** The obvious source, Dutch Wikipedia, is CC BY-SA. Share-alike
conflicts with the CC BY 4.0 this project puts on its data, so the single largest body of
human-written Dutch on the internet is unusable here. `rijksoverheid.nl` is CC0 and is usable. That
distinction has to be recorded per paragraph, not assumed per corpus.

**Which register it is in.** The registers are not interchangeable for this purpose. A corpus
collected from CC0 government sources is entirely formal `u`, and `register_consistency` was
deliberately narrowed around the *informal* reading of bare `je`, which is where its false
positives would be. A corpus that looks large and covers one register is worse than a small one
that admits what it covers, because it reads as evidence and is not.

## Decision

The corpus is `tests/corpora/clean_nl.jsonl`, one JSON object per paragraph, validated by
`meetlat.zeef.corpus.CorpusEntry`. Every entry declares:

- `text`: the paragraph, as written by a person
- `source`, `url`, `retrieved`: where it came from, resolvable by a reader
- `licence`: an SPDX identifier, which must be one the project may redistribute under CC BY 4.0
- `register` and `domain`: from the **same axes as the prompt taxonomy** in ADR-0005, so the
  corpus and the generated prompts describe coverage in one vocabulary

**No model-generated text, ever.** The corpus exists to prove the checks do not fire on human
Dutch. Filling it with model output makes it circular, and `translationese`, `meta_commentary` and
`naturalness` are exactly the properties that would be flattered. An agent may *collect* human
text; it may not author it. `origin: authored` is reserved for text a named person wrote.

**Coverage is reported, not asserted.** `make check-zeef` prints the paragraph count per register,
and an empty register is named in the output. This is the same reasoning as `meetlat.zeef.PLANNED`
and the taxonomy's empty cells: a gap nobody can see is a gap nobody fixes.

## Consequences

The gate gets slower to satisfy, deliberately. Adding a paragraph now means recording where it came
from, which is friction exactly where friction is wanted.

`scripts/collect_corpus.py` fetches from a declared source list and writes candidates with their
provenance filled in. It is run by hand and never in CI: CI reads the committed corpus and touches
no network.

The informal registers remain the hard part, and this ADR does not solve them. CC0 Dutch is
overwhelmingly administrative, so `informal_je`, `commercial` and `everyday` will stay thin until
text is found or contributed under a compatible licence. The coverage report is what keeps that
visible rather than letting a 200-paragraph total imply a breadth it does not have.
