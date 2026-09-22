"""Build step 5: prompts to an endpoint, responses back, layer 1 over each.

The piece that turns a prompt set into something measurable, and the first part of this
repository that costs money. It is deliberately small, because most of what it must not
do is more important than what it does.

**It reports findings, never quality.** Layer 2 is a model call per criterion and no
judge here is calibrated, so a run produces layer 1 output and a response file. There is
no pass rate, because a pass rate from an uncalibrated judge is not a measurement
(ADR-0001) and the runner is not where that rule gets bent.

**Every response records what produced it.** Model, temperature and the prompt seed, on
the response itself rather than in a filename. ADR-0003 pins a judge's model and
temperature for the same reason: a number nobody can attribute to a configuration is a
number nobody can reproduce or compare, and a response file that outlives the shell
history that made it is the normal case.

**It stores the responses.** That file is what build step 3 hand-labels, which is the
real reason this comes before the first judge rather than after it, whatever the order
in the build table says: a judge cannot be calibrated against labels that do not exist,
and labels cannot exist without responses to label.

The endpoint is any OpenAI-compatible `/chat/completions`, configured by environment
rather than by a flag, so a key never reaches a shell history or a `make` invocation.
"""

from __future__ import annotations

from meetlat.runner.client import Endpoint, complete
from meetlat.runner.run import Response, RunMetadata, load_responses, run_prompts

__all__ = [
    "Endpoint",
    "Response",
    "RunMetadata",
    "complete",
    "load_responses",
    "run_prompts",
]
