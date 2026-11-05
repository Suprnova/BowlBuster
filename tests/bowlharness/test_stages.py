import json
from pathlib import Path
from typing import Any

from contract import schema_errors
from scripted import COMPACT, ScriptedGame
from support import FAST, PAUSE_MENU, drive, driven_events, level, polls
from test_landing import OFFSET, WINDOW, FakePlacer, S, trip

from bowlharness.driving.placer import Placed
from bowlharness.driving.request import Request, parse_request

FRAMES = "guest-frames"


def request(kind: str = "landing", *, render: int = 5, timeout: int = 200, exits: bool = True, **test: Any) -> Request:
    entry: dict[str, Any] = {"step": 1}
    if kind == "landing":
        entry |= {
            "recipe": {"recording": "route-1/s-1", "segment": 0, "load": 2},
            "op": 7,
            "delta": -8,
            "expected": {"offset": OFFSET, "bytes": WINDOW.hex()},
        } | test
    steps = [{"scene": "ORIG"}, {"scene": "TARG", "menu": {"world": 2, "slot": 1}}]
    if exits:
        steps.append({"scene": "EXIT", "menu": {"world": 3, "slot": 1}})
    document = {
        "schema_version": 1,
        "request_id": "landing-targ-1",
        "kind": kind,
        "start": {"from": "booted"},
        "steps": steps,
        "tests": [entry],
        "windows": {
            "render": {"unit": FRAMES, "value": render},
            "reset": {"unit": FRAMES, "value": 10},
            "write_timeout": {"unit": FRAMES, "value": timeout},
        },
    }
    return parse_request(document, COMPACT)


def at_target() -> ScriptedGame:
    """ORIG, then the warp to TARG and its load up to players done."""
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG", (2, 0): "EXIT"})
    level(game, "ORIG", 1)
    trip(game, (1, 0), "TARG", 2, "ORIG")
    game.players_done()
    game.pad_poll()
    return game


def to_exit(game: ScriptedGame) -> ScriptedGame:
    trip(game, (2, 0), "EXIT", 3, "TARG")
    game.players_done()
    polls(game, 12)
    return game


def result(directory: Path) -> dict[str, Any]:
    return json.loads((directory / "out" / "result.json").read_text(encoding="utf-8"))


def stages(directory: Path) -> list[tuple[str, str]]:
    return [(stage["stage"], stage["status"]) for stage in result(directory)["stages"]]


def placer() -> FakePlacer:
    return FakePlacer(Placed(S, None))


def test_a_survived_landing_goes_through_its_stages_in_order(tmp_path: Path) -> None:
    game = at_target()
    game.drawn()
    game.stale_write()
    polls(game, 40)

    drive(to_exit(game), tmp_path, request(), placer())

    assert stages(tmp_path) == [
        ("loading", "complete"),
        ("held", "complete"),
        ("in control", "complete"),
        ("render", "complete"),
        ("exit", "complete"),
    ]
    assert result(tmp_path)["outcome"] == "survived"
    assert schema_errors(result(tmp_path), "result") == []


def test_each_stage_change_is_a_stage_event(tmp_path: Path) -> None:
    game = at_target()
    game.drawn()
    game.stale_write()
    polls(game, 40)

    drive(to_exit(game), tmp_path, request(), placer())

    changes = [(event["stage"], event["status"]) for event in driven_events(tmp_path) if event["event"] == "stage"]
    assert changes[:3] == [("loading", "open"), ("loading", "complete"), ("held", "open")]


def test_a_landing_with_no_stale_write_by_the_timeout_ends_no_write(tmp_path: Path) -> None:
    game = at_target()
    game.drawn()
    polls(game, 60)

    drive(game, tmp_path, request(timeout=30), placer())

    written = result(tmp_path)
    assert (written["outcome"], [capture["trigger"] for capture in written["captures"]]) == ("no write", ["no-write"])
    assert schema_errors(written, "result") == []


