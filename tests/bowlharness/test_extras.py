from pathlib import Path
from typing import Any

from scripted import CHEATS, PAD_STATE, ScriptedGame
from support import FAST, PAUSE_MENU, drive, driven_events, polls, request

SCREENS = FAST.navigation.menu_screens
PLAY = FAST.navigation.modes.play
_, PLSA, *_ = CHEATS
MERMAID_MAN, DISCO_PATRICK = 1, 3
ROWS = {9: 0, MERMAID_MAN: 0, 8: 0, DISCO_PATRICK: 0}
"""Extra rows 0-3: a movie, Mermaid Man, a movie, Disco Patrick; so Mermaid Man is one Right from the start."""


def ready(game: ScriptedGame, scene: str, counter: int, worn: dict[int, int] | None = None, cheats: int = 0) -> None:
    game.scene_init(scene, counter, extras={**ROWS, **(worn or {})}, cheats=cheats)
    game.players_done()
    polls(game, 11)


def into_extras(game: ScriptedGame, screens: int) -> None:
    """X to Options, three Downs and A to Extras, whose cursor starts at the top left."""
    game.await_press("x", mode=PAUSE_MENU, memory={SCREENS: screens})
    for _ in range(3):
        game.await_press("down", mode=PAUSE_MENU)
    game.await_press("a", mode=PAUSE_MENU, memory=game.extras_cursor(0, 0))


def choose(game: ScriptedGame, moves: list[tuple[str, int, int]], row: int, extra_id: int, state: int) -> None:
    for button, cursor_row, cursor_column in moves:
        game.await_press(button, mode=PAUSE_MENU, memory=game.extras_cursor(cursor_row, cursor_column))
    game.await_press("a", mode=PAUSE_MENU, memory=game.extra_row(row, extra_id, state))


def leave_extras(game: ScriptedGame, screens: int) -> None:
    """B from Extras to the pause menu, changing the screen count; B closing the pause menu; and Start opening it
    again, since the pause menu Extras returns to takes no cursor press."""
    game.await_press("b", mode=PAUSE_MENU, memory={SCREENS: screens})
    game.await_press("b", mode=PAUSE_MENU, after=PLAY)
    game.await_press("start", after=PAUSE_MENU)


def warp(game: ScriptedGame, cursor: tuple[int, int], old: str, scene: str, counter: int, **worn: Any) -> None:
    game.await_press("down", cursor=cursor, mode=PAUSE_MENU)
    for _ in range(3):
        game.await_confirm(mode=PAUSE_MENU)
    game.scene_exit(old, counter - 1)
    ready(game, scene, counter, **worn)


def buttons(manifest: dict[str, Any]) -> list[str]:
    return [row["button"] for row in manifest["input_ledger"]]


def worn(manifest: dict[str, Any], character: str) -> list[str | None]:
    return [load["costumes"][character] for load in manifest["loads"]]


