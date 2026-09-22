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
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

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


def run_prompts(
    prompts: list[Prompt],
    contexts: list[ContextDocument],
    endpoint: Endpoint,
    *,
    on_each: Callable[[Response], None] | None = None,
    ask: Callable[[Endpoint, str, str], str] = complete,
) -> Iterator[Response]:
    """Yield one response per prompt, in order, keeping failures as failures.

    A generator so the caller can write each response as it arrives. A run of several
    hundred prompts against a paid endpoint that loses everything because it died at
    item 390 is the failure worth designing against first.
    """
    documents = {document.id: document for document in contexts}

    for index, prompt in enumerate(prompts, start=1):
        context = documents[prompt.context_id].text if prompt.context_id else ""
        text, error = "", ""
        try:
            text = ask(endpoint, prompt.instruction, context)
        except EndpointError as exc:
            error = str(exc)

        response = Response(
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
        if on_each is not None:
            on_each(response)
        yield response


def metadata(endpoint: Endpoint, seed: int, per_cell: int) -> RunMetadata:
    return RunMetadata(
        model=endpoint.model,
        temperature=endpoint.temperature,
        base_url=endpoint.base_url,
        seed=seed,
        per_cell=per_cell,
        started=datetime.now(timezone.utc),
    )
