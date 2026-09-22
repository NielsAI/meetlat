"""The command a person actually runs: exit codes, and output that survives a pipe."""

from __future__ import annotations

import json

import pytest

from meetlat import cli

CLEAN = "Wij hebben uw aanvraag ontvangen en nemen binnen vijf werkdagen contact met u op."
MIXED = "Beste klant, u kunt uw bestelling annuleren. Laat maar weten of jij dat wilt."


def test_clean_text_exits_zero(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    path = tmp_path / "response.txt"
    path.write_text(CLEAN, encoding="utf-8")
    assert cli.main(["zeef", str(path)]) == 0
    assert "zeef passed" in capsys.readouterr().out


def test_a_defect_exits_one(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    path = tmp_path / "response.txt"
    path.write_text(MIXED, encoding="utf-8")
    assert cli.main(["zeef", str(path)]) == 1
    assert "register_consistency" in capsys.readouterr().out


def test_no_escape_codes_when_output_is_captured(
    capsys: pytest.CaptureFixture[str], tmp_path
) -> None:
    """The rule the console module exists for: never write colour into a file or a log."""
    path = tmp_path / "response.txt"
    path.write_text(MIXED, encoding="utf-8")
    cli.main(["zeef", str(path)])
    assert "\033[" not in capsys.readouterr().out


def test_json_is_the_machine_half(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    path = tmp_path / "response.txt"
    path.write_text(MIXED, encoding="utf-8")
    cli.main(["zeef", str(path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is False
    assert "register_consistency" in payload["failed_checks"]
    spans = [f["span"] for r in payload["results"] for f in r["findings"]]
    assert all(MIXED[s["start"] : s["end"]] == s["text"] for s in spans)


def test_only_narrows_to_one_check(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    path = tmp_path / "response.txt"
    path.write_text(MIXED, encoding="utf-8")
    cli.main(["zeef", str(path), "--only", "translationese", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert [r["check"] for r in payload["results"]] == ["translationese"]


def test_an_unknown_check_fails_loudly(tmp_path) -> None:
    path = tmp_path / "response.txt"
    path.write_text(CLEAN, encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(["zeef", str(path), "--only", "geen_check"])


def test_checks_lists_the_planned_ones(capsys: pytest.CaptureFixture[str]) -> None:
    """A gap in the designed set is visible, not an absence nobody noticed."""
    assert cli.main(["checks"]) == 0
    out = capsys.readouterr().out
    assert "anglicism_density" in out and "planned" in out
