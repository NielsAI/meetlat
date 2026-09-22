---
status: accepted
area: [zeef]
date: 2026-09-22
supersedes: []
amends: []
rule: [AGENTS.md]
enforced_by: [scripts/check_zeef_contract.py]
---

# ADR 0008: Spelling is reported as a rate, and invented compounds are not detectable

## Status

Accepted (2026-09-22). Decides what the `spelling` check in `meetlat.zeef.PLANNED` can honestly
be, before it is built.

## Context

The architecture lists a spelling check catching "misspellings, invented compounds", checked
against the OpenTaal wordlist. Two facts about Dutch make that harder than it reads.

**Dutch forms compounds productively.** *Evaluatieharnas*, *woordenlijstcontrole* and
*kwaliteitsmeting* are correct Dutch and will never appear in any word list, however large. A flat
lookup flags every one of them, on every response, which is precisely the failure ADR-0002 exists
to prevent.

**Well-formed nonsense is indistinguishable from a valid compound.** This is the part that decides
the ADR. A decomposer that accepts *evaluatie* + *harnas* must also accept *evaluatie* +
*huisdier*, because both are two known words joined by a legal rule. No lexicon can separate them;
the difference is meaning, not form. **Invented compounds are therefore not detectable at layer 1
at all**, by a flat list, by a splitter, or by Hunspell, whose Dutch compounding rules are
permissive for exactly the same reason.

A third problem is smaller but fatal to a verdict. Out-of-vocabulary words in real generated text
are dominated by proper nouns: people, places, companies, product names. A response about a
business is full of them, and no wordlist will hold them.

### What was weighed

| Option | Catches | Why not |
|---|---|---|
| Flat OpenTaal list, lookup only | Typos | Fires on every productive compound. Unusable as a verdict |
| Flat list plus a compound splitter | Typos that do not decompose | Better, but proper nouns still fire, and it still cannot see invented compounds |
| Hunspell (or `spylls`, a pure-Python implementation, avoiding a native dependency) | Typos, with proper affix and compound handling | Same proper-noun problem, same blindness to well-formed nonsense. Buys accuracy on a thing that is still not a verdict |
| **Out-of-vocabulary rate as a distribution** | Nothing, by design. It measures | Loses the ability to say "this word is wrong" |

## Decision

**`spelling` is a distribution check reporting an out-of-vocabulary rate.** It reports numbers and
can never fail, like `sentence_length` and `anglicism_density` before it.

Decomposition is still worth implementing, but for a different purpose: a compound whose parts are
all known is **not** counted as out-of-vocabulary, so the rate measures something closer to real
misspelling instead of measuring how much Dutch compounds. The splitter improves the number; it
does not produce a verdict.

**The vendored list is OpenTaal's `wordlist.txt` under its BSD-3-Clause arm**, with the NOTICE
entry the licence gate already requires. It is stored compressed, because roughly four megabytes of
uncompressed word list in a wheel is a cost every installer pays for a check most will not run.

**Invented compounds are declared out of scope for layer 1**, in the same paragraph of the
documentation that excludes `de`/`het` agreement and clause word order. They are a meaning
judgement, so they belong to a layer 2 judge or nowhere.

## Consequences

The architecture document's claim that layer 1 catches invented compounds does not survive contact
with the language. Recording that here is the point of the ADR: it is a finding about the design,
not a shortfall in the implementation, and anyone who reads the architecture and expects that check
should find this.

Absolute out-of-vocabulary rates will be uninterpretable on their own, dominated by proper-noun
density and therefore by prompt domain. They are comparative between checkpoints over a regenerated
prompt set, which is what ADR-0005 already says about every number this project produces.

The baseline on the clean corpus must be published with the check, as `anglicism_density` does, so
a reader knows what the rate is on Dutch known to be correct.
