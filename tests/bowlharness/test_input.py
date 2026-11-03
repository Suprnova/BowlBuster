import json
import struct
from pathlib import Path

import pytest
from scripted import PAD_BUFFER, ScriptedGame

from bowlharness.backends.mock import MockTarget
from bowlharness.driving.input import MANUAL, InputDriver
from bowlharness.profiles import XBOX_NTSC_U
from bowlharness.recording.recorder import Options, Recorder

BUTTONS = XBOX_NTSC_U.input.buttons


def polls(game: ScriptedGame, count: int, **kwargs: int) -> None:
    for _ in range(count):
        game.pad_poll(**kwargs)


def start(
    game: ScriptedGame, directory: Path, *, watch_person: bool = False
) -> tuple[Recorder, MockTarget, InputDriver]:
    target = game.build()
    recorder = Recorder(target, game.profile, directory, "run-1", Options())
    recorder.start("attach")
    driver = InputDriver(target, game.profile, recorder, watch_person=watch_person)
    driver.arm()
    return recorder, target, driver


def manifest(recorder: Recorder, directory: Path) -> dict:
    recorder.finish()
    return json.loads((directory / "manifest.json").read_text())


def dword(mask: int) -> bytes:
    return struct.pack("<I", mask)


def test_a_press_is_held_for_six_polls_and_released_for_six(tmp_path: Path) -> None:
    game = ScriptedGame()
    polls(game, 20)
    recorder, target, driver = start(game, tmp_path)
    driver.press("a")
    driver.press("b")

    target.run()

    rows = manifest(recorder, tmp_path)["input_ledger"]
    assert [(row["button"], row["sent_poll"], row["polls"]) for row in rows] == [("a", 1, 6), ("b", 13, 6)]
    assert target.writes == [(PAD_BUFFER, dword(BUTTONS.a))] * 6 + [(PAD_BUFFER, dword(BUTTONS.b))] * 6


def test_the_only_writes_are_to_the_button_dword_while_a_press_is_held(tmp_path: Path) -> None:
    game = ScriptedGame()
    polls(game, 20)
    recorder, target, driver = start(game, tmp_path)
    driver.press("start", hold=3)

    target.run()

    assert target.writes == [(PAD_BUFFER, dword(BUTTONS.start))] * 3
    assert manifest(recorder, tmp_path)["write_ledger"] == []


def test_a_press_is_added_to_the_physical_buttons(tmp_path: Path) -> None:
    game = ScriptedGame()
    polls(game, 2, physical=BUTTONS.l)
    _, target, driver = start(game, tmp_path)
    driver.press("x", hold=1)

    target.run()

    assert target.writes == [(PAD_BUFFER, dword(BUTTONS.l | BUTTONS.x))]


