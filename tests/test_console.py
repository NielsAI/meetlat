"""The design system's one hard rule: nothing decorative reaches a non-terminal.

Every other module prints through this one, so a regression here quietly corrupts
every report, log and CI transcript the project produces.
"""

from __future__ import annotations

import io
import time

import pytest

from meetlat import console


def test_a_captured_stream_gets_no_colour_and_no_animation() -> None:
    palette = console.Palette.for_stream(io.StringIO())
    assert palette.reset == ""
    assert palette.accent == ""
    assert palette.animated is False


def test_no_color_wins_over_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert console.Palette.for_stream(io.StringIO()) == console.Palette()


def test_forced_colour_still_refuses_to_animate(monkeypatch: pytest.MonkeyPatch) -> None:
    """FORCE_COLOR captures colour into a file; a redrawn line there is a smear."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    palette = console.Palette.for_stream(io.StringIO())
    assert palette.reset != ""
    assert palette.animated is False


def test_the_spinner_writes_nothing_to_a_captured_stream() -> None:
    stream = io.StringIO()
    with console.Spinner("werk", stream=stream):
        time.sleep(console.Spinner.INTERVAL * 3)
    assert stream.getvalue() == ""


def test_the_spinner_reports_how_long_it_ran() -> None:
    with console.Spinner("werk", stream=io.StringIO()) as spinner:
        time.sleep(0.05)
    assert spinner.elapsed >= 0.05


@pytest.mark.parametrize(
    "seconds,expected",
    [(0.0, "0.0s"), (0.44, "0.4s"), (59.9, "59.9s"), (60.0, "1m00s"), (72.4, "1m12s")],
)
def test_duration(seconds: float, expected: str) -> None:
    assert console.duration(seconds) == expected


def test_box_quotes_every_line_of_the_output(capsys: pytest.CaptureFixture[str]) -> None:
    """On stdout by default: it is part of the report the step lines above it belong to."""
    console.box("eerste regel\ntweede regel", title="make lint")
    captured = capsys.readouterr()
    assert "make lint" in captured.out
    assert "  eerste regel" in captured.out
    assert captured.err == ""
    assert "\033[" not in captured.out


def test_skip_and_verdict_stay_plain_when_captured(capsys: pytest.CaptureFixture[str]) -> None:
    console.skip("secrets", "gitleaks not installed", width=10)
    console.verdict(False, "pre-commit blocked")
    captured = capsys.readouterr()
    assert "○ secrets" in captured.out
    assert "✘ pre-commit blocked" in captured.out
    assert "\033[" not in captured.out


def test_wrap_breaks_at_spaces_and_hangs_under_its_first_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A long line used to continue at column 0, which reads as a new statement."""
    console.wrap("een twee drie vier vijf zes zeven acht negen tien elf twaalf " * 4, indent=4)
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) > 1
    assert all(line.startswith("    ") for line in lines)
    assert all(len(line) <= 100 for line in lines)
    assert not any(line.strip().endswith("-") for line in lines)


def test_field_keeps_the_figure_out_of_the_label(capsys: pytest.CaptureFixture[str]) -> None:
    """The point of `field`: a captured stream still reads as a pair, with no colour."""
    print(console.field("paragraphs", 190))
    assert capsys.readouterr().out.strip() == "paragraphs 190"


def test_settings_holds_no_rule_that_belongs_with_its_code() -> None:
    """The line this module draws, asserted so it does not become a junk drawer.

    A value that encodes a rule stays next to the code enforcing it, with the reasoning
    a reader needs where they meet it. `MIN_CHARS` and `PER_REGISTER` are read by the
    collector, the reviewer and the gate and must be one number; `REDISTRIBUTABLE` is a
    licensing decision. Settings are operating conditions, not decisions.
    """
    from meetlat import settings

    names = {n for n in vars(settings) if n.isupper()}
    for rule in ("MIN_CHARS", "MAX_CHARS", "PER_REGISTER", "SIMILARITY", "REDISTRIBUTABLE"):
        assert rule not in names, f"{rule} is a rule and belongs with the code enforcing it"
