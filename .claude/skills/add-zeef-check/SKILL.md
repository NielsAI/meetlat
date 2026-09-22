---
name: add-zeef-check
description: Add a deterministic check to the zeef (layer 1), or extend an existing wordlist, so it passes the contract gate. Use when the task is to catch a defect in generated Dutch without a model call, when building one of the checks listed in meetlat.zeef.PLANNED, or when a phrase should be added to the translationese or meta-commentary lists. Not for judges, which need calibration instead.
---

# add-zeef-check

Layer 1 is the cheapest thing here and the easiest to ruin. One check that fires on correct Dutch
teaches everyone to ignore the whole layer, so the contract in ADR-0002 is strict and the gate
enforces it: `make check-zeef`.

Delegate to the `check-author` subagent when the check is a new module. Do it inline when it is a
phrase added to an existing list.

## The decision that comes first

**Verdict or distribution?** Ask whether there is Dutch, in any register, where the rule you are
about to write is wrong. If there is, you have three options, in order of preference:

1. Narrow the trigger until there is not. `register_consistency` does this: it ignores bare `je`,
   which has an impersonal reading, and fires only on a formal marker plus an unambiguous informal
   pronoun.
2. Make it a `distribution` check that reports a number and no verdict. `sentence_length` does
   this: no sentence length is wrong, so nothing is failed.
3. Do not write it. `de`/`het` agreement and clause word order are excluded for exactly this
   reason, and that exclusion is a decision, not an omission.

## Adding a phrase to a list

`src/meetlat/resources/translationese.txt` and `meta_commentary.txt`. The bar is: a Dutch writer
would not produce this unprompted in **any** register. Common in machine output is not enough.

A phrase you considered and rejected goes in that file's rejected block **with the reason**. That
block is why `"aan het einde van de dag"` does not get re-proposed every six months.

Then run `make check-zeef`: the clean corpus decides, not your judgement of the phrase.

## Adding a check module

`.claude/agents/check-author.md` holds the procedure in full. The short version: write the
docstring first, register it in `src/meetlat/zeef/__init__.py`, write `tests/fixtures/<name>.json`
with the exact text of every span, add clean Dutch to `tests/corpora/clean_nl.txt` in the register
you touched, and run `make preflight`.

## What "done" means

`make check-zeef` green, and the fixture containing at least one near-miss you deliberately
excluded. A check whose fixture holds only cases it catches cannot be told apart from one that is
too eager.
