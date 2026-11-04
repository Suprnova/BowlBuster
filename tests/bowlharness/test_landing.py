import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from contract import schema_errors
from scripted import PAD_BUFFER, ScriptedGame
from support import FAST, PAUSE_MENU, drive, driven_events, level, polls

from bowlharness.driving.placer import NotPlaced, Placed, PlacementFault, PlacementTool
from bowlharness.driving.request import Request, parse_request
from bowlharness.profiles import XBOX_NTSC_U

S = FAST.heap.heap0_base + 0x10
OFFSET = 0x30
WINDOW = bytes(range(0x40, 0x50))
SPHERE = FAST.globals.sphere
STORAGE = FAST.bowl_storage


@dataclass
class FakePlacer:
    """Places every landing where it was told to, and remembers what it was asked."""

    answer: Placed | NotPlaced | Exception
    tool: PlacementTool | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def place(
        self, recipe: Path, segment: int, load: int, heap: dict[str, Any], op: int, delta: int, folder: Path
    ) -> Placed | NotPlaced:
        self.calls.append({"recipe": recipe, "segment": segment, "load": load, "heap": heap, "op": op, "delta": delta})
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def request(kind: str = "landing", expected: bytes = WINDOW, render: int = 5) -> Request:
    test: dict[str, Any] = {"step": 1}
    if kind == "landing":
        test |= {
            "recipe": {"recording": "route-1/s-1", "segment": 0, "load": 2},
            "op": 7,
            "delta": -8,
            "expected": {"offset": OFFSET, "bytes": expected.hex()},
        }
    document = {
        "schema_version": 1,
        "request_id": "landing-targ-1",
        "kind": kind,
        "start": {"from": "booted"},
        "steps": [
            {"scene": "ORIG"},
            {"scene": "TARG", "menu": {"world": 2, "slot": 1}},
            {"scene": "EXIT", "menu": {"world": 3, "slot": 1}},
        ],
        "tests": [test],
        "windows": {"render": {"unit": "guest-frames", "value": render}},
    }
    return parse_request(document, XBOX_NTSC_U)


def trip(game: ScriptedGame, cursor: tuple[int, int], scene: str, counter: int, old: str) -> None:
    """Start, the cursor's press, A three times, and the load of ``scene`` up to its scene init."""
    game.await_press("start", after=PAUSE_MENU)
    game.await_press("down", cursor=cursor, mode=PAUSE_MENU)
    for _ in range(3):
        game.await_press("a", mode=PAUSE_MENU, after=PAUSE_MENU)
    game.scene_exit(old, counter - 1)
    game.scene_init(scene, counter)


def landing_game(*, scale_zero: bool = False, stale: int | None = None) -> ScriptedGame:
    """A route from ORIG to the target TARG, where the render writes through the sphere, and on to EXIT."""
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG", (2, 0): "EXIT"})
    level(game, "ORIG", 1)
    trip(game, (1, 0), "TARG", 2, "ORIG")
    if scale_zero:
        game.watch(STORAGE.scale, 0)
    game.players_done()
    game.drawn()
    game.stale_write(stale)
    polls(game, 40)
    trip(game, (2, 0), "EXIT", 3, "TARG")
    game.players_done()
    polls(game, 12)
    return game


def result(directory: Path) -> dict[str, Any]:
    return json.loads((directory / "out" / "result.json").read_text(encoding="utf-8"))


def harness_writes(session: Any) -> list[tuple[int, bytes]]:
    return [(address, data) for address, data in session._target.writes if address != PAD_BUFFER]


def test_a_placed_landing_writes_the_sphere_and_the_flag_at_players_done_and_nothing_else(tmp_path: Path) -> None:
    game = landing_game()

    session, manifest = drive(game, tmp_path, request(), FakePlacer(Placed(S, (0x5C0400, 1))))

    players_done = FAST.points.players_done.entry[0]
    stops = [
        stop
        for (address, _), stop in zip(session._target.writes, session._target.write_stops, strict=True)
        if address != PAD_BUFFER
    ]
    assert harness_writes(session) == [(SPHERE, struct.pack("<I", S)), (STORAGE.flag, bytes([STORAGE.flag_set]))]
    assert stops == [players_done, players_done]
    assert [row["target"] for row in manifest["write_ledger"]] == ["sphere", "flag"]


