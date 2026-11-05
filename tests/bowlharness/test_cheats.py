from dataclasses import replace
from pathlib import Path
from typing import Any

from scripted import CHEATS, PAD_STATE, ScriptedGame
from support import FAST, PAUSE_MENU, drive, driven_events, level, polls, request

from bowlharness.profiles import XBOX_NTSC_U

BUTTONS = XBOX_NTSC_U.input.buttons
CHORD = BUTTONS.l | BUTTONS.r
EVERY_TASK, PLSA, *_ = CHEATS
COUNT = FAST.navigation.cheats.count
SCREENS = FAST.navigation.menu_screens


def open_options(game: ScriptedGame) -> None:
    """Start, X, and L and R held, from a ready level."""
    game.await_press("start", after=PAUSE_MENU)
    game.await_press("x", mode=PAUSE_MENU, memory={SCREENS: 6})
    game.await_chord("l", "r")
    polls(game, 2, mode=PAUSE_MENU)


def leave_options(game: ScriptedGame) -> None:
    game.held = 0
    game.await_press("b", mode=PAUSE_MENU, memory={SCREENS: 8})


def trip(game: ScriptedGame, cursor: tuple[int, int], scene: str, counter: int, old: str, cheats: int = 0) -> None:
    """The cursor's press, A three times, and the load of ``scene`` wearing what ``cheats`` enable."""
    game.await_press("down", cursor=cursor, mode=PAUSE_MENU)
    for _ in range(3):
        game.await_press("a", mode=PAUSE_MENU)
    game.scene_exit(old, counter - 1)
    game.scene_init(scene, counter, cheats=cheats)
    game.players_done()
    polls(game, 11)


def two_steps(**second: Any) -> Any:
    steps = [{"scene": "ORIG"}, {"scene": "TARG", "menu": {"world": 2, "slot": 1}, **second}]
    return request(steps)


def cheat_inputs(tmp_path: Path) -> list[str]:
    events = driven_events(tmp_path)
    return [e["input"] for e in events if e["event"] == "navigation" and e["action"] == "cheat"]


