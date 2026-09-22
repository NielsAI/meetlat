#!/usr/bin/env python3
"""Draw a worklist for hand-labelling from a response set (ADR-0004, step 1).

This prepares items. It does not label them and it cannot: a judge calibrated against
labels from the same model family it will evaluate measures very little, which is why
the protocol says an agent is not an annotator. What an agent can usefully do is the
part that is arithmetic, and getting the sample wrong is the one mistake in the protocol
that is invisible in the resulting number.

    python3 scripts/sample_gold.py runs/responses.jsonl --criterion register_fit

**Stratified across interaction types**, because a pass rate over mixed traffic hides
that rewriting works and summarising does not, and because a set drawn uniformly from a
run is mostly whichever type had most prompts.

**With a bounded share drawn from responses layer 1 fired on.** A set sampled from
typical output is all passes, and a judge that always answers yes scores perfectly on it;
that is the exact failure balanced accuracy exists to expose. So some items have to be
ones a person is likely to mark false, and a layer 1 finding is the only signal available
before anybody has labelled anything.

**That share is a bias and it is bounded on purpose.** Layer 1 catches translationese,
meta-commentary and repetition. Oversampling those enriches the set for defects layer 1
already finds for free, which is precisely the work layer 2 is not needed for, and a
judge calibrated on it would look good at the easy half of its job. `--failure-share`
defaults to a quarter and the composition is printed, so the bias is visible and
argued with rather than discovered later.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meetlat import console, zeef  # noqa: E402  (needs the sys.path line above)
from meetlat.runner import load_responses  # noqa: E402
from meetlat.runner.run import Response  # noqa: E402

#: What ADR-0004 asks for. Below the floor the agreement figures are too noisy to certify
#: anything; above the ceiling the cost is human minutes for precision nobody uses.
TARGET = 175
FLOOR = 150
CEILING = 200

#: The criteria a judge may be built for (CONTEXT.md). Checked here so a worklist for
#: `register-fit` is caught before two people spend an evening labelling it under a name
#: nothing else in the project uses.
CRITERIA = (
    "instruction_compliance",
    "faithfulness",
    "register_fit",
    "naturalness",
    "task_completion",
)

#: How much of the set is drawn from responses a layer 1 check fired on. See the module
#: docstring: this is a deliberate, bounded bias, not a tuning knob.
FAILURE_SHARE = 0.25


def flagged(response: Response) -> bool:
    """Whether layer 1 found anything in this response. A proxy for `likely to fail`."""
    return bool(zeef.run(response.response).findings)


def draw(
    responses: list[Response], *, size: int, failure_share: float, seed: int
) -> list[Response]:
    """A stratified sample: equal shares per interaction type, some of them flagged.

    Deterministic under `seed`, because the set a judge was calibrated against has to be
    describable later, and `whichever 175 came out that afternoon` is not a description.
    """
    rng = random.Random(seed)
    by_type: dict[str, list[Response]] = defaultdict(list)
    for response in responses:
        if response.response:
            by_type[response.task].append(response)

    if not by_type:
        return []

    per_type = max(1, size // len(by_type))
    drawn: list[Response] = []
    for task in sorted(by_type):
        pool = by_type[task]
        hits = [r for r in pool if flagged(r)]
        clean = [r for r in pool if r not in hits]
        rng.shuffle(hits)
        rng.shuffle(clean)

        want_hits = min(len(hits), round(per_type * failure_share))
        take = hits[:want_hits] + clean[: per_type - want_hits]
        # Short on clean items rather than flagged ones: top up from whatever is left
        # instead of returning a thin stratum and pretending the type is covered.
        if len(take) < per_type:
            rest = [r for r in pool if r not in take]
            take += rest[: per_type - len(take)]
        drawn.extend(take)
    return drawn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("responses", type=Path, help="a response set from `meetlat run`")
    parser.add_argument("--criterion", required=True, help="which criterion this set is for")
    parser.add_argument("--size", type=int, default=TARGET)
    parser.add_argument("--failure-share", type=float, default=FAILURE_SHARE)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.responses.exists():
        console.fail(f"{args.responses} does not exist; `make run` writes one")
    if args.criterion not in CRITERIA:
        console.fail(
            f"unknown criterion {args.criterion!r}; CONTEXT.md lists {', '.join(CRITERIA)}"
        )
    if not FLOOR <= args.size <= CEILING:
        console.fail(f"ADR-0004 asks for {FLOOR} to {CEILING} items; {args.size} is outside that")

    responses = load_responses(args.responses)
    answered = [r for r in responses if r.response]
    if not answered:
        console.fail(f"{args.responses} holds no answered responses")

    console.banner("meetlat · sample", f"{args.criterion}, target {args.size}")
    with console.Spinner(f"layer 1 over {len(answered)} responses"):
        drawn = draw(answered, size=args.size, failure_share=args.failure_share, seed=args.seed)

    out = args.out or Path("runs") / f"{args.criterion}-worklist.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for index, response in enumerate(drawn, start=1):
            handle.write(
                json.dumps(
                    {
                        "id": f"{args.criterion[:2]}-{index:04d}",
                        "interaction_type": response.task,
                        "prompt": response.instruction,
                        "response": response.response,
                        "response_id": response.id,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    per_type = Counter(r.task for r in drawn)
    hits = sum(1 for r in drawn if flagged(r))
    console.ok(f"{len(drawn)} item(s) written to {out}")
    console.stat(
        "   ".join(
            (
                console.field("items", len(drawn)),
                console.field("layer 1 fired on", hits),
                console.field("share", f"{hits / max(len(drawn), 1):.0%}"),
            )
        )
    )
    console.table([(task, str(n)) for task, n in sorted(per_type.items())], indent="    ")
    console.say()
    if len(drawn) < FLOOR:
        console.warn(f"{len(drawn)} is below the {FLOOR} ADR-0004 asks for; run more prompts first")
    console.wrap(
        f"{hits} of these were drawn because layer 1 fired on them, which enriches the set "
        f"for defects layer 1 already catches. Read the figure as a bound on that bias, not "
        f"as a count of items that will be labelled false."
    )
    console.say()
    console.note("two people label this independently and blind: scripts/label_gold.py")
    console.note("an agent is not an annotator (ADR-0004); these items are for a person")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
