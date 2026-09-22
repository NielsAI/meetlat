"""The collector's licence reading, which is what keeps unredistributable text out.

An indexed source is trusted for nothing except where to look. Everything that decides
whether a paragraph may be committed is read from the page it came from, so these are
the tests for that reading rather than for the fetching around it.
"""

from __future__ import annotations

import collect_corpus

CC_BY_4 = '<a href="https://creativecommons.org/licenses/by/4.0/deed.nl">licentie</a>'
PAGE = """
<html><body>
  <div class="content arrangement-body">
    <p>Je wordt wakker en pakt als eerste je telefoon om je berichten te bekijken.
       Daarna zoek je op internet of je het antwoord op je vraag kunt vinden.</p>
    <p>Kort.</p>
  </div>
  <div class="colofon">
    <p>Dit lesmateriaal is gepubliceerd onder de Creative Commons Naamsvermelding 4.0
       Internationale licentie, wat betekent dat je het mag delen en bewerken.</p>
  </div>
</body></html>
"""


def test_the_page_licence_is_read_from_the_licence_url() -> None:
    assert collect_corpus.page_licence(CC_BY_4) == "CC-BY-4.0"


def test_a_translated_deed_is_the_same_licence_not_a_port() -> None:
    """`by/4.0/deed.nl` is the Dutch reading of CC BY 4.0; `by/3.0/nl/` is another licence."""
    both = "http://creativecommons.org/licenses/by/4.0/ and /licenses/by/4.0/deed.nl"
    assert collect_corpus.page_licence(both) == "CC-BY-4.0"
    assert collect_corpus.page_licence("https://creativecommons.org/licenses/by/3.0/nl/") == (
        "CC-BY-3.0-NL"
    )


def test_share_alike_is_read_as_itself_and_so_never_matches() -> None:
    """The collector compares against the source's licence; it does not classify families."""
    page = "https://creativecommons.org/licenses/by-sa/4.0/"
    assert collect_corpus.page_licence(page) == "CC-BY-SA-4.0"
    assert collect_corpus.page_licence(page) != collect_corpus.SEARCH_SOURCES[0].licence


def test_a_page_declaring_nothing_is_not_treated_as_permissive() -> None:
    assert collect_corpus.page_licence("<html><p>Geen licentie hier.</p></html>") is None


def test_a_page_declaring_two_licences_is_refused_rather_than_reconciled() -> None:
    """Which licence covers which paragraph is not answerable from the page."""
    page = CC_BY_4 + '<a href="https://creativecommons.org/licenses/by-nc/4.0/">nc</a>'
    assert collect_corpus.page_licence(page) is None


def test_extraction_is_scoped_so_the_licence_footer_is_not_collected() -> None:
    """The footer is prose, it is on every page, and it is not Dutch anyone wrote to read."""
    scoped = collect_corpus.paragraphs_from(PAGE, within="arrangement-body")
    assert len(scoped) == 1
    assert scoped[0].startswith("Je wordt wakker")

    unscoped = collect_corpus.paragraphs_from(PAGE)
    assert any("Naamsvermelding" in paragraph for paragraph in unscoped)


INDEX_XML = """<?xml version="1.0"?>
<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/">
  <srw:record><czp:lom xmlns:czp="http://www.imsglobal.org/xsd/imsmd_v1p2">
    <czp:location>https://maken.wikiwijs.nl/1/Een</czp:location>
    <czp:location>https://maken.wikiwijs.nl/1/Een/thumbnail.png</czp:location>
    <czp:contribute>
      <czp:role><czp:value><czp:langstring>vdex_lifecycle.xmlauthor</czp:langstring></czp:value></czp:role>
      <czp:centity><czp:vcard>BEGIN:VCARD
FN:Anne de Vries
END:VCARD</czp:vcard></czp:centity>
      <czp:centity><czp:vcard>BEGIN:VCARD
FN:Joris Bakker
END:VCARD</czp:vcard></czp:centity>
    </czp:contribute>
    <czp:contribute>
      <czp:role><czp:value><czp:langstring>vdex_lifecycle.xmlpublisher</czp:langstring></czp:value></czp:role>
      <czp:centity><czp:vcard>BEGIN:VCARD
FN:Wikiwijs Maken
END:VCARD</czp:vcard></czp:centity>
    </czp:contribute>
  </czp:lom></srw:record>
  <srw:record><czp:lom xmlns:czp="http://www.imsglobal.org/xsd/imsmd_v1p2">
    <czp:location>urn:uuid:not-a-url</czp:location>
    <czp:location>https://maken.wikiwijs.nl/2/Twee</czp:location>
  </czp:lom></srw:record>
</srw:searchRetrieveResponse>
"""


