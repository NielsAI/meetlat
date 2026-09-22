#!/usr/bin/env python3
"""Review collected candidates one at a time and append the accepted ones.

`collect_corpus.py` produces candidates; this decides which become evidence. The split
is the point. Collection is repeatable and cheap, review is a person's judgement and
the only step that writes to the corpus, and ADR-0007 puts the register tag and the
"is this actually correct Dutch" call on a person for the same reason: a gate filled
with text an agent chose is a gate measuring itself.

So there is no `--yes`, no auto-accept and no heuristic that sets a register. What this
does instead is make the judgement cheap to make well: it runs layer 1 over the
candidate first, because accepting a paragraph a verdict check fires on breaks the gate
on the next run, and it shows length against the paragraph floor and any near-duplicate
already in the corpus, because both are ways a corpus grows a count without growing
evidence.

    python3 scripts/collect_corpus.py --source cbs --limit 40 > batch.jsonl
    python3 scripts/review_corpus.py batch.jsonl

Accepted entries are appended to the corpus as you go, so quitting halfway loses
nothing. Rejected ones go to `<batch>.rejected.jsonl` with the reason, which is what
stops the same paragraph coming back in the next batch and says which sources are worth
collecting from.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_args

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meetlat import console, zeef  # noqa: E402  (needs the sys.path line above)
from meetlat.zeef import corpus  # noqa: E402

#: The floor each register has to clear before the corpus is evidence rather than a
#: total (ADR-0007). Printed per candidate so progress is visible while reviewing.
PER_REGISTER = 25

REGISTERS = list(get_args(corpus.Register))
DOMAINS = list(get_args(corpus.Domain))


def corpus_path(repo_root: Path = REPO_ROOT) -> Path:
    return repo_root / "tests" / "corpora" / "clean_nl.jsonl"


@dataclass
class Assessment:
    """Everything known about a candidate before a person looks at it."""

    findings: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    chars: int = 0
    below_floor: bool = False
    duplicate_of: str | None = None

    @property
    def blocked(self) -> str:
        """Why this cannot be accepted, or an empty string.

        A verdict check firing is the one hard stop. The corpus is what says a check
        that fired was wrong to, so a paragraph that makes one fire cannot be in it:
        accepting it would fail `make check-zeef` and the honest fix would be to
        narrow the check, which is a separate decision made deliberately rather than
        while reviewing a batch.
        """
        if self.findings:
            return f"a verdict check fires on it: {'; '.join(self.findings)}"
        if self.duplicate_of:
            return "it is a near-copy of a paragraph already in the corpus"
        return ""


def assess(text: str, existing: list[str]) -> Assessment:
    report = zeef.run(text)
    return Assessment(
        findings=[
            f"{result.check} ({len(result.findings)})"
            for result in report.results
            if result.findings
        ],
        metrics={k: v for result in report.results for k, v in result.metrics.items()},
        chars=len(text),
        below_floor=len(text) < corpus.MIN_CHARS,
        duplicate_of=corpus.near_duplicate(text, existing),
    )


def next_id(entries: list[corpus.CorpusEntry]) -> str:
    """The next `nl-NNNN`, taken from the highest already used rather than the count.

    Counting would reuse an id if one were ever removed, and an id that has pointed at
    two different paragraphs is worse than a gap in the sequence.
    """
    used = [int(entry.id.split("-")[-1]) for entry in entries if entry.id.startswith("nl-")]
    return f"nl-{max(used, default=0) + 1:04d}"


def by_thinnest_register(
    candidates: list[dict[str, Any]], counts: dict[str, int]
) -> list[dict[str, Any]]:
    """Candidates for the emptiest registers first.

    The exit condition is a floor per register, not a total, so the useful review hour
    is the one spent on the register furthest from it. Sorted by the proposed tag,
    which is a proposal: changing it during review is expected.
    """
    return sorted(candidates, key=lambda c: counts.get(str(c.get("register")), 0))


def render(
    candidate: dict[str, Any], seen: Assessment, position: str, counts: dict[str, int]
) -> None:
    proposed = str(candidate.get("register", "TODO"))
    console.rule()
    console.banner("meetlat · review", position)
    console.say()
    for line in _wrapped(str(candidate["text"])):
        console.line(line, indent=2)
    console.say()

    if seen.findings:
        console.bad(f"a verdict check fires: {', '.join(seen.findings)}")
    else:
        console.ok("no verdict check fires")
    if seen.duplicate_of:
        console.warn(f"near-copy of: {seen.duplicate_of[:70]}")
    if seen.below_floor:
        console.warn(f"{seen.chars} characters, below the {corpus.MIN_CHARS}-character floor")
    else:
        console.stat(f"{seen.chars} characters")
    if "words" in seen.metrics:
        console.stat(
            f"{int(seen.metrics['words'])} words"
            + (
                f", {int(seen.metrics['out_of_vocabulary'])} out of vocabulary"
                if seen.metrics.get("out_of_vocabulary")
                else ""
            )
        )
    console.stat(
        f"{candidate.get('source')} · {candidate.get('licence')} · {candidate.get('author') or 'no author'}"
    )
    console.say()
    console.note(f"proposed: register {proposed}   domain {candidate.get('domain')}")
    console.note(f"{proposed}: {counts.get(proposed, 0)} of {PER_REGISTER}")


def _wrapped(text: str, width: int = 88) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def append(entry: corpus.CorpusEntry, path: Path) -> None:
    payload = entry.model_dump(mode="json", exclude_defaults=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _ask(prompt: str, options: list[str]) -> str:
    while True:
        console.say()
        for index, option in enumerate(options, start=1):
            console.line(f"[{index}] {option}", indent=4)
        answer = input("  > ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        console.warn(f"pick 1 to {len(options)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path, help="candidate JSONL from collect_corpus.py")
    parser.add_argument("--corpus", type=Path, default=corpus_path())
    args = parser.parse_args(argv)

    candidates = [
        json.loads(line)
        for line in args.batch.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    entries = corpus.load(args.corpus)
    counts: dict[str, int] = {str(k): v for k, v in corpus.coverage(entries).items()}
    rejects = args.batch.with_suffix(".rejected.jsonl")

    console.banner("meetlat · review", f"{len(candidates)} candidate(s)")
    console.note(f"corpus: {len(entries)} entries, floor {PER_REGISTER} per register")
    console.note("nothing is accepted without a keystroke: the register tag is the judgement")

    accepted = rejected = 0
    queue = by_thinnest_register(candidates, counts)
    for index, candidate in enumerate(queue, start=1):
        texts = [entry.text for entry in entries]
        seen = assess(str(candidate["text"]), texts)
        render(candidate, seen, f"{index} of {len(queue)}", counts)

        if seen.blocked:
            console.say()
            console.bad(f"cannot be accepted: {seen.blocked}")
            choice = _ask("", ["reject and continue", "quit"])
            if choice == "quit":
                break
            _reject(candidate, seen.blocked, rejects)
            rejected += 1
            continue

        choice = _ask("", ["accept", "reject", "change register", "change domain", "skip", "quit"])
        if choice == "quit":
            break
        if choice == "skip":
            continue
        if choice == "change register":
            candidate["register"] = _ask("", REGISTERS)
        if choice == "change domain":
            candidate["domain"] = _ask("", DOMAINS)
        if choice in {"change register", "change domain"}:
            choice = _ask("", ["accept", "reject", "skip"])
        if choice == "skip":
            continue
        if choice == "reject":
            _reject(
                candidate,
                _ask("", ["not natural Dutch", "wrong register", "too short", "not interesting"]),
                rejects,
            )
            rejected += 1
            continue

        entry = corpus.CorpusEntry.model_validate({**candidate, "id": next_id(entries)})
        append(entry, args.corpus)
        entries.append(entry)
        counts[entry.register] = counts.get(entry.register, 0) + 1
        accepted += 1
        console.ok(f"accepted as {entry.id}")

    console.say()
    console.rule()
    console.ok(f"{accepted} accepted, {rejected} rejected")
    console.note("corpus by register: " + "  ".join(f"{r} {counts.get(r, 0)}" for r in REGISTERS))
    console.note("run `make check-zeef` to see the gate's view of what you just added")
    return 0


def _reject(candidate: dict[str, Any], reason: str, path: Path) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({**candidate, "rejected_because": reason}, ensure_ascii=False) + "\n"
        )


if __name__ == "__main__":
    raise SystemExit(main())
