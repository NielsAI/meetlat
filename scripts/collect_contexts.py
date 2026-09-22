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
                for p in cc.paragraphs_from(fetched.text)
                if cc.MIN_CHARS <= len(p) <= cc.MAX_CHARS and p not in in_corpus
            ]
            fresh = documents_from(paragraphs, fetched.url, source, len(made) + 1)
            made.extend(fresh)
            if fresh:
                console.ok(f"{len(fresh)} document(s) from {fetched.url}")

    # Validated here rather than at read time, so a malformed document is caught while
    # the run that produced it is still on screen.
    documents = [ContextDocument.model_validate(d) for d in made]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(d.model_dump_json() + "\n" for d in documents), encoding="utf-8")
    console.say()
    console.ok(f"{len(documents)} context document(s) written to {args.out.name}")
    console.note("none of them is in the clean corpus; that disjointness is the point")
    return 0


def _corpus_path() -> Path:
    return REPO_ROOT / "tests" / "corpora" / "clean_nl.jsonl"


if __name__ == "__main__":
    raise SystemExit(main())
