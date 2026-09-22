#!/usr/bin/env python3
"""Collect the documents that document tasks hand to the model (ADR-0005).

Separate from `tests/corpora/clean_nl.jsonl` on purpose, and the reason is the whole
design. That corpus is *selected* for the property that no layer 1 check fires on it. Use
it as the input to a rewrite or a summarise and a model that copies its input scores
perfectly on layer 1, in the layer that runs on every response. The false-positive gate
and the evaluation input have to be disjoint or the cheapest layer flatters the laziest
behaviour.

So this reads the same declared sources as `collect_corpus.py`, under the same licences,
and writes somewhere else, refusing anything already in the corpus.

    python3 scripts/collect_contexts.py --source nvwa
    python3 scripts/collect_contexts.py --all

**The domain tag here is assigned by rule, not by a person**, which is the one place this
differs from the corpus and is deliberate. ADR-0007 puts the corpus's tags on a person
because the corpus is evidence; a context document is an *input*, so a wrong tag costs a
prompt about food safety being filed under `technical` rather than making a measurement
wrong. The rules are in `_DOMAIN_BY_PATH` where they can be read and argued with.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import collect_corpus as cc  # noqa: E402  (needs the sys.path lines above)

from meetlat import console  # noqa: E402
from meetlat.taxonomy.generate import ContextDocument  # noqa: E402
from meetlat.zeef import corpus  # noqa: E402

#: How many consecutive paragraphs make one document. A single paragraph is too thin to
#: summarise and too thin to extract three fields from; past four the task stops being
#: about writing and starts being about context length, which is a different measurement.
PARAGRAPHS_PER_DOCUMENT = 3

#: Which domain a page belongs to, by the first path fragment that matches. Ordered, so
#: a more specific rule can precede a broader one for the same host.
_DOMAIN_BY_PATH: tuple[tuple[str, str], ...] = (
    ("regelhulp.nl", "care"),
    ("nvwa.nl/onderwerpen/productveiligheid", "commercial"),
    ("nvwa.nl/onderwerpen/roken-drinken", "commercial"),
    ("nvwa.nl/onderwerpen/voedselveiligheid", "everyday"),
    ("nvwa.nl/onderwerpen/dier", "everyday"),
    ("nvwa.nl/onderwerpen/plant", "everyday"),
    ("digitaleoverheid.nl", "technical"),
    ("maken.wikiwijs.nl", "education"),
    ("cbs.nl", "commercial"),
    ("belastingdienst.nl", "administrative"),
    ("rijksoverheid.nl", "administrative"),
    # gov.uk, in English, for the translate task. Its paths are one topic each, so the
    # rules are per page rather than per section.
    ("gov.uk/accepting-returns", "commercial"),
    ("gov.uk/consumer-protection-rights", "commercial"),
    ("gov.uk/online-and-distance-selling", "commercial"),
    ("gov.uk/product-safety", "commercial"),
    ("gov.uk/food-safety", "everyday"),
    ("gov.uk/guidance/food-labelling", "everyday"),
    ("gov.uk/taking-a-pet-abroad", "everyday"),
    ("gov.uk/report-dead-animal", "everyday"),
    ("gov.uk/council-housing", "administrative"),
    ("gov.uk/housing-benefit", "administrative"),
    ("gov.uk/apply-for-council-tax-discount", "administrative"),
    ("gov.uk/complain-about-your-council", "administrative"),
    ("gov.uk/carers-allowance", "care"),
    ("gov.uk/apply-needs-assessment-social-services", "care"),
    ("gov.uk/attendance-allowance", "care"),
    ("gov.uk/help-with-health-costs", "care"),
    ("gov.uk/school-attendance-absence", "education"),
    ("gov.uk/complain-about-school", "education"),
    ("gov.uk/types-of-school", "education"),
    ("gov.uk/further-education-courses", "education"),
    ("gov.uk/data-protection", "technical"),
    ("gov.uk/guidance/keeping-your-data-secure", "technical"),
    ("gov.uk/government/publications/cyber-essentials", "technical"),
)


#: Which indexed sources to walk, with the subject to ask for and the domain the
#: material is filed under. An index needs a keyword or it returns whatever is newest,
#: and `education` is reachable no other way: every fixed-url Dutch source is a
#: government site, and government sites write about schools rather than teaching.
_SEARCH_PLAN: tuple[tuple[str, str, str], ...] = (
    ("edurep", "burgerschap", "education"),
    ("edurep", "rekenen", "education"),
    ("edurep", "taalverzorging", "education"),
    ("edurep", "loopbaan", "education"),
)


def domain_of(url: str) -> str:
    """The domain this page's text is filed under, or empty if no rule matches."""
    return next((domain for fragment, domain in _DOMAIN_BY_PATH if fragment in url), "")


