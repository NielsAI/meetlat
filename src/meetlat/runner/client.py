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
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Final

from meetlat import settings

# Tunables live in `meetlat.settings`; re-exported here so a caller that has this module
# does not need both, and so the names tests already use keep working.
BASE_URL_VAR: Final = settings.BASE_URL_VAR
API_KEY_VAR: Final = settings.API_KEY_VAR
MODEL_VAR: Final = settings.MODEL_VAR
ATTEMPTS: Final = settings.ATTEMPTS
BACKOFF: Final = settings.BACKOFF
TIMEOUT: Final = settings.TIMEOUT


#: Exactly the values `secrets/.env.example` ships with. Not a tunable and not in
#: `meetlat.settings`: this is a guard against unfilled configuration, and it is correct
#: only while it matches the example file it is paired with.
_PLACEHOLDERS = frozenset(
    {
        "paste-your-key-here",
        "replace-with-a-model-id",
        "https://api.example.com/v1",
        "changeme",
    }
)

#: Domains reserved for documentation and testing (RFC 2606, RFC 6761). Nobody has a
#: real endpoint on one, so a base url pointing at one is unfilled configuration rather
#: than a choice. Checked as well as the exact values above, so rewording the example
#: cannot quietly disable the check.
_RESERVED = (".example", ".invalid", ".test", "example.com", "example.net", "example.org")


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

        unfilled = [v for v in (BASE_URL_VAR, API_KEY_VAR, MODEL_VAR) if _is_placeholder(v)]
        if unfilled:
            holds = "holds" if len(unfilled) == 1 else "hold"
            raise EndpointError(
                f"{', '.join(unfilled)} still {holds} the example value; fill in "
                f"secrets/.env after copying secrets/.env.example"
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


def _is_placeholder(variable: str) -> bool:
    """Whether this variable still holds what the example file ships with."""
    value = os.environ.get(variable, "").strip()
    if value.lower() in _PLACEHOLDERS:
        return True
    return variable == BASE_URL_VAR and any(marker in value.lower() for marker in _RESERVED)


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
        except urllib.error.URLError as exc:
            # A name that does not resolve will not resolve on the third attempt either,
            # and retrying it costs the backoff for nothing. A refused connection or a
            # reset is transient and is retried; a typo in the host is not.
            if isinstance(exc.reason, socket.gaierror):
                raise EndpointError(f"cannot resolve the endpoint host: {exc.reason}") from None
            last = type(exc).__name__
        except (TimeoutError, KeyError, json.JSONDecodeError) as exc:
            last = type(exc).__name__
        if attempt + 1 < ATTEMPTS:
            time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
    raise EndpointError(f"{last} after {ATTEMPTS} attempts")
