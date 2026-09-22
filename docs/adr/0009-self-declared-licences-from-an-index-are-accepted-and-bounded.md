---
status: accepted
area: [zeef, infra]
date: 2026-09-22
supersedes: []
amends: [7]
rule: [AGENTS.md, scripts/collect_corpus.py]
enforced_by: [src/meetlat/zeef/corpus.py, scripts/check_zeef_contract.py]
---

# ADR 0009: A self-declared licence from an index is accepted, and the risk stays here

## Status

Accepted (2026-09-22). **Amends [ADR-0007](0007-the-corpus-carries-provenance-and-register.md)**,
which requires every corpus entry to carry a redistributable licence and a resolvable url but does
not distinguish a licence a publisher states centrally from a licence an individual uploader
attaches to their own page.

## Context

ADR-0007 opened the corpus to CC0 and CC BY sources and named `rijksoverheid.nl` and `cbs.nl` as
the first two: a government and a statistics office, each stating one licence for the whole
domain, read once and trusted for every page under it. `SEARCH_SOURCES` in
`scripts/collect_corpus.py` adds a third kind, reached through an index rather than a fixed list,
and it does not carry the same warranty.

`edurep`, that entry, is Kennisnet's index of open Dutch learning material. It resolves to pages
on `maken.wikiwijs.nl`, and it is the only source declared so far that can supply the informal `je`
register no CC0 government page is written in, because it is written by teachers and, on at least
one sampled page, by pupils, for pupils.

A licence audit of this source, checking what it actually grants rather than what the index
implies, established three things:

**The index and the page are not two opinions.** Edurep harvests its records from Wikiwijs, so the
`lom.rights.copyrightandotherrestrictions` value the search query filters on and the licence block
rendered on the page are the same uploader-set field, read twice from the same origin.
`page_licence()` in `scripts/collect_corpus.py` re-reads the page before anything is kept, and that
re-read is real: it catches a harvest that has gone stale and it refuses a page whose licence block
names two identifiers at once, which happens where a CC BY 3.0 link sits beside its Dutch port. It
is not independent verification, because there is no second party in the chain to disagree with
the first.

**The only warranty is the uploader's.** Wikiwijs's Eindgebruikersvoorwaarden, art. 11.4, says
material is made available under CC BY or CC BY-SA unless stated otherwise; art. 11.5 says
Kennisnet is not responsible for content placed by end users or third parties. What stands behind
the CC BY 4.0 mark on a page is a checkbox the uploader ticked on publication, asserting the
material is theirs or that they have the author's permission. Nobody downstream checks that
assertion before the page goes live.

**The uploader is not always the kind of author a licence sample expects.** Wikiwijs material is
made by teachers building lesson pages, and in at least one page sampled during the audit, by a
pupil. A CC BY 4.0 mark on a page like that carries the same legal weight as one on a government
publication; it does not carry the same likelihood that whoever ticked the box understood what
they were granting.

None of this makes the licence false. It means the licence is asserted once, by one person, with
nobody else's name behind it, which is a different risk than reading a domain's own copyright
page.

## Decision

**This project accepts CC BY 4.0 material reached this way**, self-declared by an uploader on
`maken.wikiwijs.nl` and found through the Edurep index, as a source for the corpus. Refusing it
would leave the informal register empty in a corpus that exists specifically to test
`register_consistency` where its false positives would be (ADR-0007), and no CC0 or centrally
licensed source found so far writes in that register.

**The risk of a wrong or withdrawn declaration is accepted, and it is accepted here, not passed
on.** Kennisnet warrants nothing about what an end user uploads, and this project is choosing to
redistribute that upload anyway. If a declaration turns out to be wrong, the exposure is this
project's, not the platform's.

**The risk is bounded, not left open.** Every entry already carries a licence, a `url` and a
`retrieved` date (ADR-0007); a wrong or withdrawn declaration is a one-line removal once found,
against a corpus of paragraphs rather than a shipped model. `scripts/collect_corpus.py` re-reads
the licence at the page rather than trusting the index alone, and refuses a page naming two
licences instead of guessing which paragraph each covers.

**An entry from a self-declared source must name the creator, not only the platform.** CC BY 4.0
§3(a)(1) requires retaining identification of the creator, and "maken.wikiwijs.nl" or "edurep"
identifies neither: those name the platform and the index, not the person the licence attributes
the work to. `CorpusEntry` therefore carries `author` beside `source`, `source` says where the
text was found and `author` says who wrote it, and the schema refuses a collected entry under an
attribution licence with no author. CC0 and public-domain entries may leave it empty, because
those licences waive the condition rather than because nobody bothered.

**Material the index cannot name an author for is not collected.** An attribution licence with
nobody to attribute cannot be honoured, so `collect_indexed()` skips the page rather than
offering a candidate whose credit line a reviewer would have to invent.

**This reasoning is not specific to Wikiwijs.** It applies to every `SearchSource` in
`scripts/collect_corpus.py`, present or future: an index is a harvested copy of a licence someone
else declared, never a second opinion, and a page reached through one is accepted on the same
terms as this one, or not added.

## Consequences

The corpus now carries paragraphs whose licence rests on a single, unverified assertion by a
private individual, which is a materially weaker guarantee than the two sources ADR-0007 opened
with. That is a cost of having the informal register at all, not an oversight; the alternative is
a corpus that reads as broad while covering one register, which ADR-0007 already names as worse
than a small honest one.

The creator-naming rule is enforced where it cannot be forgotten: `CorpusEntry` refuses a
collected entry under an attribution licence that names no author, so a committed entry missing
its credit fails `make check-zeef` rather than waiting for somebody to notice. What the schema
cannot check is whether the name is the right one. The index is again the only source for it, and
a wrong author on a wrongly declared licence is the same single assertion twice.

`scripts/collect_corpus.py`'s `page_licence()` re-read is the only automated check standing
between a stale or dual-licensed harvest and a candidate offered for review; it does not verify
that the uploader had the right to grant the licence in the first place, and nothing in this
project can. That residual is accepted, not closed.
