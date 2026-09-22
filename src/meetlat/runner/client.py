"""One OpenAI-compatible `/chat/completions` call, over the standard library.

No SDK, for the reason the collector uses `urllib` too: a dependency that exists to save
twenty lines is a dependency that has to be pinned, audited and updated, and this
repository's whole claim is that its cheapest layer runs anywhere with nothing installed.
An OpenAI-compatible endpoint is a POST with a JSON body; that is the whole protocol.

**The key comes from the environment and is never written anywhere.** Not into a run
record, not into a log line, not into an error message. `Endpoint.describe` exists so a
report can say which endpoint and model produced a number without saying what
authenticated it, and the request body is never echoed on failure for the same reason.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Final

#: Where the configuration comes from. Environment rather than flags so that a key never
#: reaches a shell history, a `make` invocation or a CI log.
BASE_URL_VAR: Final = "MEETLAT_BASE_URL"
API_KEY_VAR: Final = "MEETLAT_API_KEY"
MODEL_VAR: Final = "MEETLAT_MODEL"

#: Attempts per prompt, and the pause before each retry. A 429 or a 502 partway through
#: a few hundred prompts should cost a few seconds, not the run.
ATTEMPTS: Final = 3
BACKOFF: Final = (2.0, 8.0)

#: Long enough for a slow model on a long context, short enough that one hung request
#: does not hold a run open indefinitely.
TIMEOUT: Final = 120


class EndpointError(RuntimeError):
    """The endpoint failed in a way retrying did not fix. Carries no request body."""


@dataclass(frozen=True)
class Endpoint:
    """Where responses come from, and under what settings.

    `temperature` is pinned rather than defaulted, because ADR-0003 pins it for a judge
    and a response set generated at an unrecorded temperature cannot be compared with
    anything, including itself a month later.
    """

    base_url: str
    api_key: str
    model: str
    temperature: float = 0.0

    @staticmethod
    def from_environment(temperature: float = 0.0) -> "Endpoint":
        missing = [v for v in (BASE_URL_VAR, API_KEY_VAR, MODEL_VAR) if not os.environ.get(v)]
        if missing:
            raise EndpointError(
                f"set {', '.join(missing)}; the runner reads its endpoint from the "
                f"environment so a key never reaches a shell history"
            )
        return Endpoint(
            base_url=os.environ[BASE_URL_VAR].rstrip("/"),
            api_key=os.environ[API_KEY_VAR],
            model=os.environ[MODEL_VAR],
            temperature=temperature,
        )

    def describe(self) -> str:
        """The endpoint and model, without the key. Safe to print and to store."""
        return f"{self.base_url} · {self.model} · temperature {self.temperature}"


def complete(endpoint: Endpoint, instruction: str, context: str = "") -> str:
    """One completion, retried on a transient failure.

    The context document is a second user message rather than part of the instruction,
    so a response cannot be blamed on the two having been glued together in a way the
    model read as one sentence.
    """
    messages = [{"role": "user", "content": instruction}]
    if context:
        messages.append({"role": "user", "content": context})

    body = json.dumps(
        {
            "model": endpoint.model,
            "temperature": endpoint.temperature,
            "messages": messages,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        f"{endpoint.base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {endpoint.api_key}",
            "Content-Type": "application/json",
        },
    )

    last = ""
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
            return str(payload["choices"][0]["message"]["content"])
        except urllib.error.HTTPError as exc:
            # The status and reason only. A body can echo the prompt, and on some
            # gateways it echoes the Authorization header back in a diagnostic.
            last = f"HTTP {exc.code} {exc.reason}"
            if exc.code < 500 and exc.code != 429:
                raise EndpointError(last) from None
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            last = type(exc).__name__
        if attempt + 1 < ATTEMPTS:
            time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
    raise EndpointError(f"{last} after {ATTEMPTS} attempts")
