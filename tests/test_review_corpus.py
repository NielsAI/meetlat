"""The review tool's judgements about what may be accepted, not its keystroke loop.

What matters here is that a paragraph a verdict check fires on can never be accepted,
because the corpus is the thing that says a check which fired was wrong to, and one
false entry in it turns the gate into an argument in its own favour.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
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


def test_undo_removes_the_last_accepted_paragraph(tmp_path: Path) -> None:
    """Accepting is an append, so undoing is dropping the last line."""
    path = tmp_path / "clean_nl.jsonl"
    path.write_text("// a comment line the corpus starts with\n", encoding="utf-8")
    for n in (1, 2):
        review_corpus.append(
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
            ),
            path,
        )

    assert review_corpus._undo(path) == "nl-0002"
    assert [e.id for e in corpus.load(path)] == ["nl-0001"]


def test_the_progress_bar_fills_and_stops_at_the_floor() -> None:
    assert review_corpus.bar(0, floor=25, width=10).count("▰") == 0
    assert review_corpus.bar(25, floor=25, width=10).count("▰") == 10
    assert review_corpus.bar(400, floor=25, width=10).count("▰") == 10


def test_a_batch_is_described_by_what_it_would_fill(tmp_path: Path) -> None:
    """Choosing between batches is choosing which register to spend the hour on."""
    batch = tmp_path / "b.jsonl"
    rows = [{"text": CLEAN, "register": r} for r in ("business", "business", "formal_u")]
    batch.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    described = review_corpus.describe(batch)
    assert "3 candidates" in described
    assert "2 business" in described


def test_the_tools_own_output_is_not_offered_back_as_input(tmp_path: Path) -> None:
    folder = tmp_path / "batches"
    folder.mkdir()
    (folder / "cbs.jsonl").write_text("{}\n", encoding="utf-8")
    (folder / "cbs.rejected.jsonl").write_text("{}\n", encoding="utf-8")
    assert [p.name for p in review_corpus.waiting(tmp_path)] == ["cbs.jsonl"]


def test_comment_lines_are_not_candidates(tmp_path: Path) -> None:
    batch = tmp_path / "b.jsonl"
    batch.write_text('// a note\n{"text": "x"}\n', encoding="utf-8")
    assert review_corpus.read_candidates(batch) == [{"text": "x"}]


def test_every_tag_a_reviewer_can_choose_says_what_it_means() -> None:
    """The picker shows these, so a tag without one is a blank line where the choice is made."""
    assert set(review_corpus.REGISTERS) <= set(corpus.REGISTER_MEANS)
    assert set(review_corpus.DOMAINS) <= set(corpus.DOMAIN_MEANS)
    for meaning in {**corpus.REGISTER_MEANS, **corpus.DOMAIN_MEANS}.values():
        assert meaning.means and meaning.like


def test_input_that_runs_out_stops_the_review_rather_than_spinning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A closed stdin used to loop forever, which is every under-answered scripted run."""
    monkeypatch.setattr(review_corpus, "_read_key", lambda: None)
    assert review_corpus.key({"y": "accept", "q": "quit"}) == "q"
    with pytest.raises(review_corpus.Stopped):
        review_corpus.key({"1": "one", "2": "two"})


def test_a_register_past_its_floor_says_so_where_it_changes_what_you_do() -> None:
    """`formal_u: 36 of 25` in the same grey as everything else is the fact you miss."""
    done = review_corpus._progress(36, "formal_u")
    assert "has its 25" in done
    assert "thinner register" in done

    todo = review_corpus._progress(6, "informal_je")
    assert "19 more for informal_je" in todo