def test_the_index_gives_one_page_per_record() -> None:
    assert [r.url for r in collect_corpus.index_records(INDEX_XML)] == [
        "https://maken.wikiwijs.nl/1/Een",
        "https://maken.wikiwijs.nl/2/Twee",
    ]


def test_only_contributors_in_the_author_role_are_credited() -> None:
    """CC BY asks for the creator. Hosting a lesson is not writing one."""
    records = collect_corpus.index_records(INDEX_XML)
    assert records[0].authors == ("Anne de Vries", "Joris Bakker")
    assert "Wikiwijs Maken" not in records[0].authors


def test_a_record_naming_no_author_carries_none_to_credit() -> None:
    """The collector skips these: an attribution licence with nobody to attribute is not usable."""
    assert collect_corpus.index_records(INDEX_XML)[1].authors == ()


def test_a_keyword_narrows_the_query_without_replacing_the_licence_filter() -> None:
    source = collect_corpus.SEARCH_SOURCES[0]
    url = collect_corpus.search_url(source, "burgerschap", start=1)
    assert "burgerschap+AND" in url
    assert "cc-by-40" in url
    assert "cc-by-40" in collect_corpus.search_url(source, "", start=1)


def test_every_searched_source_names_a_licence_the_corpus_accepts() -> None:
    """A source offering text under a licence the schema refuses is a run wasted."""
    from meetlat.zeef import corpus

    declared = [source.licence for source in collect_corpus.SEARCH_SOURCES]
    declared += [source.licence for source in collect_corpus.SOURCES]
    assert declared
    assert all(licence in corpus.REDISTRIBUTABLE for licence in declared)


def test_a_truncated_teaser_is_not_a_paragraph() -> None:
    """News index pages are full of these: the right length, prose-shaped, half a sentence."""
    teaser = (
        "<p>Vandaag worden het nieuwe paspoort en de nieuwe identiteitskaart in gebruik "
        "genomen. Deze modellen bevatten een aantal nieuwe ...</p>"
    )
    whole = (
        "<p>Vandaag worden het nieuwe paspoort en de nieuwe identiteitskaart in gebruik "
        "genomen. Deze modellen bevatten een aantal nieuwe echtheidskenmerken.</p>"
    )
    assert collect_corpus.paragraphs_from(teaser) == []
    assert len(collect_corpus.paragraphs_from(whole)) == 1


def test_a_listing_teaser_is_not_collected_as_a_paragraph() -> None:
    """A news card is a complete sentence about an article, living nowhere but the listing.

    It passes the length floor and the truncation guard, so nothing else catches it, and
    the text it would be cited for is not at the url that would be recorded. Thirty such
    paragraphs reached the corpus before this existed.
    """
    html = """
    <div class="griditem">
      <h3><a href="/nieuws/peppol/">Tijdkaarten via Peppol</a></h3>
      <p class="meta">Gepubliceerd op 1 mei 2026</p>
      <p class="excerpt">De overheid verzendt tijdkaarten van uitzendkrachten nu elektronisch
      via het Peppol-netwerk. Dat zorgt voor een betrouwbaar en gestandaardiseerd proces.</p>
    </div>
    <p>De overheid verzendt tijdkaarten van uitzendkrachten voortaan elektronisch via het
    Peppol netwerk. Dat maakt het proces betrouwbaar, veilig en volledig gestandaardiseerd.</p>
    """
    kept = collect_corpus.paragraphs_from(html)
    assert len(kept) == 1
    assert kept[0].startswith("De overheid verzendt tijdkaarten van uitzendkrachten voortaan")
    assert not any("Gepubliceerd op" in p for p in kept)


def test_an_ordinary_paragraph_with_a_class_is_still_collected() -> None:
    """The filter names the classes that mark a summary, rather than refusing every class."""
    html = '<p class="intro">Een standaard is een afspraak die is vastgelegd in een document, en die ICT-systemen allebei moeten hanteren om gegevens uit te wisselen.</p>'
    assert len(collect_corpus.paragraphs_from(html)) == 1
