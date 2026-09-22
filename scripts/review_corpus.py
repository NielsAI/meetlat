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
    make review ARGS=batch.jsonl

One keystroke per decision, no Enter: `y` accept, `n` reject, `r` register, `d` domain,
`s` skip, `u` undo the last acceptance, `q` save and quit.

Accepted entries are appended to the corpus as you go, so quitting halfway loses
nothing. Rejected ones go to `<batch>.rejected.jsonl` with the reason, which is what
stops the same paragraph coming back in the next batch and says which sources are worth
collecting from.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_args

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meetlat import console, zeef  # noqa: E402  (needs the sys.path line above)
from meetlat.console import C  # noqa: E402
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
    console.line(f"{C.bold}proposed{C.reset}", indent=2)
    for label, value, meanings in (
        ("register", proposed, corpus.REGISTER_MEANS),
        ("domain", str(candidate.get("domain")), corpus.DOMAIN_MEANS),
    ):
        meaning = meanings.get(value)
        console.line(
            f"{C.dim}{label.ljust(8)}{C.reset} {C.bold}{C.cyan}{value.ljust(15)}{C.reset}"
            f"  {C.dim}{meaning.means if meaning else ''}{C.reset}",
            indent=4,
        )
    console.line(_progress(counts.get(proposed, 0), proposed), indent=4)


def _progress(count: int, register: str) -> str:
    """The register's standing against its floor, with the verdict on it in colour.

    A register already past 25 is the one fact that should change what you do next, and
    it was the least visible thing on the screen: `formal_u: 36 of 25` in the same grey
    as everything around it.
    """
    if count >= PER_REGISTER:
        standing = f"{C.green}✔ {register} has its {PER_REGISTER}{C.reset}"
        hint = f"{C.dim}, spend the time on a thinner register{C.reset}"
    else:
        standing = f"{C.yellow}{PER_REGISTER - count} more for {register}{C.reset}"
        hint = ""
    return (
        f"{bar(count)}  {C.bold}{count}{C.reset}{C.dim}/{PER_REGISTER}{C.reset}  {standing}{hint}"
    )


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


class Stopped(Exception):
    """Input ended or the reader asked to stop.

    Raised rather than returned so it unwinds out of a nested picker instead of being
    mistaken there for an answer.
    """


def key(choices: dict[str, str]) -> str:
    """One keystroke, without waiting for Enter where the terminal allows it.

    Review is hundreds of small decisions, and a decision that costs two keys costs
    twice as much. Falls back to a typed line whenever stdin is not a terminal, which
    is what makes the loop testable and pipeable rather than only usable by hand.
    """
    legend = "  ".join(
        f"{C.bold}{k}{C.reset} {C.dim}{label}{C.reset}" for k, label in choices.items()
    )
    print(f"\n  {legend}")
    while True:
        pressed = _read_key()
        # End of input, ctrl-c or ctrl-d. Without this the loop spins forever on a
        # closed stdin, which is every non-interactive run that runs out of answers.
        # Where quitting is on offer it is the answer, so the run ends with its summary
        # rather than by unwinding; inside a picker there is nothing to quit to, so it
        # gives up on the choice instead.
        if pressed is None or pressed in {"\x03", "\x04"}:
            if "q" in choices:
                return "q"
            raise Stopped
        if (chosen := pressed.lower()) in choices:
            return chosen
        console.warn(f"press one of: {', '.join(choices)}")


def _read_key() -> str | None:
    if not sys.stdin.isatty():
        line = sys.stdin.readline()
        return line.strip()[:1] if line else None
    import termios
    import tty

    descriptor = sys.stdin.fileno()
    previous = termios.tcgetattr(descriptor)
    try:
        tty.setraw(descriptor)
        return sys.stdin.read(1) or None
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


