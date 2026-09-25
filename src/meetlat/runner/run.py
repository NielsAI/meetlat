"""Drive a prompt set through an endpoint and keep what came back.

The response file is the artifact, not the report. It is what build step 3 hand-labels
and what a judge is later measured against, so it carries everything needed to read it
a year later without the shell history that produced it: the prompt, the context it was
given, the model, the temperature and the seed.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from meetlat import settings
from meetlat.runner.client import Endpoint, EndpointError, complete
from meetlat.taxonomy import Domain, Register, Task
from meetlat.taxonomy.generate import ContextDocument, Prompt


class RunMetadata(BaseModel):
    """What produced a response set. Never holds a key."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1)
    temperature: float
    base_url: str = Field(min_length=1)
    seed: int
    per_cell: int
    started: datetime


# `register` shadows `ABCMeta.register`, the same pydantic warning `zeef.corpus` and the
# generator both silence, for the same reason: it is this project's vocabulary.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message='Field name "register"', category=UserWarning)

    class Response(BaseModel):
        """One model response, with everything needed to label or re-measure it.

        The prompt's axes are copied onto the response rather than looked up through
        `prompt_id`. ADR-0003 reports every score per interaction type, and a report that
        has to join two files to group by task is one that gets written without grouping.
        """

        model_config = ConfigDict(extra="forbid", frozen=True)

        id: str = Field(min_length=1)
        prompt_id: str = Field(min_length=1)
        task: Task
        register: Register
        domain: Domain
        instruction: str = Field(min_length=1)
        #: The document the model was given, stored in full. Resolving a context id
        #: against a pool that has since been recollected is how a label ends up
        #: describing text nobody can see any more.
        context: str = ""
        response: str = ""
        #: Empty unless the endpoint failed for this prompt. A failed item is kept rather
        #: than dropped, because a run that silently returns fewer responses than prompts
        #: looks like a run that succeeded.
        error: str = ""
        model: str = Field(min_length=1)
        temperature: float


def load_responses(path: Path) -> list[Response]:
    """Read a response file. Raises with the line number on a malformed record."""
    responses: list[Response] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        try:
            responses.append(Response.model_validate(json.loads(line)))
        except Exception as exc:
            raise ValueError(f"{path.name}:{line_no}: {exc}") from exc
    return responses


#: Consecutive failures before a run gives up. A wrong key, a wrong model name or a
#: dead endpoint fails every prompt identically, and grinding through several hundred of
#: those at three attempts each is minutes spent learning something the fifth failure
#: already said. Consecutive rather than total, so an endpoint that drops one request in
#: fifty still completes the run.
# Tunables live in `meetlat.settings`; re-exported so `run_prompts`'s defaults read at
# the call site and a caller can override either without importing two modules.
GIVE_UP_AFTER = settings.GIVE_UP_AFTER
CONCURRENCY = settings.CONCURRENCY


def run_prompts(
    prompts: list[Prompt],
    contexts: list[ContextDocument],
    endpoint: Endpoint,
    *,
    on_each: Callable[[Response], None] | None = None,
    ask: Callable[[Endpoint, str, str], str] = complete,
    give_up_after: int = GIVE_UP_AFTER,
    concurrency: int = CONCURRENCY,
) -> Iterator[Response]:
    """Yield one response per prompt, **in prompt order**, keeping failures as failures.

    Concurrent, but ordered. Several hundred sequential round trips is most of a run's
    wall-clock, and every iteration on a prompt set pays it again. What ordering buys is
    worth keeping though: `on_each` runs in the consuming thread, so the response file is
    written by one thread in a fixed order, and an id stays tied to its prompt rather
    than to whichever request happened to finish first. A response set has to be
    describable later, and "whatever order the network returned that afternoon" is not a
    description.

    Giving up is counted in prompt order too, for the same reason: `consecutive` has to
    mean something stable, and in completion order it would mean whichever failures
    happened to land together.
    """
    documents = {document.id: document for document in contexts}

    def one(index: int, prompt: Prompt) -> Response:
        context = documents[prompt.context_id].text if prompt.context_id else ""
        text, error = "", ""
        try:
            text = ask(endpoint, prompt.instruction, context)
        except EndpointError as exc:
            error = str(exc)
        return Response(
            id=f"r-{prompt.seed}-{index:04d}",
            prompt_id=prompt.id,
            task=prompt.task,
            register=prompt.register,
            domain=prompt.domain,
            instruction=prompt.instruction,
            context=context,
            response=text,
            error=error,
            model=endpoint.model,
            temperature=endpoint.temperature,
        )

    consecutive = 0
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        pending = [pool.submit(one, index, prompt) for index, prompt in enumerate(prompts, 1)]
        try:
            for future in pending:
                response = future.result()
                if on_each is not None:
                    on_each(response)
                yield response

                consecutive = consecutive + 1 if response.error else 0
                if consecutive >= give_up_after:
                    return
        finally:
            # Reached on the give-up return and on a caller that stops consuming early.
            # Queued work is cancellable; the few already running are not, and are left
            # to finish rather than abandoned mid-request.
            for future in pending:
                future.cancel()


def metadata(endpoint: Endpoint, seed: int, per_cell: int) -> RunMetadata:
    return RunMetadata(
        model=endpoint.model,
        temperature=endpoint.temperature,
        base_url=endpoint.base_url,
        seed=seed,
        per_cell=per_cell,
        started=datetime.now(timezone.utc),
    )
