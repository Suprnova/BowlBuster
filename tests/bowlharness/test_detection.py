import json
from pathlib import Path

from scripted import ScriptedGame
from support import names

from bowlharness.backends.mock import MockTarget
from bowlharness.recording.detection import Watchdog
from bowlharness.recording.recorder import Options, Recorder

ACCESS_VIOLATION = 0xC0000005
EXCEPTION = 0x1E


def watched(game: ScriptedGame, directory: Path, options: Options | None = None, **limits: float):
    """Starts a recording of the game under a watchdog; the caller runs the guest."""
    target = game.build(kernel_loaded=True)
    recorder = Recorder(target, game.profile, directory, "run-1", options or Options())
    recorder.start("attach")
    return recorder, target, Watchdog(recorder, **limits)


def play(target: MockTarget, watchdog: Watchdog) -> None:
    """Runs the guest in liveness windows, checking it after each, until it stops for another reason."""
    while target.run(timeout=watchdog.liveness):
        if watchdog.check():
            break


def finished(recorder: Recorder, directory: Path) -> tuple[list[dict], dict]:
    recorder.finish()
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    return events, json.loads((directory / "manifest.json").read_text())


def crash_of(game: ScriptedGame, directory: Path, options: Options | None = None) -> tuple[list[dict], dict]:
    recorder, target, _ = watched(game, directory, options)
    target.run()
    return finished(recorder, directory)


