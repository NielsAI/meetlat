"""The review tool's judgements about what may be accepted, not its keystroke loop.

What matters here is that a paragraph a verdict check fires on can never be accepted,
because the corpus is the thing that says a check which fired was wrong to, and one
false entry in it turns the gate into an argument in its own favour.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import review_corpus
from pydantic import ValidationError

from meetlat import console
from meetlat.zeef import corpus
from meetlat.zeef.checks import register_consistency

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


def test_a_menu_can_be_left_without_changing_the_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opening the menu must never be able to cost you the tag you already had."""
    monkeypatch.setattr(review_corpus, "_read_key", lambda: "b")
    kept = review_corpus.pick("register", list(review_corpus.REGISTERS), "business")
    assert kept == "business"


def test_backing_out_of_a_reason_chooses_no_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reject menu has no current value, so `b` leaves the candidate undecided."""
    monkeypatch.setattr(review_corpus, "_read_key", lambda: "b")
    assert review_corpus.pick("why", ["not natural Dutch", "wrong register"], "") == ""


def test_accepting_an_untagged_candidate_asks_instead_of_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A collector batch arrives with TODO in both tags; pressing accept used to traceback."""
    monkeypatch.setattr(review_corpus, "_read_key", lambda: "1")
    candidate: dict[str, object] = {"text": CLEAN, "register": "TODO", "domain": "TODO"}
    assert review_corpus._choose_missing(candidate) is True
    assert candidate["register"] == review_corpus.REGISTERS[0]
    assert candidate["domain"] == review_corpus.DOMAINS[0]
    corpus.CorpusEntry.model_validate(
        {**candidate, "id": "nl-0001", "origin": "authored", "source": "x", "licence": "CC0-1.0"}
    )


def test_backing_out_of_the_tag_question_does_not_accept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`b` out of the forced picker leaves the candidate untagged and unwritten."""
    monkeypatch.setattr(review_corpus, "_read_key", lambda: "b")
    candidate: dict[str, object] = {"text": CLEAN, "register": "TODO", "domain": "TODO"}
    assert review_corpus._choose_missing(candidate) is False
    assert candidate["register"] == "TODO"


def test_a_tag_already_chosen_is_not_asked_for_again(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse() -> str:
        raise AssertionError("asked for a tag that was already set")

    monkeypatch.setattr(review_corpus, "_read_key", refuse)
    candidate: dict[str, object] = {"text": CLEAN, "register": "business", "domain": "technical"}
    assert review_corpus._choose_missing(candidate) is True


def test_an_unset_register_has_no_floor_to_report() -> None:
    """`0/25  25 more for TODO` was a progress report on a tag that does not exist."""
    unset = review_corpus._progress(0, review_corpus.UNSET)
    assert "TODO" not in unset
    assert "25" not in unset
    assert "no register chosen" in unset


def test_a_validation_error_becomes_one_actionable_line() -> None:
    with pytest.raises(ValidationError) as caught:
        corpus.CorpusEntry.model_validate(
            {
                "id": "nl-0001",
                "text": CLEAN,
                "register": "business",
                "domain": "technical",
                "origin": "collected",
                "source": "x",
                "licence": "CC-BY-SA-4.0",
            }
        )
    said = review_corpus._why_invalid(caught.value)
    assert "\n" not in said
    assert "CC-BY-SA-4.0" in said


def test_markers_name_the_three_families_apart() -> None:
    """Bare `je` is not informal evidence, and the reviewer has to be able to see that."""
    found = register_consistency.markers(
        "U kunt hier parkeren, al moet je wel eerst jouw kaartje kopen."
    )
    assert [(m.text, m.kind) for m in found] == [
        ("U", "formal"),
        ("je", "impersonal"),
        ("jouw", "informal"),
    ]


def test_markers_do_not_fire_where_the_letters_are_not_a_pronoun() -> None:
    """Same word-boundary rules as the verdict, because they share the patterns."""
    assert register_consistency.markers("De u-bocht in het beleid en de je-vorm.") == []
    assert register_consistency.markers("Utrecht en Jeroen zijn geen voornaamwoorden.") == []


def test_markers_locate_exactly_what_the_verdict_reports() -> None:
    """A reviewer shown different markers than the check acts on reads the wrong evidence."""
    text = "Beste klant, u kunt uw bestelling annuleren, dan weet jij waar je aan toe bent."
    reported = register_consistency.register_consistency.run(text).findings
    assert {(f.span.start, f.span.end) for f in reported} == {
        (m.start, m.end) for m in register_consistency.markers(text)
    }


def test_highlighting_never_changes_the_text_it_paints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reviewer judges this paragraph, so painting it must be purely additive."""
    monkeypatch.setattr(review_corpus, "C", console.Palette(bold="<b>", magenta="<m>", reset="<r>"))
    line = "Wanneer u een aanvraag indient, kunt u zelf kiezen hoe je de bijlagen aanlevert."
    painted = review_corpus._highlight(line)
    assert painted != line
    assert re.sub(r"<[bmr]>", "", painted) == line


