#!/usr/bin/env python3
"""Refuse a judge that is not entitled to the numbers on its card (ADR-0003, ADR-0004).

A judge is a versioned artifact: a prompt, a pinned model and temperature, and the
agreement figures from its last calibration. Two rules govern it, and both are the
kind that get broken by accident rather than by decision:

  * **A judge whose prompt changed is a new judge.** The card carries the sha256 of
    the prompt it was calibrated against. Edit the prompt and the build fails, so the
    numbers cannot quietly come to describe a judge that no longer exists.
  * **A judge below threshold does not report numbers.** Balanced accuracy and
    Cohen's kappa are recomputed here from the gold set's reconciled labels and the
    run's verdicts, and compared against what the card claims. A card cannot hold a
    figure its own evidence does not support, whether by typo or by optimism.

`audit()` is the whole gate and takes a repository root, so `tests/test_judge_gate.py`
can build a valid judge in a temp directory and break it one way at a time. A gate
nobody tests is a gate that rots, and this one guards the claim the project rests on.

Exits 1 on any finding. An empty `judges/` passes: nothing calibrated yet is an
honest state, and it is the state this repository starts in.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meetlat import console  # noqa: E402  (needs the sys.path line above)
from meetlat.ijk import agreement, gold  # noqa: E402
from meetlat.keuring import card as card_schema  # noqa: E402
from meetlat.keuring import verdicts as verdict_log  # noqa: E402

TOLERANCE = 5e-5


@dataclass(frozen=True)
class Finding:
    where: str
    what: str


def _audit_one(judge_dir: Path, repo_root: Path, out: list[Finding]) -> None:
    where = str(judge_dir.relative_to(repo_root))
    card_path = judge_dir / "card.json"
    prompt_path = judge_dir / "prompt.md"

    for required in (card_path, prompt_path):
        if not required.exists():
            out.append(Finding(where, f"no {required.name}"))
            return

    try:
        card = card_schema.load(card_path)
    except Exception as exc:
        out.append(Finding(f"{where}/card.json", f"invalid card: {exc}"))
        return

    if judge_dir.name != f"v{card.version}" or judge_dir.parent.name != card.criterion:
        out.append(Finding(where, f"path does not match card ({card.criterion} v{card.version})"))

    actual_digest = card_schema.prompt_digest(prompt_path)
    if actual_digest != card.prompt_sha256:
        out.append(
            Finding(
                f"{where}/prompt.md",
                "prompt has changed since calibration, so this is a new judge: bump the "
                f"version and recalibrate (card says {card.prompt_sha256[:12]}…, "
                f"prompt hashes to {actual_digest[:12]}…)",
            )
        )

    gold_path = repo_root / card.calibration.gold_set
    verdict_path = judge_dir / card.calibration.verdicts
    try:
        items = gold.load(gold_path)
        answers = verdict_log.load(verdict_path)
    except (OSError, ValueError) as exc:
        out.append(Finding(where, f"calibration evidence unreadable: {exc}"))
        return

    if len(items) != card.calibration.items:
        out.append(
            Finding(where, f"card claims {card.calibration.items} items, gold set has {len(items)}")
        )
    if {i.id for i in items} != set(answers):
        out.append(Finding(where, "the verdict log and the gold set cover different items"))
        return
    if len({i.interaction_type for i in items}) < 2:
        out.append(
            Finding(
                where,
                "the gold set covers one interaction type; stratify it, or the number "
                "says nothing about the traffic it will be applied to",
            )
        )

    try:
        recomputed = agreement.score([i.reconciled for i in items], [answers[i.id] for i in items])
    except agreement.NotEnoughEvidence as exc:
        out.append(Finding(where, f"agreement cannot be computed: {exc}"))
        return

    for metric in ("balanced_accuracy", "cohen_kappa"):
        claimed = getattr(card.calibration, metric)
        actual = getattr(recomputed, metric)
        if abs(claimed - actual) > TOLERANCE:
            out.append(Finding(where, f"card claims {metric}={claimed}, the labels give {actual}"))

    if card.status == "certified" and not card.meets_thresholds():
        out.append(
            Finding(
                where,
                f"certified below threshold: balanced_accuracy={card.calibration.balanced_accuracy} "
                f"(needs {card.thresholds.balanced_accuracy}), "
                f"cohen_kappa={card.calibration.cohen_kappa} "
                f"(needs {card.thresholds.cohen_kappa}). A judge below threshold goes back "
                "to prompt revision; it does not report numbers",
            )
        )


def audit(repo_root: Path) -> list[Finding]:
    """Every finding against every judge under `<repo_root>/judges/`."""
    out: list[Finding] = []
    for card_path in sorted((repo_root / "judges").glob("*/v*/card.json")):
        _audit_one(card_path.parent, repo_root, out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root to audit")
    args = parser.parse_args(argv)

    findings = audit(args.root)
    if not findings:
        count = len(list((args.root / "judges").glob("*/v*/card.json")))
        console.ok(
            f"judges ok · {count} calibrated" if count else "judges ok · none calibrated yet"
        )
        return 0

    console.heading("judges that may not report numbers (ADR-0003, ADR-0004)", stderr=True)
    for finding in findings:
        console.err(f"{console.CE.bold}{finding.where}{console.CE.reset}: {finding.what}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
