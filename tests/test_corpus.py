"""What a corpus paragraph must carry before it counts as evidence (ADR-0007)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from check_zeef_contract import REPO_ROOT, corpus_path

from meetlat.zeef import corpus

VALID = {
    "id": "nl-9001",
    "text": "De gemeente stuurt binnen vijf werkdagen een bevestiging per e-mail.",
    "register": "formal_u",
    "domain": "administrative",
    "origin": "collected",
    "source": "rijksoverheid",
    "licence": "CC0-1.0",
    "url": "https://www.rijksoverheid.nl/onderwerpen/paspoort-en-identiteitskaart",
    "retrieved": "2026-09-22",
}


def test_the_committed_corpus_loads() -> None:
    entries = corpus.load(corpus_path(REPO_ROOT))
    assert entries
    assert all(entry.text.strip() for entry in entries)


def test_every_register_is_reported_even_when_empty() -> None:
    """A total of 200 over one register is not breadth, so the zeroes have to show."""
    counts = corpus.coverage([corpus.CorpusEntry.model_validate(VALID)])
    assert set(counts) == {"informal_je", "formal_u", "business", "plain_language"}
    assert counts["formal_u"] == 1
    assert counts["informal_je"] == 0


def test_a_share_alike_licence_is_refused() -> None:
    """CC BY-SA would force this project's data licence to change: Wikipedia is out."""
    with pytest.raises(ValueError, match="not one this project can redistribute"):
        corpus.CorpusEntry.model_validate({**VALID, "licence": "CC-BY-SA-4.0"})


def test_collected_text_must_say_where_it_came_from() -> None:
    with pytest.raises(ValueError, match="url and a retrieved date"):
        corpus.CorpusEntry.model_validate({**VALID, "url": "", "retrieved": None})


def test_authored_text_needs_no_url() -> None:
    entry = corpus.CorpusEntry.model_validate(
        {
            **VALID,
            "origin": "authored",
            "source": "Niels van Beuningen",
            "licence": "CC-BY-4.0",
            "url": "",
            "retrieved": None,
        }
    )
    assert entry.origin == "authored"


def test_there_is_no_generated_origin() -> None:
    """Model-generated text would make the false-positive gate circular (ADR-0007)."""
    with pytest.raises(ValueError):
        corpus.CorpusEntry.model_validate({**VALID, "origin": "generated"})


def test_a_malformed_line_names_its_line_number(tmp_path: Path) -> None:
    path = tmp_path / "corpus.jsonl"
    path.write_text(
        json.dumps(VALID) + "\n" + json.dumps({**VALID, "id": "nl-9002", "register": "x"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="corpus.jsonl:2"):
        corpus.load(path)