def test_a_paragraph_with_no_markers_says_what_that_means() -> None:
    """The absence is evidence too: it rules out both addressed registers."""
    said = review_corpus._register_legend("Het bestuur heeft de contributie niet verhoogd.")
    assert "no register markers" in said


def test_the_legend_counts_each_family_without_needing_colour() -> None:
    said = review_corpus._register_legend(
        "U kunt hier parkeren, al moet je wel eerst uw kaartje kopen."
    )
    assert "formal u/uw 2" in said
    assert "bare je, may be impersonal 1" in said
    assert "informal jij/jouw" not in said


def _entry(text: str, entry_id: str = "nl-0001") -> corpus.CorpusEntry:
    return corpus.CorpusEntry.model_validate(
        {
            "id": entry_id,
            "text": text,
            "register": "formal_u",
            "domain": "administrative",
            "origin": "authored",
            "source": "Niels van Beuningen",
            "licence": "CC-BY-4.0",
        }
    )


def test_a_batch_resumes_where_the_last_session_stopped(tmp_path: Path) -> None:
    """Reviewing 60 of 100 and reopening used to start again at the first candidate."""
    batch = tmp_path / "b.jsonl"
    texts = [f"{CLEAN} Nummer {n}." for n in range(4)]
    batch.write_text(
        "\n".join(json.dumps({"text": t, "register": "formal_u"}) for t in texts) + "\n",
        encoding="utf-8",
    )
    review_corpus._reject(
        {"text": texts[1]}, "not natural Dutch", batch.with_suffix(".rejected.jsonl")
    )
    left = review_corpus.remaining(batch, [_entry(texts[0])])

    assert [row["text"] for row in left] == [texts[2], texts[3]]
    assert "2 left of 4" in review_corpus.describe(batch, [_entry(texts[0])])


def test_a_skipped_candidate_comes_back(tmp_path: Path) -> None:
    """`s` means not now, which is the whole difference between it and rejecting."""
    batch = tmp_path / "b.jsonl"
    batch.write_text(json.dumps({"text": CLEAN}) + "\n", encoding="utf-8")
    assert len(review_corpus.remaining(batch, [])) == 1


def test_a_fully_reviewed_batch_says_so_rather_than_listing_its_size(tmp_path: Path) -> None:
    batch = tmp_path / "b.jsonl"
    batch.write_text(json.dumps({"text": CLEAN}) + "\n", encoding="utf-8")
    assert review_corpus.describe(batch, [_entry(CLEAN)]).endswith("all reviewed")


def test_describe_without_a_corpus_still_reports_the_whole_batch(tmp_path: Path) -> None:
    """The listing is the only caller that knows the corpus; the rest must not break."""
    batch = tmp_path / "b.jsonl"
    batch.write_text(json.dumps({"text": CLEAN, "register": "business"}) + "\n", encoding="utf-8")
    assert "1 candidates" in review_corpus.describe(batch)