def documents_from(
    paragraphs: list[str], url: str, source: cc.Source, start: int
) -> list[dict[str, str]]:
    """Group consecutive paragraphs of one page into documents."""
    domain = domain_of(url)
    if not domain:
        return []
    made: list[dict[str, str]] = []
    for offset in range(0, len(paragraphs) - PARAGRAPHS_PER_DOCUMENT + 1, PARAGRAPHS_PER_DOCUMENT):
        chunk = paragraphs[offset : offset + PARAGRAPHS_PER_DOCUMENT]
        made.append(
            {
                "id": f"ctx-{start + len(made):04d}",
                "text": "\n\n".join(chunk),
                "domain": domain,
                "language": source.language,
                "source": source.name,
                "licence": source.licence,
                "author": source.author,
                "url": url,
            }
        )
    return made


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="one declared source from collect_corpus.py")
    parser.add_argument("--all", action="store_true", help="every declared fixed-url source")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "prompts" / "contexts.jsonl")
    args = parser.parse_args(argv)

    chosen = [s for s in cc.SOURCES if args.all or s.name == args.source]
    if not chosen:
        console.fail(f"no such source: {args.source!r}; `make corpus-sources` lists them")

    # Every paragraph already in the clean corpus is refused here, which is the rule this
    # file exists to enforce rather than a tidiness check.
    in_corpus = {entry.text for entry in corpus.load(_corpus_path())}

    console.banner("meetlat · contexts", ", ".join(s.name for s in chosen))
    made: list[dict[str, str]] = []
    for source in chosen:
        for url in cc.pages_of(source):
            try:
                fetched = cc.fetch(url)
            except Exception as exc:  # noqa: BLE001  (one bad page must not end the run)
                console.warn(f"{url}: {exc}")
                continue
            paragraphs = [
                p
                for p in cc.paragraphs_from(fetched.text, within=source.within)
                if cc.MIN_CHARS <= len(p) <= cc.MAX_CHARS and p not in in_corpus
            ]
            fresh = documents_from(paragraphs, fetched.url, source, len(made) + 1)
            made.extend(fresh)
            if fresh:
                console.ok(f"{len(fresh)} document(s) from {fetched.url}")

    if args.all:
        made.extend(_from_index(len(made) + 1))

    # Validated here rather than at read time, so a malformed document is caught while
    # the run that produced it is still on screen. After every source has contributed,
    # not before: the first version validated the fixed-url documents and then appended
    # the indexed ones, which wrote 37 documents nowhere.
    documents = [ContextDocument.model_validate(d) for d in made]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(d.model_dump_json() + "\n" for d in documents), encoding="utf-8")
    console.say()
    console.ok(f"{len(documents)} context document(s) written to {args.out.name}")
    console.note("none of them is in the clean corpus; that disjointness is the point")
    return 0


def _from_index(start: int) -> list[dict[str, str]]:
    """Documents from the indexed sources, grouped per page like the fixed-url ones.

    `collect_indexed` already refuses a page whose declared licence disagrees with the
    index and one the index cannot name an author for, and it already skips anything in
    the clean corpus, so this reuses it whole rather than restating those rules.
    """
    made: list[dict[str, str]] = []
    for name, keyword, domain in _SEARCH_PLAN:
        source = next((s for s in cc.SEARCH_SOURCES if s.name == name), None)
        if source is None:
            console.warn(f"no indexed source named {name!r}")
            continue
        candidates = cc.collect_indexed(source, limit=60, keyword=keyword)
        by_url: dict[str, list[str]] = {}
        authors: dict[str, str] = {}
        for candidate in candidates:
            url = str(candidate["url"])
            by_url.setdefault(url, []).append(str(candidate["text"]))
            authors[url] = str(candidate["author"])
        for url, paragraphs in by_url.items():
            for offset in range(
                0, len(paragraphs) - PARAGRAPHS_PER_DOCUMENT + 1, PARAGRAPHS_PER_DOCUMENT
            ):
                made.append(
                    {
                        "id": f"ctx-{start + len(made):04d}",
                        "text": "\n\n".join(paragraphs[offset : offset + PARAGRAPHS_PER_DOCUMENT]),
                        "domain": domain,
                        "language": "nl",
                        "source": source.host,
                        "licence": source.licence,
                        "author": authors[url],
                        "url": url,
                    }
                )
        console.ok(f"{len(made)} document(s) after {name}/{keyword}")
    return made


def _corpus_path() -> Path:
    return REPO_ROOT / "tests" / "corpora" / "clean_nl.jsonl"


if __name__ == "__main__":
    raise SystemExit(main())
