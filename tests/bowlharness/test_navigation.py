from dataclasses import replace
from pathlib import Path

from scripted import PAUSE_MENU as PAUSE_MENU_SCREEN
from scripted import ScriptedGame
from support import FAST, PAUSE_MENU, drive, driven_events, level, polls, route, warp

from bowlharness.profiles import XBOX_NTSC_U


def three_warps() -> ScriptedGame:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG", (2, 1): "TARG", (4, 0): "LAST"})
    level(game, "ORIG", 1)
    warp(game, [("down", (1, 0)), ("down", (2, 0)), ("right", (2, 1))], "TARG", 2, "ORIG")
    warp(game, [("down", (3, 0)), ("down", (4, 0))], "LAST", 3, "TARG")
    warp(game, [("up", (3, 0)), ("up", (2, 0)), ("up", (1, 0)), ("up", (0, 0))], "ORIG", 4, "LAST")
    return game


def test_a_route_of_three_warps_reaches_every_step(tmp_path: Path) -> None:
    session, manifest = drive(three_warps(), tmp_path, route("ORIG", ("TARG", 3, 2), ("LAST", 5, 1), ("ORIG", 1, 1)))

    assert (session.result, manifest["ended"]) == ("done", "done")
    assert [step["status"] for step in manifest["steps"]] == ["reached"] * 4
    assert [load["counter"] for load in manifest["loads"]] == [1, 2, 3, 4]


def test_the_presses_of_a_trip_are_the_menus(tmp_path: Path) -> None:
    _, manifest = drive(three_warps(), tmp_path, route("ORIG", ("TARG", 3, 2), ("LAST", 5, 1), ("ORIG", 1, 1)))

    trip = [row["button"] for row in manifest["input_ledger"]][:7]
    assert (trip, {row["source"] for row in manifest["input_ledger"]}) == (
        ["start", "down", "down", "right", "a", "a", "a"],
        {"harness"},
    )
    assert manifest["steps"][1]["presses"] == 0 and manifest["steps"][2]["presses"] == 0


def test_each_trip_action_is_a_navigation_event(tmp_path: Path) -> None:
    drive(three_warps(), tmp_path, route("ORIG", ("TARG", 3, 2), ("LAST", 5, 1), ("ORIG", 1, 1)))

    first = [(e["step"], e["action"], e["input"]) for e in driven_events(tmp_path) if e["event"] == "navigation"][:5]
    assert first == [
        (1, "pause", "start"),
        (1, "world", "down"),
        (1, "world", "down"),
        (1, "slot", "right"),
        (1, "confirm", "a"),
    ]


def test_a_navigation_event_says_when_a_press_was_sent_and_taken(tmp_path: Path) -> None:
    drive(three_warps(), tmp_path, route("ORIG", ("TARG", 3, 2), ("LAST", 5, 1), ("ORIG", 1, 1)))

    pause = next(e for e in driven_events(tmp_path) if e["event"] == "navigation")
    assert pause["taken"]["poll"] > pause["sent"]["poll"] and pause["taken"]["frame"] >= pause["sent"]["frame"]