def test_an_extras_costume_is_chosen_on_the_extras_screen_in_the_step_before(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG"})
    ready(game, "ORIG", 1)
    game.extras_screen()
    game.await_press("start", after=PAUSE_MENU)
    into_extras(game, 6)
    choose(game, [("right", 0, 1)], 1, MERMAID_MAN, 1)
    leave_extras(game, 8)
    warp(game, (1, 0), "ORIG", "TARG", 2, worn={1: 1})
    steps = [{"scene": "ORIG"}, {"scene": "TARG", "menu": {"world": 2, "slot": 1}, "costumes": ["PLSB"]}]

    session, manifest = drive(game, tmp_path, request(steps))

    assert (session.result, worn(manifest, "spongebob")) == ("done", [None, "PLSB"])
    assert buttons(manifest) == [
        "start",
        "x",
        "down",
        "down",
        "down",
        "a",
        "right",
        "a",
        "b",
        "b",
        "start",
        "down",
        "a",
        "a",
        "a",
    ]
    assert {address for address, _ in session._target.writes} == {PAD_STATE}


def test_a_later_step_without_the_costume_chooses_it_again_to_take_it_off(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG", (2, 0): "LAST"})
    ready(game, "ORIG", 1)
    game.extras_screen()
    game.await_press("start", after=PAUSE_MENU)
    into_extras(game, 6)
    choose(game, [("right", 0, 1)], 1, MERMAID_MAN, 1)
    leave_extras(game, 8)
    warp(game, (1, 0), "ORIG", "TARG", 2, worn={1: 1})
    game.await_press("start", after=PAUSE_MENU)
    into_extras(game, 10)
    choose(game, [("right", 0, 1)], 1, MERMAID_MAN, 0)
    leave_extras(game, 12)
    warp(game, (2, 0), "TARG", "LAST", 3)
    steps = [
        {"scene": "ORIG"},
        {"scene": "TARG", "menu": {"world": 2, "slot": 1}, "costumes": ["PLSB"]},
        {"scene": "LAST", "menu": {"world": 3, "slot": 1}},
    ]

    session, manifest = drive(game, tmp_path, request(steps))

    assert (session.result, worn(manifest, "spongebob")) == ("done", [None, "PLSB", None])


def test_a_cheat_costume_and_an_extras_costume_go_on_together_the_codes_first(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG"})
    ready(game, "ORIG", 1)
    game.extras_screen()
    game.await_press("start", after=PAUSE_MENU)
    game.await_press("x", mode=PAUSE_MENU, memory={SCREENS: 6})
    game.await_chord("l", "r")
    polls(game, 2, mode=PAUSE_MENU)
    game.enter_code(PLSA[0])
    game.held = 0
    for _ in range(3):
        game.await_press("down", mode=PAUSE_MENU)
    game.await_press("a", mode=PAUSE_MENU, memory=game.extras_cursor(0, 0))
    choose(game, [("right", 0, 1), ("right", 0, 2), ("right", 0, 3)], 3, DISCO_PATRICK, 1)
    leave_extras(game, 8)
    warp(game, (1, 0), "ORIG", "TARG", 2, worn={DISCO_PATRICK: 1}, cheats=PLSA[1])
    steps = [{"scene": "ORIG"}, {"scene": "TARG", "menu": {"world": 2, "slot": 1}, "costumes": ["PLSA", "PLPB"]}]

    session, manifest = drive(game, tmp_path, request(steps))

    assert (session.result, worn(manifest, "spongebob"), worn(manifest, "patrick")) == (
        "done",
        [None, "PLSA"],
        [None, "PLPB"],
    )
    pressed = buttons(manifest)
    after_codes = [
        "down",
        "down",
        "down",
        "a",
        "right",
        "right",
        "right",
        "a",
        "b",
        "b",
        "start",
        "down",
        "a",
        "a",
        "a",
    ]
    assert pressed[pressed.index("l+r") + 1 :] == after_codes and pressed.count("x") == 1 + PLSA[0].count("X")


def test_no_extras_screen_in_the_scene_fails_the_step_as_unsupported(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG"})
    ready(game, "ORIG", 1)
    game.await_press("start", after=PAUSE_MENU)
    game.await_press("x", mode=PAUSE_MENU, memory={SCREENS: 6})
    polls(game, 20, mode=PAUSE_MENU)
    steps = [{"scene": "ORIG"}, {"scene": "TARG", "menu": {"world": 2, "slot": 1}, "costumes": ["PLSB"]}]

    session, _ = drive(game, tmp_path, request(steps))

    assert session.result == "failed: step 0 (ORIG), unsupported"


def test_a_cursor_that_never_moves_fails_the_step_as_stalled(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG"})
    ready(game, "ORIG", 1)
    game.extras_screen()
    game.await_press("start", after=PAUSE_MENU)
    into_extras(game, 6)
    polls(game, 400, mode=PAUSE_MENU)
    steps = [{"scene": "ORIG"}, {"scene": "TARG", "menu": {"world": 2, "slot": 1}, "costumes": ["PLSB"]}]

    session, manifest = drive(game, tmp_path, request(steps))

    assert session.result == "failed: step 0 (ORIG), stalled" and buttons(manifest).count("right") == 4


def test_each_extras_press_is_a_navigation_event(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG"})
    ready(game, "ORIG", 1)
    game.extras_screen()
    game.await_press("start", after=PAUSE_MENU)
    into_extras(game, 6)
    choose(game, [("right", 0, 1)], 1, MERMAID_MAN, 1)
    leave_extras(game, 8)
    warp(game, (1, 0), "ORIG", "TARG", 2, worn={1: 1})
    steps = [{"scene": "ORIG"}, {"scene": "TARG", "menu": {"world": 2, "slot": 1}, "costumes": ["PLSB"]}]

    drive(game, tmp_path, request(steps))

    events = [e for e in driven_events(tmp_path) if e["event"] == "navigation" and e["action"] == "extra"]
    assert [event["input"] for event in events] == ["right", "a"]