def test_a_stop_that_read_no_pad_or_polled_another_port_is_left_alone(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.pad_poll(result=0)
    game.pad_poll(port=1)
    _, target, driver = start(game, tmp_path)
    driver.press("a")

    target.run()

    assert (target.writes, driver.polls) == ([], 0)


def test_identical_polls_each_count(tmp_path: Path) -> None:
    game = ScriptedGame()
    polls(game, 3)
    _, target, driver = start(game, tmp_path)

    target.run()

    assert driver.polls == 3


def test_a_scene_init_cancels_a_press_in_progress(tmp_path: Path) -> None:
    game = ScriptedGame()
    polls(game, 3)
    game.scene_init("ORIG", 2)
    polls(game, 5)
    recorder, target, driver = start(game, tmp_path)
    driver.press("a")

    target.run()

    rows = manifest(recorder, tmp_path)["input_ledger"]
    assert [(row["button"], row["polls"], row["cancelled"]) for row in rows] == [("a", 3, True)]
    assert len(target.writes) == 3


def test_the_ledger_row_says_what_the_game_was_doing_and_when_it_took_the_press(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.pad_poll(mode=XBOX_NTSC_U.navigation.modes.pause_menu, state=0, control_off=0x2)
    game.pad_poll()
    game.pad_poll(pressed=BUTTONS.a)
    taken = game.frame
    polls(game, 8)
    recorder, target, driver = start(game, tmp_path)
    driver.press("a")

    target.run()

    row = manifest(recorder, tmp_path)["input_ledger"][0]
    assert (row["game_mode"], row["play_state"], row["control_off"]) == (7, 0, 2)
    assert (row["sent_poll"], row["sent_frame"], row["taken_frame"]) == (1, 1, taken)


def test_a_press_the_game_never_took_has_no_taken_frame(tmp_path: Path) -> None:
    game = ScriptedGame()
    polls(game, 10)
    recorder, target, driver = start(game, tmp_path)
    driver.press("a")

    target.run()

    assert manifest(recorder, tmp_path)["input_ledger"][0]["taken_frame"] is None


def test_a_press_is_an_event_and_the_run_stays_unattended(tmp_path: Path) -> None:
    game = ScriptedGame()
    polls(game, 8)
    recorder, target, driver = start(game, tmp_path)
    driver.press("a")

    target.run()

    document = manifest(recorder, tmp_path)
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    press = next(event for event in events if event["event"] == "press")
    assert (press["button"], press["mask"], press["source"], press["polls"]) == ("a", BUTTONS.a, "harness", 6)
    assert document["attended"] is False


def test_a_physical_button_is_a_persons_press_and_marks_the_run_attended(tmp_path: Path) -> None:
    game = ScriptedGame()
    polls(game, 3, physical=BUTTONS.a)
    polls(game, 2)
    recorder, target, _ = start(game, tmp_path, watch_person=True)

    target.run()

    document = manifest(recorder, tmp_path)
    row = document["input_ledger"][0]
    assert (row["button"], row["source"], row["polls"], document["attended"]) == ("a", "person", 3, True)


def test_a_physical_button_is_ignored_unless_watched(tmp_path: Path) -> None:
    game = ScriptedGame()
    polls(game, 3, physical=BUTTONS.a)
    polls(game, 2)
    recorder, target, _ = start(game, tmp_path)

    target.run()

    document = manifest(recorder, tmp_path)
    assert (document["input_ledger"], document["attended"]) == ([], False)


def test_a_stop_the_guest_is_held_at_gives_its_press_when_replayed(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.pad_poll()
    target = game.build()
    target.run()
    recorder = Recorder(target, game.profile, tmp_path, "run-1", Options())
    recorder.start("attach")
    driver = InputDriver(target, game.profile, recorder)
    driver.arm()
    driver.press("a", hold=1)

    recorder.replay_current_stop()

    assert (target.writes, driver.polls) == ([(PAD_BUFFER, dword(BUTTONS.a))], 1)


def test_a_manual_press_marks_the_run_attended(tmp_path: Path) -> None:
    game = ScriptedGame()
    polls(game, 8)
    recorder, target, driver = start(game, tmp_path)
    driver.press("a", source=MANUAL)

    target.run()

    document = manifest(recorder, tmp_path)
    assert (document["input_ledger"][0]["source"], document["attended"]) == ("manual", True)


@pytest.mark.parametrize(("button", "hold"), [("select", None), ("a", 0)])
def test_a_press_needs_a_button_and_a_hold(tmp_path: Path, button: str, hold: int | None) -> None:
    _, _, driver = start(ScriptedGame(), tmp_path)

    with pytest.raises(ValueError, match="invalid button|must be held"):
        driver.press(button, hold=hold)


def test_a_scene_init_drops_the_presses_still_queued(tmp_path: Path) -> None:
    game = ScriptedGame()
    polls(game, 3)
    game.scene_init("ORIG", 2)
    polls(game, 30)
    recorder, target, driver = start(game, tmp_path)
    for button in ("a", "b", "x"):
        driver.press(button)

    target.run()

    assert (len(target.writes), driver.idle) == (3, True)


def test_a_poll_the_debugger_reports_twice_is_not_a_persons_press_or_a_second_poll(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.pad_poll()
    game.pad_poll(physical=BUTTONS.a)
    polls(game, 12)
    recorder, target, driver = start(game, tmp_path, watch_person=True)
    driver.press("a", hold=1)

    target.run()

    document = manifest(recorder, tmp_path)
    assert ([row["source"] for row in document["input_ledger"]], document["attended"], driver.polls) == (
        ["harness"],
        False,
        13,
    )


def test_a_chord_is_held_at_every_poll_across_the_presses_queued_while_it_is_held(tmp_path: Path) -> None:
    game = ScriptedGame()
    polls(game, 12)
    recorder, target, driver = start(game, tmp_path)
    chord = BUTTONS.l | BUTTONS.r
    driver.hold_chord("l", "r")
    driver.press("x", hold=2)
    driver.press("y", hold=2)

    target.run()
    driver.release_chord()

    expected = [chord | BUTTONS.x] * 2 + [chord] * 6 + [chord | BUTTONS.y] * 2 + [chord] * 2
    assert target.writes == [(PAD_BUFFER, dword(value)) for value in expected]
    chord_row = manifest(recorder, tmp_path)["input_ledger"][-1]
    assert (chord_row["button"], chord_row["mask"], chord_row["polls"], chord_row["cancelled"]) == (
        "l+r",
        chord,
        12,
        False,
    )


def test_a_chord_a_scene_init_finds_is_cancelled(tmp_path: Path) -> None:
    game = ScriptedGame()
    polls(game, 5)
    game.scene_init("TARG", 2)
    polls(game, 5)
    recorder, target, driver = start(game, tmp_path)
    driver.hold_chord("l", "r")

    target.run()

    rows = manifest(recorder, tmp_path)["input_ledger"]
    assert ([(row["button"], row["polls"], row["cancelled"]) for row in rows], len(target.writes)) == (
        [("l+r", 5, True)],
        5,
    )


def test_a_second_chord_or_a_chord_of_no_button_is_refused(tmp_path: Path) -> None:
    _, _, driver = start(ScriptedGame(), tmp_path)

    with pytest.raises(ValueError, match="invalid button"):
        driver.hold_chord("l", "z")
    driver.hold_chord("l")
    with pytest.raises(ValueError, match="already held"):
        driver.hold_chord("r")
