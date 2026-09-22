#!/usr/bin/env python3
"""Label a worklist by hand, and reconcile two passes into a gold set (ADR-0004, steps 2-3).

    python3 scripts/label_gold.py runs/register_fit-worklist.jsonl --annotator niels
    python3 scripts/label_gold.py --reconcile runs/register_fit-{niels,sam}.jsonl

**Blind means blind.** Each annotator writes their own file and this never reads another
annotator's. That is the step most often skipped, and skipping it turns the exercise into
measuring agreement with whoever labelled first.

**An agent must not run the labelling mode.** A judge calibrated against labels from the
same model family it evaluates measures very little, so this is a person's tool; the
protocol says so and `gold/` has a fail-closed guard behind it. What an agent may do is
prepare the worklist and run the arithmetic.

**Reconciliation refuses to resolve a disagreement silently.** Where two annotators
disagreed, a note is required before the item is written, because `GoldItem` refuses one
without it and because those notes are the most valuable output of the protocol: if the
disagreements share a shape, the criterion is badly defined rather than the raters
careless, and the fix is rewriting the criterion before any judge exists for it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from review_corpus import Stopped, key  # noqa: E402  (the same keystroke reader)

from meetlat import console  # noqa: E402
from meetlat.console import C  # noqa: E402
from meetlat.ijk.gold import GoldItem  # noqa: E402


def read_items(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("//")
    ]


def already_done(path: Path) -> set[str]:
    """Item ids this annotator has already labelled, so a session resumes."""
    if not path.exists():
        return set()
    return {str(row["id"]) for row in read_items(path)}


def show(item: dict[str, Any], position: str, question: str) -> None:
    console.rule()
    console.banner("meetlat · label", position)
    console.say()
    console.line(f"{C.dim}{item['interaction_type']}{C.reset}", indent=2)
    console.say()
    console.line(f"{C.dim}prompt{C.reset}", indent=2)
    for line in _wrapped(str(item["prompt"])):
        console.line(line, indent=4)
    console.say()
    console.line(f"{C.dim}response{C.reset}", indent=2)
    for line in _wrapped(str(item["response"])):
        console.line(line, indent=4)
    console.say()
    console.line(f"{C.bold}{question}{C.reset}", indent=2)


def _wrapped(text: str, width: int = 86) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines or [""]


def label(path: Path, annotator: str, question: str) -> int:
    out = path.with_name(f"{path.stem.replace('-worklist', '')}-{annotator}.jsonl")
    items = read_items(path)
    done = already_done(out)
    todo = [item for item in items if item["id"] not in done]

    console.banner("meetlat · label", f"{annotator}, {len(todo)} of {len(items)} left")
    console.note("your own file only: this never reads another annotator's labels")
    if done:
        console.note(f"{len(done)} already labelled in an earlier session")

    labelled = 0
    with out.open("a", encoding="utf-8") as handle:
        for index, item in enumerate(todo, start=1):
            show(item, f"{index} of {len(todo)}", question)
            try:
                choice = key({"y": "yes", "n": "no", "s": "skip", "q": "save and quit"})
            except Stopped:
                break
            if choice == "q":
                break
            if choice == "s":
                continue
            handle.write(
                json.dumps({"id": item["id"], "label": choice == "y"}, ensure_ascii=False) + "\n"
            )
            handle.flush()
            labelled += 1

    console.say()
    console.rule()
    console.ok(f"{labelled} labelled this session, written to {out}")
    console.note("when a second person has done the same, reconcile the two files")
    return 0


def reconcile(worklist: Path, first: Path, second: Path, out: Path) -> int:
    """Merge two annotators' passes, asking for a note wherever they disagreed."""
    items = {row["id"]: row for row in read_items(worklist)}
    a_name, b_name = first.stem.split("-")[-1], second.stem.split("-")[-1]
    a = {row["id"]: bool(row["label"]) for row in read_items(first)}
    b = {row["id"]: bool(row["label"]) for row in read_items(second)}

    shared = [i for i in items if i in a and i in b]
    disputed = [i for i in shared if a[i] != b[i]]

    console.banner("meetlat · reconcile", f"{a_name} and {b_name}")
    console.stat(
        "   ".join(
            (
                console.field("labelled by both", len(shared)),
                console.field("disagreed on", len(disputed)),
                console.field("agreement", f"{1 - len(disputed) / max(len(shared), 1):.0%}"),
            )
        )
    )
    if not shared:
        console.fail("no item was labelled by both annotators; there is nothing to reconcile")

    resolved: list[GoldItem] = []
    for item_id in shared:
        item = items[item_id]
        labels = {a_name: a[item_id], b_name: b[item_id]}
        if item_id not in disputed:
            resolved.append(
                GoldItem.model_validate(
                    {
                        "id": item_id,
                        "interaction_type": item["interaction_type"],
                        "prompt": item["prompt"],
                        "response": item["response"],
                        "labels": labels,
                        "reconciled": a[item_id],
                    }
                )
            )
            continue

        show(item, item_id, f"{a_name} said {a[item_id]}, {b_name} said {b[item_id]}")
        console.say()
        console.line(f"{C.bold}what is the reconciled label?{C.reset}", indent=2)
        try:
            choice = key({"y": "yes", "n": "no", "q": "stop here"})
        except Stopped:
            break
        if choice == "q":
            break
        console.say()
        console.line(f"{C.bold}why? (one line, required){C.reset}", indent=2)
        note = input("    ").strip()
        if not note:
            console.warn(
                "no note, so this item is left out; a disagreement without one is not a label"
            )
            continue
        resolved.append(
            GoldItem.model_validate(
                {
                    "id": item_id,
                    "interaction_type": item["interaction_type"],
                    "prompt": item["prompt"],
                    "response": item["response"],
                    "labels": labels,
                    "reconciled": choice == "y",
                    "note": note,
                }
            )
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(item.model_dump_json() + "\n" for item in resolved), encoding="utf-8")
    console.say()
    console.ok(f"{len(resolved)} reconciled item(s) written to {out}")

    classes = {item.reconciled for item in resolved}
    if len(classes) < 2:
        console.warn(
            "every reconciled label is the same class; `make check-judges` refuses a set "
            "like this, because a judge that always answers that way scores perfectly on it"
        )
    console.say()
    console.wrap(
        "Read the notes as a set before going further. If the disagreements share a shape, "
        "the criterion is badly defined rather than the raters careless, and the fix is "
        "rewriting the criterion and sampling again."
    )
    console.note("when it is right, copy it to gold/<criterion>-v1.jsonl yourself")
    console.note("that copy is a person's job: an agent write to gold/ is refused, and correctly")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("worklist", type=Path, nargs="?", help="from scripts/sample_gold.py")
    parser.add_argument("--annotator", help="your name, for your own label file")
    parser.add_argument(
        "--question",
        default="Does this response satisfy the criterion? (y/n)",
        help="the yes-or-no question, as one sentence with no `and` in it",
    )
    parser.add_argument("--reconcile", nargs=2, type=Path, metavar=("FIRST", "SECOND"))
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.reconcile:
        if args.worklist is None:
            console.fail("reconciling needs the worklist too, for the prompts and responses")
        out = args.out or args.worklist.with_name(
            args.worklist.stem.replace("-worklist", "") + "-reconciled.jsonl"
        )
        return reconcile(args.worklist, args.reconcile[0], args.reconcile[1], out)

    if args.worklist is None or not args.annotator:
        console.fail("labelling needs a worklist and --annotator; --reconcile merges two passes")
    if " and " in args.question:
        console.fail(
            "that question contains `and`, so it is two criteria and needs two judges (ADR-0003)"
        )
    return label(args.worklist, args.annotator, args.question)


if __name__ == "__main__":
    raise SystemExit(main())
