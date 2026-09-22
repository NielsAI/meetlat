"""`meetlat` on the command line.

The zeef needs no endpoint, no key and no budget, so it is usable the moment the
package is installed: pipe it Dutch text and it names what is wrong and where. The
runner that drives an OpenAI-compatible endpoint is a later subcommand; this stays
the single entry point so there is one place to look.

Human output goes through `meetlat.console`, never through a bare `print` with a
colour code in it. `--json` is the other half of that rule: a machine reads the JSON,
a person reads the rendering, and neither format is bent to serve the other.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from meetlat import console, zeef
from meetlat.console import C
from meetlat.types import CheckResult, Finding, Span, ZeefReport

#: Past this, a report stops being readable and starts being a wall. The count is
#: always reported in full; only the excerpts are capped.
DEFAULT_MAX_FINDINGS = 5

#: Characters of context kept on either side of a span in an excerpt.
_CONTEXT = 24


def _line_and_column(text: str, offset: int) -> tuple[int, int, int]:
    """1-based line and column, plus the offset the line starts at."""
    line_start = text.rfind("\n", 0, offset) + 1
    return text.count("\n", 0, offset) + 1, offset - line_start + 1, line_start


def _excerpt(text: str, span: Span) -> tuple[str, str]:
    """The span's line, trimmed around it, and a caret line marking it.

    The caret is drawn even when the terminal has colour. An excerpt someone pastes
    into an issue or a log loses the colour and keeps the carets.
    """
    _, _, line_start = _line_and_column(text, span.start)
    line_end = text.find("\n", span.start)
    line_end = len(text) if line_end == -1 else line_end
    line = text[line_start:line_end]

    col = span.start - line_start
    span_end = min(span.end, line_end) - line_start
    window_start = max(0, col - _CONTEXT)
    window_end = min(len(line), span_end + _CONTEXT)

    prefix = "…" if window_start > 0 else ""
    suffix = "…" if window_end < len(line) else ""
    shown = prefix + line[window_start:window_end] + suffix
    carets = " " * (len(prefix) + col - window_start) + "^" * max(1, span_end - col)
    return shown, carets


def _render_findings(report: ZeefReport, result: CheckResult, limit: int) -> None:
    for finding in result.findings[:limit]:
        line, column, _ = _line_and_column(report.text, finding.span.start)
        console.line(f"{C.cyan}{line}:{column}{C.reset}  {finding.message}", indent=6)
        shown, carets = _excerpt(report.text, finding.span)
        console.line(f"{C.dim}{shown}{C.reset}")
        console.line(f"{C.red}{carets}{C.reset}")
    if len(result.findings) > limit:
        console.line(f"{C.dim}… and {len(result.findings) - limit} more{C.reset}", indent=6)


def render(report: ZeefReport, source: str, limit: int) -> None:
    console.banner("meetlat · zeef", source)
    for result in report.results:
        if result.kind == "distribution":
            numbers = "  ".join(f"{k} {v:g}" for k, v in result.metrics.items())
            console.stat(f"{result.check:<24}{numbers}")
        elif result.findings:
            count = len(result.findings)
            console.bad(f"{result.check:<24}{count} finding{'s' if count != 1 else ''}")
            _render_findings(report, result, limit)
        else:
            console.ok(result.check)

    print()
    total = len(report.findings)
    if report.passed:
        console.ok(f"{C.bold}zeef passed{C.reset} · {len(report.results)} checks, no findings")
    else:
        console.bad(
            f"{C.bold}zeef failed{C.reset} · {len(report.failed_checks)} of "
            f"{len(report.results)} checks · {total} finding{'s' if total != 1 else ''}"
        )


def _as_dict(report: ZeefReport) -> dict[str, object]:
    def finding(f: Finding) -> dict[str, object]:
        return {
            "message": f.message,
            "span": {"start": f.span.start, "end": f.span.end, "text": f.span.text},
        }

    return {
        "passed": report.passed,
        "failed_checks": list(report.failed_checks),
        "results": [
            {
                "check": r.check,
                "kind": r.kind,
                "metrics": dict(r.metrics),
                "findings": [finding(f) for f in r.findings],
            }
            for r in report.results
        ],
    }


def _list_checks() -> int:
    console.banner(
        "meetlat · checks",
        f"{len(zeef.CHECKS)} registered, {len(zeef.PLANNED)} designed but not built",
    )
    console.table(
        [(c.name, c.kind, c.description) for c in zeef.CHECKS]
        + [(name, "planned", blocker) for name, blocker in zeef.PLANNED.items()]
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="meetlat",
        description="Score free-form Dutch text generation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_zeef = sub.add_parser("zeef", help="run the deterministic checks over Dutch text")
    run_zeef.add_argument("path", nargs="?", type=Path, help="file to read; omit to read stdin")
    run_zeef.add_argument("--only", action="append", default=[], metavar="CHECK")
    run_zeef.add_argument("--json", action="store_true", help="machine-readable output")
    run_zeef.add_argument(
        "--max-findings",
        type=int,
        default=DEFAULT_MAX_FINDINGS,
        metavar="N",
        help=f"excerpts shown per check (default {DEFAULT_MAX_FINDINGS}; 0 for all)",
    )

    sub.add_parser("checks", help="list the registered checks and the designed ones")

    args = parser.parse_args(argv)
    if args.command == "checks":
        return _list_checks()

    text = args.path.read_text(encoding="utf-8") if args.path else sys.stdin.read()
    try:
        report = zeef.run(text, only=tuple(args.only))
    except KeyError as exc:
        console.fail(str(exc).strip("'"))

    if args.json:
        print(json.dumps(_as_dict(report), indent=2, ensure_ascii=False))
    else:
        render(
            report,
            str(args.path) if args.path else "stdin",
            args.max_findings or len(report.findings) or 1,
        )
    # Exit 1 on a verdict failure so the command composes into a shell pipeline.
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
