"""The review tool's judgements about what may be accepted, not its keystroke loop.

What matters here is that a paragraph a verdict check fires on can never be accepted,
because the corpus is the thing that says a check which fired was wrong to, and one
false entry in it turns the gate into an argument in its own favour.
"""

from __future__ import annotations

import json
from pathlib import Path

import review_corpus

from meetlat.zeef import corpus

CLEAN = "De gemeente stuurt binnen vijf werkdagen een bevestiging per e-mail aan de aanvrager."
FIRES = "Beste klant, u kunt uw bestelling annuleren, dan weet jij precies waar je aan toe bent."


def test_a_paragraph_a_verdict_check_fires_on_cannot_be_accepted() -> None:
    assessed = review_corpus.assess(FIRES, [])
    assert assessed.findings
    assert "verdict check fires" in assessed.blocked


def test_clean_dutch_is_not_blocked() -> None:
    assessed = review_corpus.assess(CLEAN, [])
    assert assessed.findings == []
    assert assessed.blocked == ""


def test_a_near_copy_of_something_already_in_the_corpus_is_blocked() -> None:
    """A monthly series republished with new figures is one piece of evidence, not two."""
    already = "De omzet van de detailhandel was in juli 3,5 procent hoger dan een jaar eerder."
    variant = "De omzet van de detailhandel was in juni 2,9 procent hoger dan een jaar eerder."
    assert review_corpus.assess(variant, [already]).blocked.startswith("it is a near-copy")


def test_the_paragraph_floor_is_reported_but_does_not_block() -> None:
    """Short entries are already in the corpus; the reviewer says so rather than refusing."""
    assessed = review_corpus.assess("Kort bericht van de gemeente.", [])
    assert assessed.below_floor
    assert assessed.blocked == ""


def test_the_next_id_comes_from_the_highest_used_not_the_count() -> None:
    """An id that has pointed at two paragraphs is worse than a gap in the sequence."""
    entries = [
        corpus.CorpusEntry.model_validate(
            {
                "id": f"nl-{n:04d}",
                "text": CLEAN,
                "register": "formal_u",
                "domain": "administrative",
                "origin": "authored",
                "source": "Niels van Beuningen",
                "licence": "CC-BY-4.0",
            }
        )
        for n in (1, 7)
    ]
    assert review_corpus.next_id(entries) == "nl-0008"
    assert review_corpus.next_id([]) == "nl-0001"


def test_the_thinnest_register_is_reviewed_first() -> None:
    """The exit condition is a floor per register, so the useful hour is spent there."""
    candidates: list[dict[str, object]] = [
        {"register": "formal_u"},
        {"register": "business"},
        {"register": "informal_je"},
    ]
    counts = {"formal_u": 9, "business": 5, "informal_je": 6}
    ordered = review_corpus.by_thinnest_register(candidates, counts)
    assert [c["register"] for c in ordered] == ["business", "informal_je", "formal_u"]


def test_an_accepted_entry_is_appended_as_the_corpus_can_read_it(tmp_path: Path) -> None:
    path = tmp_path / "clean_nl.jsonl"
    path.write_text("", encoding="utf-8")
    entry = corpus.CorpusEntry.model_validate(
        {
            "id": "nl-0001",
            "text": CLEAN,
            "register": "formal_u",
            "domain": "administrative",
            "origin": "collected",
            "source": "rijksoverheid",
            "licence": "CC0-1.0",
            "url": "https://www.rijksoverheid.nl/themas/onderwijs/basisonderwijs",
            "retrieved": "2026-09-22",
        }
    )
    review_corpus.append(entry, path)

    reloaded = corpus.load(path)
    assert [e.id for e in reloaded] == ["nl-0001"]
    assert json.loads(path.read_text(encoding="utf-8"))["retrieved"] == "2026-09-22"
