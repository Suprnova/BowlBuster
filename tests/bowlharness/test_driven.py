from pathlib import Path

from scripted import ScriptedGame
from support import DIGEST, drive, driven_events, route

from bowlharness.driving.request import parse_request
from bowlharness.profiles import XBOX_NTSC_U
from bowlharness.session.session import ENDED


def loaded(scene: str = "ORIG", polls: int = 14, **poll: int) -> ScriptedGame:
    game = ScriptedGame()
    game.scene_init(scene, 1)
    game.players_done()
    for _ in range(polls):
        game.pad_poll(**poll)
    return game


def test_a_route_whose_first_step_is_ready_ends_done(tmp_path: Path) -> None:
    session, manifest = drive(loaded(), tmp_path, route("ORIG"))

    assert (session.ended, session.result) == (True, "done")
    assert (manifest["complete"], manifest["ended"], manifest["passive"], manifest["attended"]) == (
        True,
        "done",
        False,
        False,
    )
    assert (manifest["steps"][0]["status"], manifest["steps"][0]["presses"]) == ("reached", 0)
    assert manifest["write_ledger"] == []


def test_the_manifest_holds_the_request_and_the_hash_of_its_file(tmp_path: Path) -> None:
    request = route("ORIG")

    _, manifest = drive(loaded(), tmp_path, request)

    assert (manifest["request"], manifest["request_sha256"]) == (request.to_json(), DIGEST)


def test_a_step_is_an_event(tmp_path: Path) -> None:
    drive(loaded(), tmp_path, route("ORIG"))

    step = next(event for event in driven_events(tmp_path) if event["event"] == "step")
    assert (step["index"], step["scene"], step["status"], step["reason"]) == (0, "ORIG", "reached", None)


def test_a_scene_that_initialises_in_the_steps_place_fails_the_step(tmp_path: Path) -> None:
    session, manifest = drive(loaded("TARG"), tmp_path, route("ORIG"))

    assert session.result == "failed: step 0 (ORIG), scene change"
    assert (manifest["ended"], manifest["steps"][0]["status"], manifest["steps"][0]["reason"]) == (
        "failed",
        "failed",
        "scene change",
    )


def test_a_step_is_not_ready_while_the_player_is_out_of_control(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 1)
    game.players_done()
    for _ in range(5):
        game.pad_poll(control_off=2)
    returned = game.frame + 1
    for _ in range(14):
        game.pad_poll()

    _, manifest = drive(game, tmp_path, route("ORIG"))

    settle = XBOX_NTSC_U.scene_classes.other.settle_frames
    assert manifest["steps"][0]["frame"] == returned + settle


def test_a_scene_in_a_class_with_its_own_settle_count_is_ready_by_it(tmp_path: Path) -> None:
    game = loaded("FB01", polls=4)

    _, manifest = drive(game, tmp_path, route("FB01"))

    assert manifest["steps"][0]["status"] == "reached"


def test_a_new_game_start_fails_as_unsupported(tmp_path: Path) -> None:
    session, manifest = drive(loaded(), tmp_path, route("ORIG", start="new-game"))

    assert (session.result, manifest["steps"][0]["status"]) == ("failed: step 0 (ORIG), unsupported", "failed")


def test_a_crash_ends_the_recording_as_a_crash_and_leaves_the_step_unreached(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 1)
    game.bugcheck("KeBugCheckEx", 0x1E, 0xC0000005, 0x182BC5, 1, 0x41414140)

    session, manifest = drive(game, tmp_path, route("ORIG"))

    assert (session.ended, session.result, manifest["ended"]) == (True, None, "crash")
    assert manifest["steps"][0]["status"] == "not reached"


def test_a_reboot_ends_the_route(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 1)
    game.scene_init("MNUS", 1, caller=XBOX_NTSC_U.boot_return)
    game.pad_poll()

    session, manifest = drive(game, tmp_path, route("ORIG"))

    assert (session.ended, manifest["ended"]) == (True, "reboot")


def test_a_button_on_the_controller_is_a_persons_press_and_marks_the_run_attended(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 1)
    game.players_done()
    for _ in range(3):
        game.pad_poll(physical=XBOX_NTSC_U.input.buttons.a)
    for _ in range(14):
        game.pad_poll()

    _, manifest = drive(game, tmp_path, route("ORIG"))

    assert [(row["source"], row["button"]) for row in manifest["input_ledger"]] == [("person", "a")]
    assert manifest["attended"] is True


def test_a_session_that_ended_runs_no_further(tmp_path: Path) -> None:
    session, _ = drive(loaded(), tmp_path, route("ORIG"))

    assert session.run() == ENDED


def test_cheats_or_costumes_on_any_step_fail_the_route_as_unsupported(tmp_path: Path) -> None:
    request = parse_request(
        {
            "schema_version": 1,
            "request_id": "route-1",
            "kind": "record",
            "start": {"from": "booted"},
            "steps": [{"scene": "ORIG"}, {"scene": "TARG", "menu": {"world": 2, "slot": 1}, "costumes": ["PLSA"]}],
        },
        XBOX_NTSC_U,
    )

    session, manifest = drive(loaded(), tmp_path, request)

    assert (session.result, manifest["input_ledger"]) == ("failed: step 0 (ORIG), unsupported", [])
