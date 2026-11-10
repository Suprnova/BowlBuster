import json
from dataclasses import replace
from pathlib import Path

from contract import schema_errors
from scripted import ScriptedGame
from support import ENVIRONMENT, FAST, drive, driven_events, level, polls, route
from test_new_game import boot, screens, start_taken

MENU = FAST.navigation.modes.menu
LOAD_GAME = FAST.navigation.modes.load_game


def from_save(slot: int = 2) -> tuple[object, dict[str, object]]:
    request = replace(route("ORIG"), start="save", save="base")
    save = {"name": "base", "slot": slot, "image": "played-1", "storage_sha256": "ab" * 32}
    return request, {**ENVIRONMENT, "save": save}


def at_the_menu() -> ScriptedGame:
    game = ScriptedGame(FAST)
    boot(game)
    start_taken(game)
    game.main_menu_ready = True
    game.menu_scene(rows=3)
    return game


def test_a_save_is_loaded_through_load_game_and_its_slot(tmp_path: Path) -> None:
    game = at_the_menu()
    game.await_press("down", mode=MENU, memory=game.highlight(1, 3))
    game.await_press("a", mode=MENU, after=LOAD_GAME)
    game.await_press("down", mode=LOAD_GAME)
    game.await_load(2)
    game.scene_exit("MNUS", 1)
    level(game, "ORIG", 2)
    request, environment = from_save(slot=2)

    session, manifest = drive(game, tmp_path, request, environment=environment)

    assert (session.result, [load["scene"] for load in manifest["loads"]]) == ("done", ["MNUS", "ORIG"])
    assert [row["button"] for row in manifest["input_ledger"]] == ["a", "start", "down", "a", "down", "a"]
    assert screens(tmp_path) == ["logos", "title", "menu", "load game", "save"]


def test_the_slot_load_game_took_is_an_event(tmp_path: Path) -> None:
    game = at_the_menu()
    game.await_press("down", mode=MENU, memory=game.highlight(1, 3))
    game.await_press("a", mode=MENU, after=LOAD_GAME)
    game.await_load(1)
    game.scene_exit("MNUS", 1)
    level(game, "ORIG", 2)
    request, environment = from_save(slot=1)

    drive(game, tmp_path, request, environment=environment)

    events = [event for event in driven_events(tmp_path) if event["event"] == "save_slot"]
    assert [(event["slot"], event["wanted"]) for event in events] == [(1, 1)]


def test_a_down_the_list_dropped_loads_the_slot_above_and_fails_the_step_as_stalled(tmp_path: Path) -> None:
    game = at_the_menu()
    game.await_press("down", mode=MENU, memory=game.highlight(1, 3))
    game.await_press("a", mode=MENU, after=LOAD_GAME)
    game.await_press("down", mode=LOAD_GAME)
    game.await_load(1)
    polls(game, 40, mode=LOAD_GAME)
    request, environment = from_save(slot=2)

    session, _ = drive(game, tmp_path, request, environment=environment)

    events = [event for event in driven_events(tmp_path) if event["event"] == "save_slot"]
    assert (session.result, [(event["slot"], event["wanted"]) for event in events]) == (
        "failed: step 0 (ORIG), stalled",
        [(1, 2)],
    )


def test_a_down_the_main_menu_dropped_is_sent_again_until_it_is_taken(tmp_path: Path) -> None:
    game = at_the_menu()
    game.await_press("down", mode=MENU)
    game.await_press("down", mode=MENU, memory=game.highlight(1, 3))
    game.await_press("a", mode=MENU, after=LOAD_GAME)
    game.await_load(1)
    game.scene_exit("MNUS", 1)
    level(game, "ORIG", 2)
    request, environment = from_save(slot=1)

    session, manifest = drive(game, tmp_path, request, environment=environment)

    assert (session.result, [row["button"] for row in manifest["input_ledger"]]) == (
        "done",
        ["a", "start", "down", "down", "a", "a"],
    )


def test_a_main_menu_that_never_takes_its_down_fails_the_step_as_stalled_at_load_game(tmp_path: Path) -> None:
    game = at_the_menu()
    polls(game, 20000, mode=MENU)
    request, environment = from_save()

    session, manifest = drive(game, tmp_path, request, environment=environment)

    assert (session.result, screens(tmp_path)[-1]) == ("failed: step 0 (ORIG), stalled", "load game")
    assert {row["button"] for row in manifest["input_ledger"]} == {"a", "start", "down"}


def test_an_a_the_main_menu_dropped_never_reaches_load_game_and_fails_there(tmp_path: Path) -> None:
    game = at_the_menu()
    game.await_press("down", mode=MENU, memory=game.highlight(1, 3))
    polls(game, 20000, mode=MENU)
    request, environment = from_save()

    session, manifest = drive(game, tmp_path, request, environment=environment)

    assert (session.result, screens(tmp_path)[-1]) == ("failed: step 0 (ORIG), stalled", "load game")
    assert {row["button"] for row in manifest["input_ledger"]} == {"a", "start", "down"}


def test_a_list_that_never_takes_its_a_fails_the_step_as_stalled_at_the_save(tmp_path: Path) -> None:
    game = at_the_menu()
    game.await_press("down", mode=MENU, memory=game.highlight(1, 3))
    game.await_press("a", mode=MENU, after=LOAD_GAME)
    polls(game, 20000, mode=LOAD_GAME)
    request, environment = from_save(slot=1)

    session, _ = drive(game, tmp_path, request, environment=environment)

    assert (session.result, screens(tmp_path)[-1]) == ("failed: step 0 (ORIG), stalled", "save")


def test_loading_a_save_writes_nothing_but_the_pad_state(tmp_path: Path) -> None:
    game = at_the_menu()
    game.await_press("down", mode=MENU, memory=game.highlight(1, 3))
    game.await_press("a", mode=MENU, after=LOAD_GAME)
    game.await_load(1)
    game.scene_exit("MNUS", 1)
    level(game, "ORIG", 2)
    request, environment = from_save(slot=1)

    _, manifest = drive(game, tmp_path, request, environment=environment)

    assert manifest["write_ledger"] == []


def test_the_manifest_names_the_save(tmp_path: Path) -> None:
    game = at_the_menu()
    game.await_press("down", mode=MENU, memory=game.highlight(1, 3))
    game.await_press("a", mode=MENU, after=LOAD_GAME)
    game.await_load(1)
    game.scene_exit("MNUS", 1)
    level(game, "ORIG", 2)
    request, environment = from_save(slot=1)

    _, manifest = drive(game, tmp_path, request, environment=environment)

    assert manifest["save"] == environment["save"]


def test_the_result_records_a_save_setup_and_validates(tmp_path: Path) -> None:
    game = at_the_menu()
    game.await_press("down", mode=MENU, memory=game.highlight(1, 3))
    game.await_press("a", mode=MENU, after=LOAD_GAME)
    game.await_load(1)
    game.scene_exit("MNUS", 1)
    level(game, "ORIG", 2)
    request, environment = from_save(slot=1)
    drive(game, tmp_path, request, environment=environment)

    written = json.loads((tmp_path / "out" / "result.json").read_text(encoding="utf-8"))

    assert (written["manifest"]["setup"], written["manifest"]["save"]) == ("save", environment["save"])
    assert schema_errors(written, "result") == []
