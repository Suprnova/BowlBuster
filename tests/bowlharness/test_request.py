import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from bowlharness.driving.request import Menu, Step, parse_request, read_request
from bowlharness.profiles import XBOX_NTSC_U


def document(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": 1,
        "request_id": "route-1",
        "kind": "record",
        "start": {"from": "booted"},
        "steps": [{"scene": "ORIG"}, {"scene": "TARG", "menu": {"world": 3, "slot": 2}}],
    }
    return base | changes


def step(**changes: Any) -> dict[str, Any]:
    return {"scene": "TARG", "menu": {"world": 1, "slot": 1}} | changes


def refused(request: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_request(request, XBOX_NTSC_U)


def test_a_request_gets_the_documented_defaults() -> None:
    request = parse_request(document(), XBOX_NTSC_U)

    assert request.to_json()["observe"] == {"heap_events": "all", "cutoff_captures": "none", "capture_budget": None}
    assert request.to_json()["input"] == {"hold": 6, "release": 6}


def test_a_request_is_read_with_its_steps() -> None:
    request = parse_request(document(), XBOX_NTSC_U)

    assert request.steps == (Step("ORIG"), Step("TARG", Menu(3, 2)))


def test_the_manifests_copy_of_a_request_states_its_defaults_and_reads_back_the_same() -> None:
    request = parse_request(document(client={"id": 7}), XBOX_NTSC_U)

    assert parse_request(request.to_json(), XBOX_NTSC_U) == request


def test_the_options_and_the_input_are_taken_from_the_request() -> None:
    request = parse_request(
        document(
            observe={"heap_events": ["orig"], "cutoff_captures": "all", "capture_budget": 3},
            input={"hold": 4, "release": 8},
        ),
        XBOX_NTSC_U,
    )

    assert (request.options.heap_events, request.options.cutoff_captures, request.options.capture_budget) == (
        frozenset({"ORIG"}),
        True,
        3,
    )
    assert (request.hold, request.release) == (4, 8)


def test_the_hash_is_of_the_files_bytes(tmp_path: Path) -> None:
    path = tmp_path / "route.json"
    path.write_text(json.dumps(document(), indent=4))

    _, digest = read_request(path, XBOX_NTSC_U)

    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_file_that_is_not_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "route.json"
    path.write_text("{")

    with pytest.raises(ValueError, match=r"route\.json is not valid JSON"):
        read_request(path, XBOX_NTSC_U)


def test_an_unknown_field_is_refused_by_name() -> None:
    refused(document(extra=1), "request has an unknown field 'extra'")


def test_an_unknown_step_field_is_refused_by_name() -> None:
    refused(document(steps=[{"scene": "ORIG", "flags": []}]), r"steps\[0\] has an unknown field 'flags'")


def test_a_kind_other_than_record_is_refused() -> None:
    refused(document(kind="landing"), "kind 'landing' is not supported")


def test_a_step_after_the_first_needs_a_menu() -> None:
    refused(document(steps=[{"scene": "ORIG"}, {"scene": "TARG"}]), r"steps\[1\]\.menu is required")


def test_the_first_step_has_no_menu() -> None:
    refused(document(steps=[step()]), r"steps\[0\]\.menu is not allowed")


def test_a_menu_number_counts_from_1() -> None:
    refused(document(steps=[{"scene": "ORIG"}, step(menu={"world": 0, "slot": 1})]), r"steps\[1\]\.menu\.world")


def test_two_costumes_for_one_character_are_refused() -> None:
    refused(
        document(steps=[{"scene": "ORIG"}, step(costumes=["PLSA", "PLSB"])]), r"steps\[1\]\.costumes has more than one"
    )


def test_a_costume_for_each_character_is_allowed() -> None:
    request = parse_request(document(steps=[{"scene": "ORIG"}, step(costumes=["PLSA", "PLPB"])]), XBOX_NTSC_U)

    assert request.steps[1].costumes == ("PLSA", "PLPB")


def test_a_step_names_the_cheats_it_enters() -> None:
    steps = [{"scene": "ORIG", "cheats": ["all-tasks", "all-moves-upgraded"]}]

    request = parse_request(document(steps=steps), XBOX_NTSC_U)

    assert request.steps[0].cheats == ("all-tasks", "all-moves-upgraded")


def test_a_cheat_the_schema_does_not_name_is_refused() -> None:
    refused(
        document(steps=[{"scene": "ORIG", "cheats": ["all-coins"]}]),
        r"steps\[0\]\.cheats\[0\] must be one of all-tasks",
    )


def test_a_cheat_is_named_not_spelled_as_its_presses() -> None:
    refused(
        document(steps=[{"scene": "ORIG", "cheats": ["Y X Y Y X Y X X"]}]), r"steps\[0\]\.cheats\[0\] must be one of"
    )


def test_a_cheat_the_profile_does_not_map_is_refused() -> None:
    cheats = replace(XBOX_NTSC_U.navigation.cheats, names=(("all-tasks", 0x800000),))
    profile = replace(XBOX_NTSC_U, navigation=replace(XBOX_NTSC_U.navigation, cheats=cheats))

    with pytest.raises(ValueError, match=r"steps\[0\]\.cheats has an unknown cheat 'all-health'"):
        parse_request(document(steps=[{"scene": "ORIG", "cheats": ["all-health"]}]), profile)


def test_a_scene_is_four_characters() -> None:
    refused(document(steps=[{"scene": "TOOLONG"}]), r"steps\[0\]\.scene must be a four-character tag")


def test_a_start_is_new_game_or_booted() -> None:
    refused(document(start={"from": "save"}), "start.from must be one of new-game, booted")


def test_a_route_needs_a_step() -> None:
    refused(document(steps=[]), "steps must be a non-empty list")


def test_a_press_is_held_for_a_poll_at_least() -> None:
    refused(document(input={"hold": 0}), "input.hold must be at least 1 poll")
