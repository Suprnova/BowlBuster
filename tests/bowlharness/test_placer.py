import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from test_landing import request

from bowlharness.driving import placer as placer_module
from bowlharness.driving.landing import check_recipe
from bowlharness.driving.placer import NotPlaced, Placed, PlacementFault, PlacementTool, ToolPlacer, parse_placed
from bowlharness.driving.request import LandingTest
from bowlharness.session.commands import parse_drive_arguments
from bowlharness.session.driven import pin_placer

HEAP = {"depth": 0, "states": [{"cursor": 0x5C0100, "blocks": 1, "used": 0x100, "wasted": 0}], "last_block": None}


def answering(monkeypatch: pytest.MonkeyPatch, code: int, stdout: str = "", stderr: str = "") -> list[list[str]]:
    """Makes every run of a tool exit ``code`` with the given output, and keeps the commands run."""
    commands: list[list[str]] = []

    def run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, code, stdout, stderr)

    monkeypatch.setattr(placer_module.subprocess, "run", run)
    return commands


def tool(tmp_path: Path) -> ToolPlacer:
    return ToolPlacer(PlacementTool(tmp_path / "bowlbuster.exe", "BowlBuster.Cli 1.0.0.0", "ab" * 32))


def test_the_tool_is_asked_with_the_recipe_and_the_heap_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commands = answering(monkeypatch, 0, "0x005c1000\n0x005c0400 1\n")

    placed = tool(tmp_path).place(tmp_path / "route-1", 0, 3, HEAP, 12, -24, tmp_path)

    heap_file = tmp_path / "place-heap-12.json"
    assert placed == Placed(0x5C1000, (0x5C0400, 1))
    assert commands[0][1:] == [
        *("place", "--recording", str(tmp_path / "route-1"), "--segment", "0", "--load", "3"),
        *("--heap", str(heap_file), "--op", "12", "--delta", "-24", "--top"),
    ]
    assert json.loads(heap_file.read_text(encoding="utf-8")) == HEAP


@pytest.mark.parametrize("code", [65, 66])
def test_a_load_the_tool_cannot_place_is_not_placed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    answering(monkeypatch, code, stderr="no op 12\n")

    assert tool(tmp_path).place(tmp_path, 0, 3, HEAP, 12, 0, tmp_path) == NotPlaced("no op 12")


@pytest.mark.parametrize("code", [64, 70, 1])
def test_any_other_exit_is_a_fault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    answering(monkeypatch, code, stderr="broken")

    with pytest.raises(PlacementFault, match=f"place exited {code}: broken"):
        tool(tmp_path).place(tmp_path, 0, 3, HEAP, 12, 0, tmp_path)


def test_a_placement_without_a_cutoff_has_no_top() -> None:
    assert parse_placed("0x005c1000\n") == Placed(0x5C1000, None)


@pytest.mark.parametrize("stdout", ["", "S\n", "0x1 2\n", "0x1\n0x2\n"])
def test_output_place_never_prints_is_a_fault(stdout: str) -> None:
    with pytest.raises(PlacementFault):
        parse_placed(stdout)


def test_pinning_records_the_build_and_the_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executable = tmp_path / "bowlbuster.exe"
    executable.write_bytes(b"not really a program")
    answering(monkeypatch, 0, "BowlBuster.Cli 1.0.0.0\n")

    pinned = ToolPlacer.pin(executable)

    assert pinned.tool == PlacementTool(
        executable, "BowlBuster.Cli 1.0.0.0", hashlib.sha256(b"not really a program").hexdigest()
    )


def test_a_tool_whose_version_fails_cannot_be_pinned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    answering(monkeypatch, 70, stderr="broken")

    with pytest.raises(PlacementFault, match="--version exited 70"):
        ToolPlacer.pin(tmp_path / "bowlbuster.exe")


def recipe(tmp_path: Path, platform: str) -> LandingTest:
    test = request().test
    assert isinstance(test, LandingTest)
    folder = tmp_path / test.recipe.recording
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"disc": {"platform": platform}}), encoding="utf-8")
    return test


def test_a_recipe_from_the_sessions_platform_is_accepted(tmp_path: Path) -> None:
    check_recipe(recipe(tmp_path, "xbox"), tmp_path, "xbox")


def test_a_recipe_recorded_on_another_platform_refuses_the_session(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="was recorded on ps2, not xbox"):
        check_recipe(recipe(tmp_path, "ps2"), tmp_path, "xbox")


def test_a_recipe_that_is_not_a_recording_refuses_the_session(tmp_path: Path) -> None:
    test = request().test
    assert isinstance(test, LandingTest)

    with pytest.raises(ValueError, match="is not a recording under"):
        check_recipe(test, tmp_path, "xbox")


def test_a_landing_needs_the_tool_and_the_recordings(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="a landing request needs --place and --recordings"):
        pin_placer(request(), None, tmp_path, "xbox")


def test_a_control_needs_no_tool(tmp_path: Path) -> None:
    assert pin_placer(request("control"), None, None, "xbox") is None


def test_drive_takes_the_tool_and_the_recordings() -> None:
    arguments = parse_drive_arguments(
        [
            "--out",
            str(Path.cwd() / "runs-new"),
            "--xemu",
            "x.exe",
            "--request",
            "r.json",
            "--place",
            "b.exe",
            "--recordings",
            "r",
        ],
        "run",
    )

    assert (arguments.place, arguments.recordings) == (Path("b.exe"), Path("r"))