def test_the_first_stale_write_reports_the_placed_sphere(tmp_path: Path) -> None:
    drive(landing_game(), tmp_path, request(), FakePlacer(Placed(S, (0x5C0400, 1))))

    written = result(tmp_path)
    placement = written["placement"]
    assert (written["outcome"], placement["s"], placement["first_write"]["s"], placement["match"]) == (
        "survived",
        S,
        S,
        1.0,
    )
    assert (placement["predicted_top"], placement["live_top"]["depth"]) == ({"cursor": 0x5C0400, "depth": 1}, 0)
    assert schema_errors(written, "result") == []


def test_the_placer_is_given_the_targets_heap_and_the_recipe(tmp_path: Path) -> None:
    placer = FakePlacer(Placed(S, None))

    drive(landing_game(), tmp_path, request(), placer)

    (call,) = placer.calls
    assert (call["recipe"], call["segment"], call["load"], call["op"], call["delta"]) == (
        tmp_path / "recordings" / "route-1" / "s-1",
        0,
        2,
        7,
        -8,
    )
    assert call["heap"] == result(tmp_path)["placement"]["heap"]


def test_a_scale_at_or_below_the_threshold_is_written_too(tmp_path: Path) -> None:
    session, _ = drive(landing_game(scale_zero=True), tmp_path, request(), FakePlacer(Placed(S, None)))

    assert harness_writes(session)[-1] == (STORAGE.scale, struct.pack("<f", STORAGE.scale_value))


def test_a_window_below_the_match_fraction_is_a_layout_mismatch_with_nothing_written(tmp_path: Path) -> None:
    session, _ = drive(landing_game(), tmp_path, request(expected=bytes(16)), FakePlacer(Placed(S, None)))

    written = result(tmp_path)
    assert (written["outcome"], written["memory"]["live_window"], harness_writes(session)) == (
        "layout mismatch",
        WINDOW.hex(),
        [],
    )
    assert schema_errors(written, "result") == []


def test_a_landing_the_placer_cannot_place_is_not_placed_with_nothing_written(tmp_path: Path) -> None:
    session, _ = drive(landing_game(), tmp_path, request(), FakePlacer(NotPlaced("no op 7")))

    written = result(tmp_path)
    assert (written["outcome"], written["placement"]["s"], harness_writes(session)) == ("not placed", None, [])
    assert schema_errors(written, "result") == []


def test_a_placer_fault_interrupts_the_run_with_the_fault_as_its_cause(tmp_path: Path) -> None:
    drive(landing_game(), tmp_path, request(), FakePlacer(PlacementFault("place exited 70: broken build")))

    written = result(tmp_path)
    assert (written["outcome"], written["cause"]) == ("interrupted", "harness fault: place exited 70: broken build")


def test_a_stale_write_through_another_pointer_is_a_harness_fault(tmp_path: Path) -> None:
    drive(landing_game(stale=S + 4), tmp_path, request(), FakePlacer(Placed(S, None)))

    written = result(tmp_path)
    assert written["outcome"] == "interrupted" and "not the placed" in written["cause"]


def test_a_control_writes_nothing_and_goes_on_to_the_exit(tmp_path: Path) -> None:
    session, manifest = drive(landing_game(), tmp_path, request("control"))

    written = result(tmp_path)
    assert (written["outcome"], written["placement"], harness_writes(session)) == ("survived", None, [])
    assert [step["status"] for step in manifest["steps"]] == ["reached"] * 3
    assert schema_errors(written, "result") == []


def test_the_test_step_is_held_for_its_render_window_after_players_done(tmp_path: Path) -> None:
    _, manifest = drive(landing_game(), tmp_path, request("control", render=25))

    events = driven_events(tmp_path)
    target = next(
        index for index, event in enumerate(events) if event["event"] == "scene_init" and event["scene"] == "TARG"
    )
    players_done = next(event["frame"] for event in events[target:] if event["event"] == "players_done")
    assert manifest["steps"][1]["frame"] >= players_done + 25


def test_the_result_records_the_pinned_tool(tmp_path: Path) -> None:
    tool = PlacementTool(Path("C:/tools/bowlbuster.exe"), "BowlBuster.Cli 1.0.0.0", "ab" * 32)

    drive(landing_game(), tmp_path, request(), FakePlacer(Placed(S, None), tool))

    assert result(tmp_path)["manifest"]["placement_tool"] == {
        "path": str(tool.path),
        "build": tool.build,
        "sha256": tool.sha256,
    }