def pick(
    label: str, options: list[str], current: str, meanings: dict[str, Any] | None = None
) -> str:
    """Choose from a short list by number, with each option saying what it means.

    The names alone do not decide anything: `business` and `plain_language` are both
    unaddressed prose, and choosing between them from two words is guesswork. So each
    option carries its definition and a paragraph that is unmistakably it, which is
    the part that actually settles a borderline case.
    """
    console.say()
    console.note(f"{label}:")
    width = max(len(option) for option in options)
    for index, option in enumerate(options, start=1):
        marker = f"{C.green}●{C.reset}" if option == current else " "
        meaning = (meanings or {}).get(option)
        console.line(f"{marker} {index}  {C.bold}{option.ljust(width)}{C.reset}", indent=4)
        if meaning is not None:
            console.line(f"{C.dim}{meaning.means}{C.reset}", indent=11)
            console.line(f'{C.dim}e.g. "{meaning.like}"{C.reset}', indent=11)
    keys = {str(i): options[i - 1] for i in range(1, len(options) + 1)}
    # Opening this menu should never be able to cost you the tag you already had, so
    # there is a way out that changes nothing. Without it the only exits are picking
    # something and quitting, and a menu you cannot leave is a menu that gets answered
    # wrongly rather than left.
    legend = {**keys, "b": f"back, keep {current}" if current else "back, change nothing"}
    pressed = key(legend)
    return current if pressed == "b" else keys[pressed]


def vocabulary() -> None:
    """Both tag lists with their definitions, for when the names are not enough."""
    for label, options, meanings in (
        ("register", REGISTERS, corpus.REGISTER_MEANS),
        ("domain", DOMAINS, corpus.DOMAIN_MEANS),
    ):
        console.heading(label)
        width = max(len(option) for option in options)
        for option in options:
            meaning = meanings[option]
            console.line(f"{C.bold}{option.ljust(width)}{C.reset}  {meaning.means}", indent=2)
            console.line(f'{C.dim}e.g. "{meaning.like}"{C.reset}', indent=4 + width)


def bar(count: int, floor: int = PER_REGISTER, width: int = 12) -> str:
    filled = min(width, round(width * count / floor)) if floor else width
    colour = C.green if count >= floor else C.yellow
    return f"{colour}{'▰' * filled}{C.reset}{C.dim}{'▱' * (width - filled)}{C.reset}"


def read_candidates(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("//")
    ]