def test_a_run_whose_player_never_has_control_ends_no_control(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG", (2, 0): "EXIT"})
    level(game, "ORIG", 1)
    trip(game, (1, 0), "TARG", 2, "ORIG")
    game.players_done()
    game.drawn()
    for _ in range(60):
        game.pad_poll(control_off=2)

    drive(game, tmp_path, request("control", timeout=40))

    assert result(tmp_path)["outcome"] == "no control"


def test_a_controls_render_window_starts_at_the_draw(tmp_path: Path) -> None:
    game = at_target()
    polls(game, 3)
    game.drawn()
    drawn = game.frame
    polls(game, 40)

    drive(to_exit(game), tmp_path, request("control"))

    render = next(stage for stage in result(tmp_path)["stages"] if stage["stage"] == "render")
    assert render["from"] == drawn


def test_the_windows_are_recorded_as_configured_and_as_taken(tmp_path: Path) -> None:
    game = at_target()
    game.drawn()
    game.stale_write()
    polls(game, 40)

    drive(to_exit(game), tmp_path, request(render=7), placer())

    windows = result(tmp_path)["manifest"]["windows"]
    assert (windows["render"]["configured"], windows["render"]["frames"]) == ({"unit": FRAMES, "value": 7}, 7)
    assert windows["write_timeout"]["frames"] == 3 and windows["reset"]["frames"] is None


def test_only_the_first_reset_opens_the_reset_window_and_it_ends_the_render_window(tmp_path: Path) -> None:
    game = at_target()
    game.drawn()
    game.stale_write()
    polls(game, 2)
    game.reset()
    polls(game, 3)
    game.reset()
    polls(game, 40)

    drive(to_exit(game), tmp_path, request(render=50), placer())

    written = result(tmp_path)
    assert [stage for stage, _ in stages(tmp_path)].count("reset") == 1
    assert (len(written["resets"]), written["resets"][0]["cause"]) == (2, "game")
    render = next(stage for stage in written["stages"] if stage["stage"] == "render")
    assert render["to"] == written["resets"][0]["frame"]


def test_a_crash_in_the_render_window_is_a_render_crash(tmp_path: Path) -> None:
    game = at_target()
    game.drawn()
    game.stale_write()
    polls(game, 2)
    game.bugcheck("KeBugCheckEx", 0x1E, 0xC0000005, 0x182BC5, 1, 0x41414140)

    drive(game, tmp_path, request(render=50), placer())

    written = result(tmp_path)
    assert (written["outcome"], written["crash"]["stage"]) == ("crash", "render")
    assert all(status == "cut" for stage, status in stages(tmp_path) if stage == "render")


def test_a_crash_within_a_second_of_the_games_reset_is_a_reset_crash(tmp_path: Path) -> None:
    game = at_target()
    game.drawn()
    game.stale_write()
    polls(game, 2)
    game.reset()
    polls(game, 20)
    game.bugcheck("KeBugCheckEx", 0x1E, 0xC0000005, 0x182BC5, 1, 0x41414140)

    drive(game, tmp_path, request(render=50), placer())

    assert result(tmp_path)["crash"]["stage"] == "reset"


def test_a_crash_after_the_windows_is_an_exit_crash(tmp_path: Path) -> None:
    game = at_target()
    game.drawn()
    game.stale_write()
    polls(game, 40)
    game.await_press("start", after=PAUSE_MENU)
    game.bugcheck("KeBugCheckEx", 0x1E, 0xC0000005, 0x182BC5, 1, 0x41414140)

    drive(game, tmp_path, request(), placer())

    assert result(tmp_path)["crash"]["stage"] == "exit"


def test_an_exit_the_menu_cannot_reach_fails_the_exit_stage_and_not_the_run(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG", (2, 0): "ELSE"})
    level(game, "ORIG", 1)
    trip(game, (1, 0), "TARG", 2, "ORIG")
    game.players_done()
    game.pad_poll()
    game.drawn()
    game.stale_write()
    polls(game, 40)

    drive(game, tmp_path, request(), placer())

    written = result(tmp_path)
    exit_stage = written["stages"][-1]
    assert (written["outcome"], exit_stage["stage"], exit_stage["status"], exit_stage["reason"]) == (
        "survived",
        "exit",
        "failed",
        "menu unreachable",
    )


def test_a_test_step_with_no_exit_step_ends_after_its_windows_with_no_exit_stage(tmp_path: Path) -> None:
    game = at_target()
    game.drawn()
    game.stale_write()
    polls(game, 40)

    drive(game, tmp_path, request(exits=False), placer())

    assert result(tmp_path)["outcome"] == "survived"
    assert "exit" not in [stage for stage, _ in stages(tmp_path)]


def test_more_than_three_resets_flag_the_run(tmp_path: Path) -> None:
    game = at_target()
    game.drawn()
    game.stale_write()
    for _ in range(4):
        polls(game, 2)
        game.reset()
    polls(game, 40)

    drive(to_exit(game), tmp_path, request(), placer())

    assert result(tmp_path)["integrity"]["flags"] == ["over 3 resets"]


def test_a_stale_write_out_of_play_flags_the_run(tmp_path: Path) -> None:
    game = at_target()
    game.drawn()
    game.pad_poll(state=0)
    game.stale_write()
    polls(game, 40)

    drive(to_exit(game), tmp_path, request(), placer())

    assert result(tmp_path)["integrity"]["flags"] == ["not in play at write"]


def test_a_match_below_0_9_flags_the_run(tmp_path: Path) -> None:
    expected = bytes([0, 0]) + WINDOW[2:]
    game = at_target()
    game.drawn()
    game.stale_write()
    polls(game, 40)

    drive(
        to_exit(game), tmp_path, request(expected={"offset": OFFSET, "bytes": expected.hex()}, min_match=0.5), placer()
    )

    written = result(tmp_path)
    assert (written["placement"]["match"], written["integrity"]["flags"]) == (0.875, ["match below 0.9"])


def test_a_clean_run_raises_no_flag(tmp_path: Path) -> None:
    game = at_target()
    game.drawn()
    game.stale_write()
    polls(game, 40)

    drive(to_exit(game), tmp_path, request(), placer())

    assert result(tmp_path)["integrity"]["flags"] == []
