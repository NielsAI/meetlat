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


def test_the_example_values_are_refused_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Copying .env.example and forgetting to fill it in used to spend 29s on api.example.com."""
    monkeypatch.setenv(BASE_URL_VAR, "https://api.example.com/v1")
    monkeypatch.setenv(API_KEY_VAR, "paste-your-key-here")
    monkeypatch.setenv(MODEL_VAR, "replace-with-a-model-id")
    with pytest.raises(EndpointError, match="example value"):
        Endpoint.from_environment()


def test_a_reserved_domain_is_refused_however_the_example_is_worded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RFC 2606 and 6761 domains can never be a real endpoint, so they mean `not configured`."""
    monkeypatch.setenv(API_KEY_VAR, "a-real-looking-key")
    monkeypatch.setenv(MODEL_VAR, "a-real-model")
    for host in ("https://api.example.org/v1", "https://foo.invalid/v1", "https://x.test/v1"):
        monkeypatch.setenv(BASE_URL_VAR, host)
        with pytest.raises(EndpointError, match="example value"):
            Endpoint.from_environment()


def test_a_real_looking_endpoint_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The check must not get in the way of a local or self-hosted endpoint."""
    monkeypatch.setenv(BASE_URL_VAR, "http://127.0.0.1:11434/v1")
    monkeypatch.setenv(API_KEY_VAR, "a-real-looking-key")
    monkeypatch.setenv(MODEL_VAR, "qwen3")
    assert Endpoint.from_environment().model == "qwen3"


def test_a_run_gives_up_after_consecutive_failures() -> None:
    """A wrong key fails every prompt identically; the fifth says what the four hundredth would."""

    def always_fail(endpoint: Endpoint, instruction: str, context: str) -> str:
        raise EndpointError("HTTP 401 Unauthorized")

    prompts, contexts = _prompts(40)
    got = list(run_prompts(prompts, contexts, ENDPOINT, ask=always_fail, give_up_after=5))
    assert len(got) == 5
    assert all(r.error for r in got)


def test_an_occasional_failure_does_not_stop_the_run() -> None:
    """Consecutive, not total: an endpoint dropping one request in ten still completes."""
    calls = {"n": 0}

    def flaky(endpoint: Endpoint, instruction: str, context: str) -> str:
        calls["n"] += 1
        if calls["n"] % 4 == 0:
            raise EndpointError("HTTP 503 Service Unavailable")
        return "Een antwoord."

    prompts, contexts = _prompts(40)
    got = list(run_prompts(prompts, contexts, ENDPOINT, ask=flaky, give_up_after=5))
    assert len(got) == len(prompts)


def test_responses_stay_in_prompt_order_however_they_finish() -> None:
    """A response set has to be describable later; completion order is not a description."""
    import time

    def slow_first(endpoint: Endpoint, instruction: str, context: str) -> str:
        # The earliest prompts take longest, so completion order is the reverse of
        # submission order unless ordering is actually enforced.
        time.sleep(0.05 if "Herschrijf" in instruction else 0.0)
        return instruction[:12]

    prompts, contexts = _prompts(12)
    got = list(run_prompts(prompts, contexts, ENDPOINT, ask=slow_first, concurrency=6))
    assert [r.prompt_id for r in got] == [p.id for p in prompts]
    assert [r.id for r in got] == sorted(r.id for r in got)


def test_the_work_actually_overlaps() -> None:
    """Otherwise this is sequential with extra machinery."""
    import threading
    import time

    live, peak, lock = 0, 0, threading.Lock()

    def watched(endpoint: Endpoint, instruction: str, context: str) -> str:
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(0.05)
        with lock:
            live -= 1
        return "ok"

    prompts, contexts = _prompts(12)
    list(run_prompts(prompts, contexts, ENDPOINT, ask=watched, concurrency=4))
    assert peak > 1, "requests never overlapped"
    assert peak <= 4, f"concurrency bound exceeded: {peak}"


def test_giving_up_is_still_counted_in_prompt_order() -> None:
    """Concurrency must not turn `five in a row` into `whichever five landed together`."""

    def fail_after_two(endpoint: Endpoint, instruction: str, context: str) -> str:
        raise EndpointError("HTTP 401 Unauthorized")

    prompts, contexts = _prompts(40)
    got = list(
        run_prompts(prompts, contexts, ENDPOINT, ask=fail_after_two, give_up_after=5, concurrency=8)
    )
    assert len(got) == 5
    assert [r.prompt_id for r in got] == [p.id for p in prompts[:5]]


def test_the_file_is_written_by_one_thread_in_order() -> None:
    """on_each runs in the consuming thread, so the response file cannot interleave."""
    import threading

    seen = []
    threads = set()

    def record(response) -> None:
        threads.add(threading.current_thread().name)
        seen.append(response)

    prompts, contexts = _prompts(12)
    list(
        run_prompts(
            prompts, contexts, ENDPOINT, ask=lambda e, i, c: "ok", on_each=record, concurrency=6
        )
    )
    assert threads == {threading.current_thread().name}, f"written from {threads}"
    assert [r.prompt_id for r in seen] == [p.id for p in prompts]
