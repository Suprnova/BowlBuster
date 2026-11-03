from pathlib import Path

from scripted import PAD_BUFFER, ScriptedGame
from support import FAST, drive, driven_events, level, polls, route

from bowlharness.backends.mock import Wait

MENU = FAST.navigation.modes.menu
TITLE_START = FAST.navigation.title_start
A = FAST.input.buttons.a


def boot(game: ScriptedGame) -> None:
    """The boot scene, a logo skipped with A, and the title."""
    game.scene_init("MNUS", 1)
    game.players_done()
    game.pad_poll(mode=1, movie=1, wait=Wait(PAD_BUFFER, A, 30))
    polls(game, 11, mode=1)


def start_taken(game: ScriptedGame) -> None:
    game.await_press("start", mode=MENU, memory={TITLE_START: 0})


def screens(tmp_path: Path) -> list[str]:
    return [event["name"] for event in driven_events(tmp_path) if event["event"] == "screen"]


def test_a_new_game_reaches_its_first_step_from_the_logos(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    boot(game)
    start_taken(game)
    game.main_menu_ready = True
    game.await_press("a", mode=MENU)
    game.scene_exit("MNUS", 1)
    level(game, "ORIG", 2)

    session, manifest = drive(game, tmp_path, route("ORIG", start="new-game"))

    assert (session.result, [load["scene"] for load in manifest["loads"]]) == ("done", ["MNUS", "ORIG"])
    assert [row["button"] for row in manifest["input_ledger"]] == ["a", "start", "a"]
    assert screens(tmp_path) == ["logos", "title", "menu", "new game"]


def test_a_title_that_never_takes_start_fails_the_step_as_stalled_at_the_title(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    boot(game)
    polls(game, 20000, mode=MENU)

    session, manifest = drive(game, tmp_path, route("ORIG", start="new-game"))

    assert (session.result, screens(tmp_path)[-1]) == ("failed: step 0 (ORIG), stalled", "title")
    assert [row["button"] for row in manifest["input_ledger"]].count("start") == 4


def test_a_menu_that_never_becomes_active_fails_the_step_as_stalled_at_the_menu(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    boot(game)
    start_taken(game)
    polls(game, 20000, mode=MENU)

    session, manifest = drive(game, tmp_path, route("ORIG", start="new-game"))

    assert (session.result, screens(tmp_path)[-1]) == ("failed: step 0 (ORIG), stalled", "menu")
    assert [row["button"] for row in manifest["input_ledger"]] == ["a", "start"]


def test_a_is_pressed_again_until_the_load_begins(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    boot(game)
    start_taken(game)
    game.main_menu_ready = True
    game.await_press("a", mode=MENU)
    game.await_press("a", mode=MENU)
    game.scene_exit("MNUS", 1)
    level(game, "ORIG", 2)

    session, manifest = drive(game, tmp_path, route("ORIG", start="new-game"))

    assert (session.result, [row["button"] for row in manifest["input_ledger"]]) == ("done", ["a", "start", "a", "a"])