def test_reselecting_the_loaded_task_is_a_load(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    warp(game, [], "ORIG", 2, "ORIG")

    session, manifest = drive(game, tmp_path, route("ORIG", ("ORIG", 1, 1)))

    assert (session.result, [load["counter"] for load in manifest["loads"]]) == ("done", [1, 2])


def test_a_press_the_menu_did_not_take_is_sent_again(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    polls(game, 20)
    warp(game, [], "ORIG", 2, "ORIG")

    session, manifest = drive(game, tmp_path, route("ORIG", ("ORIG", 1, 1)))

    starts = [row for row in manifest["input_ledger"] if row["button"] == "start"]
    assert (session.result, len(starts) >= 2) == ("done", True)


def test_a_resent_press_is_logged_as_sent_when_its_last_send_was(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    polls(game, 20)
    warp(game, [], "ORIG", 2, "ORIG")

    _, manifest = drive(game, tmp_path, route("ORIG", ("ORIG", 1, 1)))

    first_start = next(row for row in manifest["input_ledger"] if row["button"] == "start")
    pause = next(e for e in driven_events(tmp_path) if e["event"] == "navigation")
    assert pause["sent"]["frame"] > first_start["sent_frame"] and pause["sent"]["poll"] > first_start["sent_poll"]


def test_a_fourth_miss_fails_the_step_as_stalled(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    polls(game, 100)

    session, manifest = drive(game, tmp_path, route("ORIG", ("ORIG", 1, 1)))

    starts = [row for row in manifest["input_ledger"] if row["button"] == "start"]
    assert (session.result, len(starts)) == ("failed: step 1 (ORIG), stalled", 4)
    assert (manifest["ended"], manifest["steps"][1]["reason"]) == ("failed", "stalled")


def test_a_slot_holding_another_scene_fails_before_any_input(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(2, 1): "OTHR"})
    level(game, "ORIG", 1)
    polls(game, 20)

    session, manifest = drive(game, tmp_path, route("ORIG", ("TARG", 3, 2)))

    assert (session.result, manifest["input_ledger"]) == ("failed: step 1 (TARG), menu unreachable", [])


def test_a_start_from_a_save_is_not_driven_yet(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    level(game, "ORIG", 1)
    polls(game, 20)

    session, manifest = drive(game, tmp_path, replace(route("ORIG"), start="save", save="base"))

    assert (session.result, manifest["input_ledger"]) == ("failed: step 0 (ORIG), unsupported", [])


def test_a_confirmed_warp_that_loads_nothing_fails_as_menu_unreachable(tmp_path: Path) -> None:
    quick = replace(FAST, navigation=replace(FAST.navigation, warp_polls=60))
    game = ScriptedGame(quick)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    game.await_press("start", after=PAUSE_MENU)
    for _ in range(3):
        game.await_confirm(mode=PAUSE_MENU)
    polls(game, 80, mode=PAUSE_MENU)

    session, _ = drive(game, tmp_path, route("ORIG", ("ORIG", 1, 1)))

    assert session.result == "failed: step 1 (ORIG), menu unreachable"


def test_the_pause_menu_the_game_opens_is_where_the_trip_starts_and_its_first_press_is_a_world_move(
    tmp_path: Path,
) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(2, 0): "TARG"})
    game.scene_init("ORIG", 1)
    game.players_done()
    game.cursor = (5, 0)
    polls(game, 6, mode=PAUSE_MENU, state=0)
    game.await_press("up", cursor=(3, 0), mode=PAUSE_MENU)
    game.await_press("up", cursor=(2, 0), mode=PAUSE_MENU)
    for _ in range(3):
        game.await_confirm(mode=PAUSE_MENU)
    game.scene_exit("ORIG", 1)
    level(game, "TARG", 2)

    session, manifest = drive(game, tmp_path, route("ORIG", ("TARG", 3, 1)))

    assert (session.result, manifest["steps"][0]["signal"]) == ("done", "pause_menu")
    assert [row["button"] for row in manifest["input_ledger"]] == ["up", "up", "a", "a", "a"]


def test_a_cutscene_is_pressed_through_while_it_holds_and_not_after(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.scene_init("ORIG", 1)
    game.players_done()
    polls(game, 30, control_off=2)
    polls(game, 20)

    _, manifest = drive(game, tmp_path, route("ORIG"))

    rows = manifest["input_ledger"]
    assert len(rows) >= 2 and {row["button"] for row in rows} == {"a"} and max(row["sent_poll"] for row in rows) <= 30
    assert manifest["steps"][0]["presses"] == len(rows)


def test_a_movie_is_pressed_through_while_it_plays(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.scene_init("ORIG", 1)
    polls(game, 20, movie=1)
    game.players_done()
    polls(game, 20)

    _, manifest = drive(game, tmp_path, route("ORIG"))

    assert {row["button"] for row in manifest["input_ledger"]} == {"a"}


def test_nothing_is_pressed_while_a_scene_is_ready_and_in_play(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    level(game, "ORIG", 1)

    session, manifest = drive(game, tmp_path, route("ORIG"))

    assert (session.result, manifest["input_ledger"]) == ("done", [])


def test_a_spongeball_scene_is_ready_on_the_first_frame_after_its_player_inits(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.scene_init("BL01", 1)
    game.players_done()
    polls(game, 20, gate=0)

    _, manifest = drive(game, tmp_path, route("BL01"))

    assert manifest["steps"][0]["signal"] == "first_frame"


def test_a_driving_scene_is_ready_when_control_comes(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.scene_init("PT02", 1)
    game.players_done()
    polls(game, 5, control_off=2)
    returned = game.frame + 1
    polls(game, 70)

    _, manifest = drive(game, tmp_path, route("PT02"))

    settle = XBOX_NTSC_U.scene_classes.of("PT02").settle_frames
    assert (manifest["steps"][0]["signal"], manifest["steps"][0]["frame"]) == ("drawn_and_control", returned + settle)


def test_a_scene_that_never_draws_logs_undrawn_and_goes_on(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.scene_init("ORIG", 1)
    game.players_done()
    polls(game, 45, gate=0)

    _, manifest = drive(game, tmp_path, route("ORIG"))

    assert [e["event"] for e in driven_events(tmp_path) if e["event"] == "undrawn"] == ["undrawn"]
    assert (manifest["steps"][0]["status"], manifest["steps"][0]["signal"]) == ("reached", "drawn_and_control")


def test_a_player_that_never_gets_control_logs_control_off_and_stops_waiting(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.scene_init("ORIG", 1)
    game.players_done()
    polls(game, 45, control_off=2)

    _, manifest = drive(game, tmp_path, route("ORIG"))

    assert "control_off" in [e["event"] for e in driven_events(tmp_path)]
    assert (manifest["steps"][0]["status"], manifest["steps"][0]["signal"]) == ("reached", "control_off")


def test_nothing_is_pressed_in_the_pause_menu_until_it_is_active(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    game.menu_lag = 30
    game.await_press("start", after=PAUSE_MENU)
    polls(game, 19, mode=PAUSE_MENU)
    for _ in range(3):
        game.await_confirm(mode=PAUSE_MENU, polls=100)
    game.scene_exit("ORIG", 1)
    level(game, "ORIG", 2)

    session, manifest = drive(game, tmp_path, route("ORIG", ("ORIG", 1, 1)))

    start, first_a = manifest["input_ledger"][:2]
    assert (session.result, first_a["sent_poll"] - start["sent_poll"] >= 30) == ("done", True)


def test_a_pause_menu_that_never_becomes_active_fails_the_step_as_stalled(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    game.menu_lag = 100000
    game.await_press("start", after=PAUSE_MENU)
    polls(game, 20000, mode=PAUSE_MENU)

    session, manifest = drive(game, tmp_path, route("ORIG", ("ORIG", 1, 1)))

    assert (session.result, [row["button"] for row in manifest["input_ledger"]]) == (
        "failed: step 1 (ORIG), stalled",
        ["start"],
    )


def test_a_conversation_is_pressed_through_with_b_and_a_cutscene_with_a(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 1)
    game.players_done()
    polls(game, 14, control_off=XBOX_NTSC_U.navigation.talk_box)
    polls(game, 14, control_off=2)
    polls(game, 14)

    _, manifest = drive(game, tmp_path, route("ORIG"))

    assert [row["button"] for row in manifest["input_ledger"]] == ["b", "b", "a"]


def test_a_confirm_that_does_not_begin_the_warp_is_pressed_again_after_the_time_it_normally_takes(
    tmp_path: Path,
) -> None:
    quick = replace(FAST, navigation=replace(FAST.navigation, warp_wait_polls=20))
    game = ScriptedGame(quick)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    game.await_press("start", after=PAUSE_MENU)
    game.await_confirm(mode=PAUSE_MENU)
    game.await_confirm(mode=PAUSE_MENU)
    polls(game, 12, mode=PAUSE_MENU)
    game.await_confirm(mode=PAUSE_MENU, polls=100)
    game.scene_exit("ORIG", 1)
    level(game, "ORIG", 2)

    session, manifest = drive(game, tmp_path, route("ORIG", ("ORIG", 1, 1)))

    presses = [row["button"] for row in manifest["input_ledger"]]
    assert (session.result, presses) == ("done", ["start", "a", "a", "a", "a"])


def test_a_confirm_is_not_pressed_again_once_the_menu_has_closed(tmp_path: Path) -> None:
    quick = replace(FAST, navigation=replace(FAST.navigation, warp_wait_polls=20))
    game = ScriptedGame(quick)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    game.await_press("start", after=PAUSE_MENU)
    game.await_confirm(mode=PAUSE_MENU, after=XBOX_NTSC_U.navigation.modes.play)
    polls(game, 100)
    game.scene_exit("ORIG", 1)
    level(game, "ORIG", 2)

    session, manifest = drive(game, tmp_path, route("ORIG", ("ORIG", 1, 1)))

    assert (session.result, [row["button"] for row in manifest["input_ledger"]].count("a")) == ("done", 1)


def test_an_a_the_menu_never_counts_is_sent_again_until_the_warp_has_had_its_polls(tmp_path: Path) -> None:
    quick = replace(FAST, navigation=replace(FAST.navigation, warp_wait_polls=20, warp_polls=300))
    game = ScriptedGame(quick)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    game.await_press("start", after=PAUSE_MENU)
    polls(game, 400, mode=PAUSE_MENU)

    session, manifest = drive(game, tmp_path, route("ORIG", ("ORIG", 1, 1)))

    presses = [row["button"] for row in manifest["input_ledger"]].count("a")
    assert (session.result, presses > 1) == ("failed: step 1 (ORIG), stalled", True)
    assert presses <= quick.navigation.warp_polls // quick.navigation.action_polls + 1


def test_each_a_of_a_warp_waits_for_the_menu_to_count_the_one_before(tmp_path: Path) -> None:
    quick = replace(FAST, input=replace(FAST.input, hold_polls=1, release_polls=1))
    game = ScriptedGame(quick)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    game.await_press("start", after=PAUSE_MENU)
    for _ in range(3):
        game.await_confirm(mode=PAUSE_MENU, after=PAUSE_MENU)
    polls(game, 2, mode=PAUSE_MENU)
    game.scene_exit("ORIG", 1)
    level(game, "ORIG", 2)

    session, _ = drive(game, tmp_path, route("ORIG", ("ORIG", 1, 1), profile=quick))

    events = [e for e in driven_events(tmp_path) if e["event"] == "navigation"]
    confirms = [e for e in events if e["action"] == "confirm"]
    assert (session.result, len(confirms), [e["action"] for e in events][-1]) == ("done", 3, "warp")
    pairs = zip(confirms, confirms[1:], strict=False)
    assert all(later["sent"]["poll"] >= earlier["taken"]["poll"] for earlier, later in pairs)


def test_the_pause_menu_screen_is_found_by_its_name_when_another_screen_is_active(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    game.active_screen = PAUSE_MENU_SCREEN - FAST.navigation.screens.stride
    game.await_press("start", after=PAUSE_MENU)
    for _ in range(3):
        game.await_confirm(mode=PAUSE_MENU, after=PAUSE_MENU)
    game.scene_exit("ORIG", 1)
    level(game, "ORIG", 2)

    session, _ = drive(game, tmp_path, route("ORIG", ("ORIG", 1, 1)))

    confirms = [e for e in driven_events(tmp_path) if e["event"] == "navigation" and e["action"] == "confirm"]
    assert (session.result, len(confirms)) == ("done", 3)


def test_a_press_still_pending_when_a_scene_loads_is_dropped(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    game.await_press("start", after=PAUSE_MENU)
    game.await_press("a", mode=PAUSE_MENU)
    game.scene_exit("ORIG", 1)
    level(game, "ORIG", 2)
    warp(game, [], "ORIG", 3, "ORIG")

    session, manifest = drive(game, tmp_path, route("ORIG", ("ORIG", 1, 1), ("ORIG", 1, 1)))

    presses = [row["button"] for row in manifest["input_ledger"]]
    assert (session.result, presses[:3]) == ("done", ["start", "a", "start"])


def test_start_waits_for_the_player_to_be_back_in_control_after_the_step_was_reached(tmp_path: Path) -> None:
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    polls(game, FAST.scene_classes.stall_frames - 5, control_off=1)
    back = game.frame
    game.await_press("start", after=PAUSE_MENU)
    for _ in range(3):
        game.await_confirm(mode=PAUSE_MENU, after=PAUSE_MENU)
    game.scene_exit("ORIG", 1)
    level(game, "ORIG", 2)

    session, manifest = drive(game, tmp_path, route("ORIG", ("ORIG", 1, 1)))

    start = manifest["input_ledger"][0]
    assert (session.result, start["button"], start["sent_frame"] > back) == ("done", "start", True)


def test_start_is_sent_anyway_when_the_player_never_recovers(tmp_path: Path) -> None:
    stall = FAST.scene_classes.stall_frames
    game = ScriptedGame(FAST)
    game.menu_scenes({(0, 0): "ORIG"})
    level(game, "ORIG", 1)
    polls(game, stall + 40, control_off=1)

    _, manifest = drive(game, tmp_path, route("ORIG", ("ORIG", 1, 1)))

    start = manifest["input_ledger"][0]
    assert (start["button"], start["sent_frame"] >= manifest["steps"][0]["frame"] + stall) == ("start", True)