def test_a_code_holds_l_and_r_across_all_eight_presses(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    level(game, "ORIG", 1)
    open_options(game)
    game.enter_code(EVERY_TASK[0])

    session, manifest = drive(game, tmp_path, request([{"scene": "ORIG", "cheats": ["all-tasks"]}]))

    rows = manifest["input_ledger"]
    chord = rows[-1]
    assert (session.result, [row["button"] for row in rows]) == (
        "done",
        ["start", "x", *EVERY_TASK[0].lower().split(), "l+r"],
    )
    assert (chord["mask"], chord["polls"] >= 8 * 12, chord["cancelled"]) == (CHORD, True, False)
    written = [FAST.input.held(value) for _, value in session._target.writes]
    held = written[next(i for i, value in enumerate(written) if value & CHORD == CHORD) :]
    assert (
        all(value & CHORD == CHORD for value in held)
        and sum(value & (BUTTONS.x | BUTTONS.y) != 0 for value in held) == 8 * 6
    )


def test_each_press_of_a_code_is_a_navigation_event(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    level(game, "ORIG", 1)
    open_options(game)
    game.enter_code(EVERY_TASK[0])

    drive(game, tmp_path, request([{"scene": "ORIG", "cheats": ["all-tasks"]}]))

    assert cheat_inputs(tmp_path) == EVERY_TASK[0].lower().split()


def test_a_cheat_costume_is_toggled_on_before_its_step_and_off_before_the_next(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG", (2, 0): "LAST"})
    level(game, "ORIG", 1)
    open_options(game)
    game.enter_code(EVERY_TASK[0])
    game.enter_code(PLSA[0], mask_before=EVERY_TASK[1])
    leave_options(game)
    trip(game, (1, 0), "TARG", 2, "ORIG", cheats=PLSA[1] | EVERY_TASK[1])
    open_options(game)
    game.enter_code(PLSA[0], mask_before=PLSA[1] | EVERY_TASK[1])
    leave_options(game)
    trip(game, (2, 0), "LAST", 3, "TARG", cheats=EVERY_TASK[1])
    steps = [
        {"scene": "ORIG", "cheats": ["all-tasks"]},
        {"scene": "TARG", "menu": {"world": 2, "slot": 1}, "costumes": ["PLSA"]},
        {"scene": "LAST", "menu": {"world": 3, "slot": 1}},
    ]

    session, manifest = drive(game, tmp_path, request(steps))

    assert (session.result, [load["costumes"]["spongebob"] for load in manifest["loads"]]) == (
        "done",
        [None, "PLSA", None],
    )
    assert cheat_inputs(tmp_path) == [
        *EVERY_TASK[0].lower().split(),
        *PLSA[0].lower().split(),
        *PLSA[0].lower().split(),
    ]
    assert {address for address, _ in session._target.writes} == {PAD_STATE}


def test_a_code_the_game_dropped_is_entered_again_from_a_cleared_history(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    level(game, "ORIG", 1)
    open_options(game)
    game.await_press("x", mode=PAUSE_MENU, memory={COUNT: 1})
    game.await_press("y", mode=PAUSE_MENU, memory={COUNT: 0})
    game.enter_code(EVERY_TASK[0])

    session, _ = drive(game, tmp_path, request([{"scene": "ORIG", "cheats": ["all-tasks"]}]))

    assert (session.result, cheat_inputs(tmp_path)) == ("done", ["x", *EVERY_TASK[0].lower().split()])


def test_a_code_that_never_takes_fails_the_step_as_stalled_after_its_attempts(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    level(game, "ORIG", 1)
    open_options(game)
    for _ in range(4):
        game.await_press("x", mode=PAUSE_MENU, memory={COUNT: 1})
        game.await_press("y", mode=PAUSE_MENU, memory={COUNT: 0})

    session, manifest = drive(game, tmp_path, request([{"scene": "ORIG", "cheats": ["all-tasks"]}]))

    assert (session.result, manifest["steps"][0]["status"], len(cheat_inputs(tmp_path))) == (
        "failed: step 0 (ORIG), stalled",
        "failed",
        4,
    )


def test_an_options_menu_that_never_takes_a_press_fails_the_step_as_stalled(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    level(game, "ORIG", 1)
    open_options(game)
    polls(game, 20000, mode=PAUSE_MENU)

    session, _ = drive(game, tmp_path, request([{"scene": "ORIG", "cheats": ["all-tasks"]}]))

    assert session.result == "failed: step 0 (ORIG), stalled"


def test_a_non_toggling_code_already_in_the_cheat_mask_is_not_entered(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.scene_init("ORIG", 1, cheats=EVERY_TASK[1])
    game.players_done()
    polls(game, 12)

    session, manifest = drive(game, tmp_path, request([{"scene": "ORIG", "cheats": ["all-tasks"]}]))

    assert (session.result, manifest["input_ledger"]) == ("done", [])


def test_a_load_that_wears_other_costumes_than_the_step_names_fails_as_a_costume_mismatch(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG"})
    level(game, "ORIG", 1)
    open_options(game)
    game.enter_code(PLSA[0])
    leave_options(game)
    trip(game, (1, 0), "TARG", 2, "ORIG")

    session, manifest = drive(game, tmp_path, two_steps(costumes=["PLSA"]))

    assert (session.result, manifest["steps"][1]["reason"]) == (
        "failed: step 1 (TARG), costume mismatch",
        "costume mismatch",
    )


def test_a_cheat_whose_bit_no_row_sets_fails_the_route_as_unsupported_before_any_input(tmp_path: Path) -> None:
    cheats = replace(FAST.navigation.cheats, names=(("all-tasks", 0x1),))
    game = ScriptedGame(replace(FAST, navigation=replace(FAST.navigation, cheats=cheats)))
    level(game, "ORIG", 1)
    polls(game, 20)

    session, manifest = drive(game, tmp_path, request([{"scene": "ORIG", "cheats": ["all-tasks"]}]))

    assert (session.result, manifest["input_ledger"]) == ("failed: step 0 (ORIG), unsupported", [])


def test_an_extras_costume_fails_the_route_as_unsupported_before_any_input(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG"})
    level(game, "ORIG", 1)
    polls(game, 20)

    session, manifest = drive(game, tmp_path, two_steps(costumes=["PLSB"]))

    assert (session.result, manifest["input_ledger"]) == ("failed: step 0 (ORIG), unsupported", [])


def test_a_b_that_does_not_close_options_fails_the_step_as_stalled(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG"})
    level(game, "ORIG", 1)
    open_options(game)
    game.enter_code(PLSA[0])
    game.held = 0
    polls(game, 20000, mode=PAUSE_MENU)

    session, _ = drive(game, tmp_path, two_steps(costumes=["PLSA"]))

    assert session.result == "failed: step 0 (ORIG), stalled"


def test_a_pause_menu_that_takes_no_press_after_options_fails_the_next_step_as_stalled(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG"})
    level(game, "ORIG", 1)
    open_options(game)
    game.enter_code(PLSA[0])
    leave_options(game)
    polls(game, 20000, mode=PAUSE_MENU)

    session, manifest = drive(game, tmp_path, two_steps(costumes=["PLSA"]))

    assert (session.result, manifest["steps"][0]["status"]) == ("failed: step 1 (TARG), stalled", "reached")


def test_a_press_after_options_is_sent_again_until_the_pause_menu_takes_it(tmp_path: Path) -> None:
    patient = replace(FAST, navigation=replace(FAST.navigation, ready_seconds=60.0))
    game = ScriptedGame(patient)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG"})
    level(game, "ORIG", 1)
    open_options(game)
    game.enter_code(PLSA[0])
    leave_options(game)
    polls(game, 150, mode=PAUSE_MENU)
    trip(game, (1, 0), "TARG", 2, "ORIG", cheats=PLSA[1])

    session, manifest = drive(game, tmp_path, two_steps(costumes=["PLSA"]))

    downs = [row for row in manifest["input_ledger"] if row["button"] == "down"]
    assert (session.result, len(downs) > XBOX_NTSC_U.input.resend_limit + 1) == ("done", True)


def test_a_cursor_already_on_the_task_after_options_is_moved_off_and_back_before_the_confirm(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    open_options(game)
    game.enter_code(EVERY_TASK[0])
    leave_options(game)
    game.await_press("down", cursor=(1, 0), mode=PAUSE_MENU)
    game.await_press("up", cursor=(0, 0), mode=PAUSE_MENU)
    for _ in range(3):
        game.await_press("a", mode=PAUSE_MENU)
    game.scene_exit("ORIG", 1)
    level(game, "ORIG", 2)
    steps = [{"scene": "ORIG", "cheats": ["all-tasks"]}, {"scene": "ORIG", "menu": {"world": 1, "slot": 1}}]

    session, manifest = drive(game, tmp_path, request(steps))

    buttons = [row["button"] for row in manifest["input_ledger"]]
    assert (session.result, buttons[buttons.index("b") :]) == ("done", ["b", "down", "up", "a", "a", "a"])
