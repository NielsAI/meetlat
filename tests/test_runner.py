"""The runner's promises, none of which need a network or a key.

What matters is not that it can POST, which is twenty lines of stdlib, but that a failed
item is kept rather than dropped, that nothing it writes contains the API key, and that
every response says what produced it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meetlat.runner import Endpoint, load_responses, run_prompts
from meetlat.runner.client import API_KEY_VAR, BASE_URL_VAR, MODEL_VAR, EndpointError
from meetlat.runner.run import metadata
from meetlat.taxonomy.generate import ContextDocument, generate

KEY = "sk-test-do-not-log-me"
ENDPOINT = Endpoint(base_url="https://example.invalid/v1", api_key=KEY, model="a-model")


def _context() -> ContextDocument:
    return ContextDocument.model_validate(
        {
            "id": "ctx-0001",
            "text": "Een standaard is een afspraak.\n\nSystemen moeten dezelfde standaard hanteren.",
            "domain": "technical",
            "language": "nl",
            "source": "digitaleoverheid",
            "licence": "CC0-1.0",
        }
    )


def _prompts(n: int = 4):
    contexts = [_context()]
    prompts, _ = generate(seed=11, per_cell=1, contexts=contexts)
    return prompts[:n], contexts


def test_every_response_records_what_produced_it() -> None:
    """A number nobody can attribute to a configuration cannot be reproduced (ADR-0003)."""
    prompts, contexts = _prompts()
    got = list(run_prompts(prompts, contexts, ENDPOINT, ask=lambda e, i, c: "Een antwoord."))
    assert got
    for response in got:
        assert response.model == "a-model"
        assert response.temperature == 0.0
        assert response.prompt_id


def test_a_failed_prompt_is_kept_rather_than_dropped() -> None:
    """A run that returns fewer responses than prompts looks like a run that succeeded."""

    calls = {"n": 0}

    def flaky(endpoint: Endpoint, instruction: str, context: str) -> str:
        calls["n"] += 1
        if calls["n"] % 2 == 0:
            raise EndpointError("HTTP 503 Service Unavailable")
        return "Een antwoord."

    prompts, contexts = _prompts(8)
    got = list(run_prompts(prompts, contexts, ENDPOINT, ask=flaky))

    assert len(got) == len(prompts), "a dropped item makes a partial run look complete"
    assert len([r for r in got if r.error]) == 4
    assert len([r for r in got if r.response]) == 4
    for response in got:
        assert bool(response.error) != bool(response.response)


def test_the_context_is_stored_with_the_response_not_just_its_id() -> None:
    """A label describing a document the pool no longer holds describes nothing."""
    prompts, contexts = _prompts(20)
    got = list(run_prompts(prompts, contexts, ENDPOINT, ask=lambda e, i, c: "ok"))
    with_context = [r for r in got if r.context]
    assert with_context
    assert all(r.context == contexts[0].text for r in with_context)


def test_nothing_written_by_a_run_contains_the_api_key(tmp_path: Path) -> None:
    """The one thing this must never do, asserted rather than assumed."""
    prompts, contexts = _prompts(3)
    got = list(run_prompts(prompts, contexts, ENDPOINT, ask=lambda e, i, c: "Een antwoord."))
    written = "\n".join(r.model_dump_json() for r in got)
    written += metadata(ENDPOINT, seed=11, per_cell=1).model_dump_json()
    written += ENDPOINT.describe()
    assert KEY not in written


def test_run_metadata_carries_the_endpoint_but_not_the_key() -> None:
    record = metadata(ENDPOINT, seed=11, per_cell=2)
    dumped = json.loads(record.model_dump_json())
    assert dumped["model"] == "a-model"
    assert dumped["base_url"] == "https://example.invalid/v1"
    assert KEY not in json.dumps(dumped)


def test_a_missing_endpoint_variable_names_which_one(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (BASE_URL_VAR, API_KEY_VAR, MODEL_VAR):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(EndpointError, match=BASE_URL_VAR):
        Endpoint.from_environment()


def test_responses_round_trip_through_the_file(tmp_path: Path) -> None:
    prompts, contexts = _prompts(3)
    got = list(run_prompts(prompts, contexts, ENDPOINT, ask=lambda e, i, c: "Een antwoord."))
    path = tmp_path / "responses.jsonl"
    path.write_text(
        f"// {metadata(ENDPOINT, 11, 1).model_dump_json()}\n"
        + "".join(r.model_dump_json() + "\n" for r in got),
        encoding="utf-8",
    )
    reloaded = load_responses(path)
    assert [r.id for r in reloaded] == [r.id for r in got]


def test_a_malformed_response_names_its_line(tmp_path: Path) -> None:
    path = tmp_path / "responses.jsonl"
    path.write_text('{"id": "r-1"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="responses.jsonl:1"):
        load_responses(path)