def waiting(root: Path = REPO_ROOT) -> list[Path]:
    """Batches still to be reviewed, most recently collected first.

    `*.rejected.jsonl` is this tool's own output rather than an input, so it is not
    offered back as something to review.
    """
    folder = root / "batches"
    if not folder.is_dir():
        return []
    return sorted(
        (p for p in folder.glob("*.jsonl") if not p.name.endswith(".rejected.jsonl")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def shown(path: Path) -> str:
    """The path as a person would type it back: relative to the repository root."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def describe(path: Path) -> str:
    """One line about a batch: how much work it is, and which registers it would fill."""
    try:
        rows = read_candidates(path)
    except Exception as exc:
        return f"unreadable: {exc}"
    tally = Counter(str(row.get("register", "untagged")) for row in rows)
    return f"{len(rows):3d} candidates · " + ", ".join(f"{n} {r}" for r, n in tally.most_common())


def guide(batches: list[Path], detail: str = "no batch given") -> None:
    """What to do, when the tool was run without a batch it can read."""
    console.banner("meetlat · review", detail)
    console.say()
    console.note("A batch is candidate paragraphs from `collect_corpus.py`. Reviewing one")
    console.note("is the only way text enters the corpus, because the register tag and the")
    console.note("`is this correct Dutch` call are a person's judgement (ADR-0007).")
    console.say()
    if batches:
        console.heading("Waiting to be reviewed")
        for path in batches:
            console.ok(shown(path))
            console.line(describe(path), indent=4)
        console.say()
        console.note("make review ARGS=<one of the paths above>")
    else:
        console.heading("Nothing collected yet")
        console.note("Collect some first, then review what comes back:")
        console.say()
        console.line("make corpus-sources", indent=4)
        console.line(
            "python3 scripts/collect_corpus.py --source cbs --limit 40 > batches/cbs.jsonl",
            indent=4,
        )
        console.line("make review ARGS=batches/cbs.jsonl", indent=4)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "batch", type=Path, nargs="?", help="candidate JSONL from collect_corpus.py"
    )
    parser.add_argument("--corpus", type=Path, default=corpus_path())
    args = parser.parse_args(argv)

    batches = waiting()
    if args.batch is None:
        # Not an error: forgetting the argument is the likeliest way to arrive here, and
        # an argparse usage line answers a question nobody asked.
        guide(batches)
        if not batches or not sys.stdin.isatty():
            return 0
        console.say()
        chosen = pick("review which", [shown(path) for path in batches], "")
        args.batch = REPO_ROOT / chosen

    if not args.batch.exists():
        guide(batches, f"no such batch: {shown(args.batch)}")
        return 1

    candidates = read_candidates(args.batch)
    if not candidates:
        console.warn(f"{args.batch} holds no candidates; collect some first")
        return 0
    entries = corpus.load(args.corpus)
    counts: dict[str, int] = {str(k): v for k, v in corpus.coverage(entries).items()}
    rejects = args.batch.with_suffix(".rejected.jsonl")

    console.banner("meetlat · review", f"{len(candidates)} candidate(s)")
    console.note(f"corpus: {len(entries)} entries, floor {PER_REGISTER} per register")
    console.note("nothing is accepted without a keystroke: the register tag is the judgement")

    accepted: list[str] = []
    rejected = 0
    queue = by_thinnest_register(candidates, counts)
    index = 0
    while index < len(queue):
        candidate = queue[index]
        seen = assess(str(candidate["text"]), [entry.text for entry in entries])
        render(candidate, seen, f"{index + 1} of {len(queue)}", counts)

        if seen.blocked:
            console.say()
            console.bad(f"cannot be accepted: {seen.blocked}")
            blocked_choice = key({"n": "reject", "s": "skip", "q": "quit"})
            if blocked_choice == "q":
                break
            if blocked_choice == "n":
                _reject(candidate, seen.blocked, rejects)
                rejected += 1
            index += 1
            continue

        choice = key(
            {
                "y": "accept",
                "n": "reject",
                "r": "register",
                "d": "domain",
                "s": "skip",
                "u": "undo last",
                "?": "what the tags mean",
                "q": "quit",
            }
        )
        if choice == "?":
            vocabulary()
            continue
        if choice == "q":
            break
        if choice == "s":
            index += 1
            continue
        if choice == "u":
            if not accepted:
                console.warn("nothing to undo")
                continue
            removed = _undo(args.corpus)
            entries = corpus.load(args.corpus)
            counts = {str(k): v for k, v in corpus.coverage(entries).items()}
            accepted.pop()
            console.warn(f"removed {removed} from the corpus; this candidate is unchanged")
            continue
        if choice in {"r", "d"}:
            field, options, meanings = (
                ("register", REGISTERS, corpus.REGISTER_MEANS)
                if choice == "r"
                else ("domain", DOMAINS, corpus.DOMAIN_MEANS)
            )
            before = str(candidate[field])
            try:
                candidate[field] = pick(field, options, before, meanings)
            except Stopped:
                pass
            if candidate[field] == before:
                console.note(f"{field} unchanged: {before}")
            continue
        if choice == "n":
            reasons = ["not natural Dutch", "wrong register", "not interesting", "a duplicate idea"]
            try:
                why = pick("why", reasons, "")
            except Stopped:
                break
            if not why:  # backed out of the menu: the candidate is still undecided
                continue
            _reject(candidate, why, rejects)
            rejected += 1
            index += 1
            continue

        entry = corpus.CorpusEntry.model_validate({**candidate, "id": next_id(entries)})
        append(entry, args.corpus)
        entries.append(entry)
        counts[entry.register] = counts.get(entry.register, 0) + 1
        accepted.append(entry.id)
        console.ok(
            f"accepted as {entry.id}  ({entry.register} {counts[entry.register]}/{PER_REGISTER})"
        )
        index += 1

    console.say()
    console.rule()
    console.ok(f"{len(accepted)} accepted, {rejected} rejected, {len(queue) - index} not reached")
    for register in REGISTERS:
        count = counts.get(register, 0)
        console.line(f"{bar(count)}  {register.ljust(15)}{count} of {PER_REGISTER}", indent=2)
    console.note("run `make check-zeef` to see the gate's view of what you just added")
    return 0


def _undo(path: Path) -> str:
    """Remove the paragraph accepted most recently and say which it was.

    Accepting is an append, so undoing is dropping the last line. It earns its key:
    tagging a register wrongly is the mistake this loop makes easiest to make and the
    most tedious to find later, when it is one line among two hundred.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    while lines and (not lines[-1].strip() or lines[-1].lstrip().startswith("//")):
        lines.pop()
    removed = str(json.loads(lines.pop())["id"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return removed


def _reject(candidate: dict[str, Any], reason: str, path: Path) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({**candidate, "rejected_because": reason}, ensure_ascii=False) + "\n"
        )


if __name__ == "__main__":
    raise SystemExit(main())
