#!/usr/bin/env python3
"""Fetch candidate paragraphs for the clean corpus, with their provenance filled in.

Run by hand, never in CI: CI reads the committed corpus and touches no network. The
output is *candidates*, printed for review, not appended to the corpus. A paragraph
enters `tests/corpora/clean_nl.jsonl` when a person has read it and tagged its
register, because the register is the one field no heuristic gets right and the one
that decides whether the corpus is evidence (ADR-0007).

Only declared sources can be fetched, and each names the licence its text arrives
under. That list is the licensing decision, made once and reviewable, rather than a
judgement made per URL while scraping. Dutch Wikipedia is deliberately absent: CC BY-SA
is share-alike and would force this project's data licence to change.

There are two kinds. A `Source` is a fixed list of pages under one licence. A
`SearchSource` is an index that finds the pages, which is the only way to reach the
informal registers: CC0 Dutch is written by governments and governments write `u`.
An index repeats what an uploader typed, so its answer is treated as a lead and the
licence is read again from the page the text comes from. That re-read is not a second
opinion, because on a harvested index both readings trace back to the same uploader: it
catches a stale harvest and it refuses a page naming two licences, and no more than
that.

    python3 scripts/collect_corpus.py --list
    python3 scripts/collect_corpus.py --source rijksoverheid --limit 20
    python3 scripts/collect_corpus.py --source edurep --keyword burgerschap --limit 25
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meetlat import console  # noqa: E402  (needs the sys.path line above)
from meetlat.zeef import corpus  # noqa: E402

#: What counts as a paragraph is the corpus's definition, not the collector's, so the
#: floor a candidate is measured against is the one the gate reports the corpus against.
MIN_CHARS = corpus.MIN_CHARS
MAX_CHARS = corpus.MAX_CHARS

USER_AGENT = "meetlat-corpus-collector (https://github.com/NielsAI/meetlat)"

#: Records per index request. The Edurep endpoint refuses anything larger.
INDEX_PAGE = 100

#: A lesson page yields well under one usable paragraph, so a run reads a lot of them.
#: The cap is what stops a narrow keyword from walking the whole index in one go.
MAX_PAGES = 150

#: Seconds between page fetches. The index is public and free to use, and reading it
#: at full speed is the one reliable way to make it stop being either.
PAUSE = 0.5


@dataclass(frozen=True)
class Source:
    """A place text may be taken from, and the licence it arrives under."""

    name: str
    licence: str
    #: Who to credit. One publisher writes everything a fixed list of URLs points at,
    #: which is exactly why these are a fixed list and not a search.
    author: str
    note: str
    urls: tuple[str, ...]


@dataclass(frozen=True)
class SearchSource:
    """An index that finds the pages, each of which carries its own licence.

    The licence is filtered for in the query and then read again from the page, which is
    the whole difference from `Source`: there the licence is known before the fetch
    because a person put the URL in a list against terms a publisher states centrally,
    here it is a self-declaration by whoever uploaded the material, on a platform whose
    operator warrants nothing about it.
    """

    name: str
    licence: str
    note: str
    endpoint: str
    #: The query that restricts the index to language and licence, in the index's own
    #: syntax. A keyword from the operator is prepended to it, never substituted into it.
    cql: str
    #: The one host whose layout `within` describes. An index reaches many sites, and a
    #: paragraph taken from a layout this extractor does not know is as likely to be a
    #: navigation menu as a sentence.
    host: str
    #: The class of the element holding the material, so the page's own licence footer
    #: (which is prose, and is on every page) is not collected as Dutch.
    within: str


SOURCES: tuple[Source, ...] = (
    Source(
        name="rijksoverheid",
        licence="CC0-1.0",
        author="Rijksoverheid",
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
    Source(
        name="cbs",
        licence="CC-BY-4.0",
        author="Centraal Bureau voor de Statistiek",
        note=(
            "Statistics Netherlands. CC BY 4.0 per cbs.nl/nl-nl/over-ons/website/copyright, "
            "and CBS is both the publisher and the author it must be credited as. Economic prose "
            "addressed to nobody, which is the business register: the one the informal sources "
            "cannot reach and government `u` pages are not written in."
        ),
        urls=(
            "https://www.cbs.nl/nl-nl/nieuws/2026/36/detailhandel-zet-bijna-3-procent-meer-om-in-juli",
            "https://www.cbs.nl/nl-nl/nieuws/2026/09/omzet-detailhandel-3-5-procent-hoger-in-vierde-kwartaal",
            "https://www.cbs.nl/nl-nl/nieuws/2026/18/minder-vacatures-in-eerste-kwartaal-van-2026",
            "https://www.cbs.nl/nl-nl/nieuws/2026/31/economie-groeit-met-0-4-procent-in-tweede-kwartaal-2026",
            "https://www.cbs.nl/nl-nl/nieuws/2026/05/economie-groeit-in-vierde-kwartaal-2025-met-0-5-procent",
        ),
    ),
)

SEARCH_SOURCES: tuple[SearchSource, ...] = (
    SearchSource(
        name="edurep",
        licence="CC-BY-4.0",
        note=(
            "Open Dutch learning material, indexed by Kennisnet, searchable without a key. "
            "Written by teachers and by pupils, for pupils, and so addressed as `je`, which "
            "is the register no CC0 government source supplies. Material the uploader marked "
            "CC BY 4.0 only: a `cc-by-30` page links both the unported licence and the Dutch "
            "port CC-BY-3.0-NL, so two identifiers disagree and the page is refused anyway, "
            "and the `cc0-10` and `publicdomain` slices index video and third-party sites "
            "rather than pages with text on them."
        ),
        endpoint="https://wszoeken.edurep.kennisnet.nl/edurep/sruns",
        cql=("lom.general.language=nl AND lom.rights.copyrightandotherrestrictions=cc-by-40"),
        host="maken.wikiwijs.nl",
        within="arrangement-body",
    ),
)


class _Paragraphs(HTMLParser):
    """Text inside <p>, with tags and script/style dropped.

    A real extractor would be a dependency; this is deliberately crude because its
    output is reviewed by a person before anything is committed.

    `within` narrows collection to the elements carrying that class. Without it a page
    whose licence footer is written out in prose contributes that footer to the corpus,
    once per page, which `self_repetition` would then be measured against.
    """

    def __init__(self, within: str = "") -> None:
        super().__init__()
        self._within = within
        self._divs = 0
        self._scope: int | None = None
        self._depth = 0
        self._skip = 0
        self._buffer: list[str] = []
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "div":
            self._divs += 1
            if self._within and self._scope is None:
                classes = (dict(attrs).get("class") or "").split()
                if self._within in classes:
                    self._scope = self._divs
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
            if text and (not self._within or self._scope is not None):
                self.paragraphs.append(text)
        if tag == "div":
            if self._scope == self._divs:
                self._scope = None
            self._divs = max(0, self._divs - 1)

    def handle_data(self, data: str) -> None:
        if self._depth and not self._skip:
            self._buffer.append(data)


def fetch(url: str, *, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def paragraphs_from(html: str, *, within: str = "") -> list[str]:
    parser = _Paragraphs(within)
    parser.feed(html)
    return [p for p in parser.paragraphs if MIN_CHARS <= len(p) <= MAX_CHARS]


#: A Creative Commons licence URL, which every page using one links to. The port
#: segment is read because a ported licence is a different identifier: CC BY 3.0 NL
#: is not CC BY 3.0. `deed.nl` is a translation of the same licence, not a port, and
#: is not matched because it has no trailing slash to close the segment.
_CC_URL = re.compile(r"https?://creativecommons\.org/licenses/([a-z-]+)/(\d\.\d)(?:/([a-z]{2})/)?")


def page_licence(html: str) -> str | None:
    """The SPDX identifier the page itself declares, or None if it declares none.

    The page is the authority and the index is a lead. A page naming two licences is
    refused rather than reconciled: which of them covers which paragraph is not a
    question answerable from here, and guessing it wrong is how text nobody may
    redistribute ends up in a file that says everything in it is redistributable.
    """
    declared = {
        "-".join(part for part in ("CC", family.upper(), version, (port or "").upper()) if part)
        for family, version, port in _CC_URL.findall(html)
    }
    return declared.pop() if len(declared) == 1 else None


_SRW_RECORD = "{http://www.loc.gov/zing/srw/}record"
_LOM = "{http://www.imsglobal.org/xsd/imsmd_v1p2}"
_VCARD_NAME = re.compile(r"^FN:(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class IndexRecord:
    """One search result: where the material is, and who has to be credited for it."""

    url: str
    authors: tuple[str, ...]


def index_records(xml: str) -> list[IndexRecord]:
    """What each search result points at, and who the index says wrote it.

    A record can carry several locations, a thumbnail and a publisher page among them;
    the first that is a URL is the material. The authors are read because CC BY requires
    retaining identification of the creator, and a paragraph credited to the index it was
    found through is not attributed at all. Contributors in every other role are left
    out, the publisher included: hosting a lesson is not writing one.
    """
    found: list[IndexRecord] = []
    for record in ElementTree.fromstring(xml).iter(_SRW_RECORD):
        url = next(
            (
                text
                for location in record.iter(_LOM + "location")
                if (text := "".join(location.itertext()).strip()).startswith("http")
            ),
            "",
        )
        if not url:
            continue
        authors: list[str] = []
        for contribute in record.iter(_LOM + "contribute"):
            role = contribute.find(_LOM + "role")
            if role is None or not "".join(role.itertext()).strip().endswith("author"):
                continue
            for entity in contribute.iter(_LOM + "centity"):
                if name := _VCARD_NAME.search("".join(entity.itertext())):
                    authors.append(name.group(1).strip())
        found.append(IndexRecord(url, tuple(authors)))
    return found


def search_url(source: SearchSource, keyword: str, start: int) -> str:
    query = f"{keyword} AND {source.cql}" if keyword else source.cql
    parameters = {
        "operation": "searchRetrieve",
        "version": "1.2",
        "recordPacking": "xml",
        "maximumRecords": INDEX_PAGE,
        "startRecord": start,
        "query": query,
    }
    return f"{source.endpoint}?{urllib.parse.urlencode(parameters)}"


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
                    "author": source.author,
                    "licence": source.licence,
                    "url": url,
                    "retrieved": today,
                }
            )
    return candidates


def collect_indexed(source: SearchSource, limit: int, keyword: str) -> list[dict[str, object]]:
    seen = existing_texts()
    today = date.today().isoformat()
    candidates: list[dict[str, object]] = []
    # An index answers with the same material more than once, and a page fetched twice
    # is both a wasted request and a paragraph offered twice for review.
    visited: set[str] = set()
    read = 0
    start = 1
    while len(candidates) < limit and read < MAX_PAGES:
        try:
            records = index_records(fetch(search_url(source, keyword, start)))
        except Exception as exc:
            console.warn(f"{source.name}: {exc}")
            break
        if not records:
            break
        start += INDEX_PAGE
        for record in records:
            url = record.url
            if len(candidates) >= limit or read >= MAX_PAGES:
                break
            if urllib.parse.urlsplit(url).hostname != source.host or url in visited:
                continue
            visited.add(url)
            time.sleep(PAUSE)
            read += 1
            try:
                html = fetch(url)
            except Exception as exc:
                console.warn(f"{url}: {exc}")
                continue
            declared = page_licence(html)
            if declared != source.licence:
                console.skip(url, f"page declares {declared or 'no licence'}")
                continue
            # CC BY is conditional on naming the creator, so a page the index cannot
            # name an author for cannot be used, however clean its licence looks.
            if not record.authors:
                console.skip(url, "the index names no author, so it cannot be credited")
                continue
            found = paragraphs_from(html, within=source.within)
            if found:
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
                        "source": source.host,
                        "author": ", ".join(record.authors),
                        "licence": source.licence,
                        "url": url,
                        "retrieved": today,
                    }
                )
    console.say()
    console.stat(f"{read} page(s) read, {len(candidates)} candidate(s) kept")
    return candidates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="which declared source to fetch")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--keyword", default="", help="narrow a searched source to a subject")
    parser.add_argument("--list", action="store_true", help="show the declared sources")
    args = parser.parse_args(argv)

    declared = len(SOURCES) + len(SEARCH_SOURCES)
    if args.list or not args.source:
        console.banner("meetlat · corpus sources", f"{declared} declared")
        for source in SOURCES:
            console.ok(f"{source.name}  ({source.licence}, {len(source.urls)} urls)")
            console.line(source.note, indent=4)
        for indexed in SEARCH_SOURCES:
            console.ok(f"{indexed.name}  ({indexed.licence}, searches {indexed.host})")
            console.line(indexed.note, indent=4)
        console.say()
        console.note("Dutch Wikipedia is excluded: CC BY-SA is share-alike (ADR-0007).")
        return 0

    matched = next((s for s in SOURCES if s.name == args.source), None)
    searched = next((s for s in SEARCH_SOURCES if s.name == args.source), None)
    if searched is not None:
        console.banner(
            "meetlat · corpus candidates", f"{searched.name}  {args.keyword or 'all subjects'}"
        )
        candidates = collect_indexed(searched, args.limit, args.keyword)
    elif matched is not None:
        console.banner("meetlat · corpus candidates", matched.name)
        candidates = collect(matched, args.limit)
    else:
        console.fail(f"unknown source {args.source!r}; see --list")
        return 1

    console.say()
    for candidate in candidates:
        print(json.dumps(candidate, ensure_ascii=False))
    console.say()
    console.ok(f"{len(candidates)} candidate(s)")
    console.note("Review each, set id/register/domain, then append to the corpus by hand.")
    console.note("Nothing here is committed automatically: the register tag is the judgement.")
    if searched is not None:
        console.warn(
            "Written by teachers and by pupils, so read for errors and not only for register: "
            "a paragraph here can be natural Dutch and still be wrong, and the corpus is what "
            "says a check that fired was wrong to."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
