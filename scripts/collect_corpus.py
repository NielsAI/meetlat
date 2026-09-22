#!/usr/bin/env python3
"""Fetch candidate paragraphs for the clean corpus, with their provenance filled in.

Run by hand, never in CI: CI reads the committed corpus and touches no network. The
output is *candidates*, printed for review, not appended to the corpus. A paragraph
enters `tests/corpora/clean_nl.jsonl` when a person has read it and tagged its
register, because the register is the one field no heuristic gets right and the one
that decides whether the corpus is evidence (ADR-0007).

Only sources listed in `SOURCES` can be fetched, and each names the licence its text
arrives under. That list is the licensing decision, made once and reviewable, rather
than a judgement made per URL while scraping. Dutch Wikipedia is deliberately absent:
CC BY-SA is share-alike and would force this project's data licence to change.

    python3 scripts/collect_corpus.py --list
    python3 scripts/collect_corpus.py --source rijksoverheid --limit 20
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meetlat import console  # noqa: E402  (needs the sys.path line above)
from meetlat.zeef import corpus  # noqa: E402

#: Paragraphs shorter than this are headings, labels and navigation crumbs; longer
#: ones are usually two paragraphs an extractor failed to split.
MIN_CHARS = 80
MAX_CHARS = 400

USER_AGENT = "meetlat-corpus-collector (https://github.com/NielsAI/meetlat)"


@dataclass(frozen=True)
class Source:
    """A place text may be taken from, and the licence it arrives under."""

    name: str
    licence: str
    note: str
    urls: tuple[str, ...]


SOURCES: tuple[Source, ...] = (
    Source(
        name="rijksoverheid",
        licence="CC0-1.0",
        note=(
            "Dutch central government. CC0 1.0 per rijksoverheid.nl/copyright. Formal `u` "
            "register, administrative domain, so it cannot fill the informal registers."
        ),
        urls=(
            "https://www.rijksoverheid.nl/onderwerpen/paspoort-en-identiteitskaart",
            "https://www.rijksoverheid.nl/onderwerpen/huurwoning",
            "https://www.rijksoverheid.nl/onderwerpen/zorgverzekering",
            "https://www.rijksoverheid.nl/onderwerpen/verkeersveiligheid",
            "https://www.rijksoverheid.nl/onderwerpen/basisonderwijs",
        ),
    ),
)


class _Paragraphs(HTMLParser):
    """Text inside <p>, with tags and script/style dropped.

    A real extractor would be a dependency; this is deliberately crude because its
    output is reviewed by a person before anything is committed.
    """

    def __init__(self) -> None:
        super().__init__()
        self._depth = 0
        self._skip = 0
        self._buffer: list[str] = []
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in {"script", "style", "nav", "footer"}:
            self._skip += 1
        elif tag == "p":
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "footer"}:
            self._skip = max(0, self._skip - 1)
        elif tag == "p" and self._depth:
            self._depth -= 1
            text = re.sub(r"\s+", " ", "".join(self._buffer)).strip()
            self._buffer.clear()
            if text:
                self.paragraphs.append(text)

    def handle_data(self, data: str) -> None:
        if self._depth and not self._skip:
            self._buffer.append(data)


def fetch(url: str, *, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def paragraphs_from(html: str) -> list[str]:
    parser = _Paragraphs()
    parser.feed(html)
    return [p for p in parser.paragraphs if MIN_CHARS <= len(p) <= MAX_CHARS]


def existing_texts() -> set[str]:
    path = REPO_ROOT / "tests" / "corpora" / "clean_nl.jsonl"
    return {entry.text for entry in corpus.load(path)} if path.exists() else set()


def collect(source: Source, limit: int) -> list[dict[str, object]]:
    seen = existing_texts()
    today = date.today().isoformat()
    candidates: list[dict[str, object]] = []
    for url in source.urls:
        if len(candidates) >= limit:
            break
        try:
            found = paragraphs_from(fetch(url))
        except Exception as exc:
            console.warn(f"{url}: {exc}")
            continue
        console.note(f"{len(found)} usable paragraph(s) from {url}")
        for text in found:
            if len(candidates) >= limit:
                break
            if text in seen:
                continue
            seen.add(text)
            candidates.append(
                {
                    "id": "TODO-assign",
                    "text": text,
                    "register": "TODO",
                    "domain": "TODO",
                    "origin": "collected",
                    "source": source.name,
                    "licence": source.licence,
                    "url": url,
                    "retrieved": today,
                }
            )
    return candidates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="which declared source to fetch")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--list", action="store_true", help="show the declared sources")
    args = parser.parse_args(argv)

    if args.list or not args.source:
        console.banner("meetlat · corpus sources", f"{len(SOURCES)} declared")
        for source in SOURCES:
            console.ok(f"{source.name}  ({source.licence}, {len(source.urls)} urls)")
            console.line(source.note, indent=4)
        console.say()
        console.note("Dutch Wikipedia is excluded: CC BY-SA is share-alike (ADR-0007).")
        return 0

    matched = next((s for s in SOURCES if s.name == args.source), None)
    if matched is None:
        console.fail(f"unknown source {args.source!r}; see --list")
        return 1

    console.banner("meetlat · corpus candidates", matched.name)
    candidates = collect(matched, args.limit)
    console.say()
    for candidate in candidates:
        print(json.dumps(candidate, ensure_ascii=False))
    console.say()
    console.ok(f"{len(candidates)} candidate(s)")
    console.note("Review each, set id/register/domain, then append to the corpus by hand.")
    console.note("Nothing here is committed automatically: the register tag is the judgement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
