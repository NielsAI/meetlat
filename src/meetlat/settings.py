"""Operational tunables: how hard to try, how fast to go, how long to wait.

One place for the numbers an operator adjusts for their own endpoint or their own
patience, so tuning a run does not mean reading four modules to find where the knobs
ended up.

**What belongs here and what does not.** These are values that could reasonably differ
between two people running the same code correctly: a concurrency that suits a private
endpoint and throttles a shared one, a pause that is polite to one publisher and rude to
another. They encode an operating condition, not a rule.

A value that encodes a *rule* stays with the code that enforces it, next to the comment
explaining why it is that number. `MIN_CHARS` and `PER_REGISTER` live in
`meetlat.zeef.corpus` on purpose, because the collector, the reviewer and the gate all
have to read one number and the reasoning has to be where a reader meets it.
`REDISTRIBUTABLE` is a licensing decision. The 150-to-200 gold set size is ADR-0004.
Moving those here would turn a documented decision into a setting somebody feels free to
change, which is the opposite of what this file is for.

The test is: if changing it would need an argument, it is a rule and does not belong
here. If changing it would need a reason, it is a setting and does.
"""

from __future__ import annotations

from typing import Final

# --- Talking to a model endpoint -------------------------------------------------

#: Where the runner reads its endpoint from. Environment rather than flags so a key
#: never reaches a shell history, a `make` invocation or a CI log.
BASE_URL_VAR: Final = "MEETLAT_BASE_URL"
API_KEY_VAR: Final = "MEETLAT_API_KEY"
MODEL_VAR: Final = "MEETLAT_MODEL"

#: Requests in flight at once. Modest by default because the endpoint is unknown: a
#: shared or rate-limited one punishes a burst, and the retry path turns a 429 into
#: wall-clock rather than throughput. Raise it with `--concurrency` for one you own.
CONCURRENCY: Final = 4

#: Attempts per prompt, and the pause before each retry. A 429 or a 502 partway through
#: a few hundred prompts should cost a few seconds, not the run.
ATTEMPTS: Final = 3
BACKOFF: Final = (2.0, 8.0)

#: Long enough for a slow model on a long context, short enough that one hung request
#: does not hold a run open indefinitely.
TIMEOUT: Final = 120

#: Consecutive failures, counted in prompt order, before a run gives up. A wrong key, a
#: wrong model name or a dead endpoint fails every prompt identically, and grinding
#: through several hundred of those at three attempts each is minutes spent learning
#: what the fifth failure already said. Consecutive rather than total, so an endpoint
#: that drops one request in fifty still completes the run.
GIVE_UP_AFTER: Final = 5


# --- Fetching pages from a publisher ---------------------------------------------

#: Who the collector says it is. A publisher that wants to block or throttle this should
#: be able to, and an unidentified scraper takes that choice away from them.
USER_AGENT: Final = "meetlat-corpus-collector (https://github.com/NielsAI/meetlat)"

#: Seconds between page fetches. The indexes read here are public and free to use, and
#: reading one at full speed is the reliable way to make it stop being either.
PAUSE: Final = 0.5

#: Records per index request. The Edurep endpoint refuses anything larger.
INDEX_PAGE: Final = 100

#: Pages one indexed run will read. A lesson page yields well under one usable
#: paragraph, so a run reads a lot of them, and this is what stops a narrow keyword
#: walking the whole index in one go.
MAX_PAGES: Final = 150