def test_an_access_violation_names_the_instruction_the_access_and_the_address(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.bugcheck("KeBugCheckEx", EXCEPTION, ACCESS_VIOLATION, 0x182BC5, 1, 0x41414140)

    events, manifest = crash_of(game, tmp_path)

    crash = manifest["crash"]
    assert (crash["kind"], crash["code"], crash["params"]) == (
        "KeBugCheckEx",
        0x1E,
        [ACCESS_VIOLATION, 0x182BC5, 1, 0x41414140],
    )
    assert (crash["instruction"], crash["access"], crash["accessed"]) == (0x182BC5, "write", 0x41414140)
    assert (crash["scene"], crash["counter"], crash["arch"]) == ("ORIG", 2, "x86")
    assert crash["registers"]["esp"] == 0x1000
    assert events[-1] == {
        "seq": events[-1]["seq"],
        "segment": 0,
        "frame": events[-1]["frame"],
        "event": "crash",
        **crash,
    }


def test_a_read_fault_is_a_read(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.bugcheck("KeBugCheckEx", EXCEPTION, ACCESS_VIOLATION, 0x182BC5, 0, 0x41414140)

    _, manifest = crash_of(game, tmp_path)

    assert manifest["crash"]["access"] == "read"


def test_a_bugcheck_with_no_parameters_has_no_fault(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.bugcheck("KeBugCheck", 0x7B)

    _, manifest = crash_of(game, tmp_path)

    crash = manifest["crash"]
    assert (crash["kind"], crash["code"], crash["params"]) == ("KeBugCheck", 0x7B, [])
    assert "instruction" not in crash and "accessed" not in crash


def test_an_exception_that_is_not_an_access_violation_names_only_the_instruction(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.bugcheck("KeBugCheckEx", EXCEPTION, 0xC000001D, 0x182BC5, 0, 0)

    _, manifest = crash_of(game, tmp_path)

    crash = manifest["crash"]
    assert (crash["instruction"], "accessed" in crash) == (0x182BC5, False)


def test_return_addresses_are_the_stack_words_after_a_call(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.bugcheck("KeBugCheckEx", EXCEPTION, ACCESS_VIOLATION, 0x182BC5, 0, 0x4, calls=(0x20010, 0x20020))

    _, manifest = crash_of(game, tmp_path)

    assert manifest["crash"]["return_addresses"] == [0x20010, 0x20020]


def test_the_crash_is_captured_and_ends_the_recording(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.bugcheck("KeBugCheckEx", EXCEPTION, ACCESS_VIOLATION, 0x182BC5, 0, 0x4)
    game.scene_init("TARG", 3)

    events, manifest = crash_of(game, tmp_path)

    assert manifest["crash"]["capture"] == "0-2-crash"
    assert (tmp_path / "captures" / "0-2-crash" / "complete").exists()
    assert names(events)[-2:] == ["capture", "crash"]
    assert [load["scene"] for load in manifest["loads"]] == ["ORIG"]


def test_a_crash_is_captured_even_when_the_budget_is_spent(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.bugcheck("KeBugCheckEx", EXCEPTION, ACCESS_VIOLATION, 0x182BC5, 0, 0x4)

    _, manifest = crash_of(game, tmp_path, Options(capture_budget=0))

    assert (manifest["crash"]["capture"], manifest["captures_dropped"]) == ("0-2-crash", [])


def test_only_one_crash_is_recorded(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.bugcheck("KeBugCheckEx", EXCEPTION, ACCESS_VIOLATION, 0x182BC5, 0, 0x4)
    game.bugcheck("KeBugCheck", 0x7B)
    recorder, target, _ = watched(game, tmp_path)

    target.run()
    target.run()
    events, _ = finished(recorder, tmp_path)

    assert names(events).count("crash") == 1


def test_a_kernel_that_loads_after_the_attach_is_watched_from_the_title_start(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.kernel_loaded()
    game.title_started()
    game.bugcheck("KeBugCheck", 0x7B)
    target = game.build()
    recorder = Recorder(target, game.profile, tmp_path, "run-1", Options())
    recorder.start("boot")

    target.run()
    _, manifest = finished(recorder, tmp_path)

    assert manifest["crash"]["code"] == 0x7B


def test_a_guest_that_makes_progress_does_not_hang(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.drawn()
    for frame in (10, 20, 30, 40):
        game.idle(5, frame)
    recorder, target, watchdog = watched(game, tmp_path)

    play(target, watchdog)
    _, manifest = finished(recorder, tmp_path)

    assert manifest["hang"] is None


def test_a_guest_that_stops_advancing_hangs(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.drawn()
    for frame in (10, 20, 20, 20, 20):
        game.idle(5, frame)
    recorder, target, watchdog = watched(game, tmp_path)

    play(target, watchdog)
    events, manifest = finished(recorder, tmp_path)

    hang = manifest["hang"]
    assert (hang["stalled"], hang["last_frame"], hang["capture"]) == (5.0, 20, "0-2-hang")
    assert (hang["scene"], hang["counter"], hang["last_event"]["event"]) == ("ORIG", 2, "drawn")
    assert names(events)[-2:] == ["capture", "hang"]


def test_events_count_as_progress(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    for _ in range(4):
        game.idle(5, 0)
        game.grow(0, 0x20)
    recorder, target, watchdog = watched(game, tmp_path)

    play(target, watchdog)
    _, manifest = finished(recorder, tmp_path)

    assert manifest["hang"] is None


def test_a_load_is_given_longer_to_stall_than_play(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    for _ in range(4):
        game.idle(5, 0)
    recorder, target, watchdog = watched(game, tmp_path, load_limit=20.0)

    play(target, watchdog)
    _, manifest = finished(recorder, tmp_path)

    assert manifest["hang"] is None


def test_a_load_that_stalls_past_its_limit_hangs(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    for _ in range(6):
        game.idle(5, 0)
    recorder, target, watchdog = watched(game, tmp_path, load_limit=15.0)

    play(target, watchdog)
    _, manifest = finished(recorder, tmp_path)

    assert manifest["hang"]["stalled"] == 15.0


def test_a_guest_held_for_a_person_is_not_hung(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.drawn()
    for _ in range(6):
        game.idle(5, 10)
    recorder, target, watchdog = watched(game, tmp_path)
    watchdog.hold()

    play(target, watchdog)
    _, manifest = finished(recorder, tmp_path)

    assert manifest["hang"] is None


def test_a_released_guest_is_watched_again_from_a_fresh_baseline(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.drawn()
    for _ in range(3):
        game.idle(5, 10)
    recorder, target, watchdog = watched(game, tmp_path)
    watchdog.hold()
    target.run(timeout=5)
    watchdog.release()

    play(target, watchdog)
    _, manifest = finished(recorder, tmp_path)

    assert manifest["hang"]["stalled"] == 5.0
