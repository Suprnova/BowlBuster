import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from contract import FIXTURES

from bowlharness.driving.request import (
    ControlTest,
    Injection,
    InjectTest,
    LandingTest,
    Menu,
    Recipe,
    Step,
    Target,
    Window,
    Windows,
    default_windows,
    parse_request,
    read_request,
)
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
    assert request.to_json()["input"] == {"hold": 1, "release": 1}


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


def test_an_unknown_kind_is_refused() -> None:
    refused(document(kind="chain"), "kind must be one of record, landing, control, inject")


def landing(**changes: Any) -> dict[str, Any]:
    base = json.loads((FIXTURES / "requests" / "landing.json").read_text(encoding="utf-8"))
    return base | changes


def with_test(**changes: Any) -> dict[str, Any]:
    test = landing()["tests"][0] | changes
    return landing(tests=[test])


def test_a_landing_request_is_read_with_its_test_and_windows() -> None:
    request = parse_request(landing(), XBOX_NTSC_U)

    assert request.kind == "landing"
    assert request.test == LandingTest(
        1, Recipe("route-1-1", 0, 3), 12, -24, 48, bytes.fromhex("00112233445566778899aabbccddeeff")
    )
    assert request.windows == Windows(
        Window("guest-frames", 1200), Window("guest-frames", 900), Window("wall-seconds", 120)
    )


def test_a_landing_requests_manifest_copy_reads_back_the_same() -> None:
    request = parse_request(landing(), XBOX_NTSC_U)

    assert parse_request(request.to_json(), XBOX_NTSC_U) == request


def test_windows_left_out_take_their_defaults() -> None:
    request = parse_request(landing(windows={"render": {"unit": "wall-seconds", "value": 5}}), XBOX_NTSC_U)

    assert request.windows == Windows(
        Window("wall-seconds", 5), Window("guest-frames", 900), Window("wall-seconds", 120)
    )


def test_a_control_request_is_read_with_its_step() -> None:
    document = json.loads((FIXTURES / "requests" / "control.json").read_text(encoding="utf-8"))

    request = parse_request(document, XBOX_NTSC_U)

    assert (request.kind, request.test, request.windows) == ("control", ControlTest(1), default_windows(XBOX_NTSC_U))


def test_a_test_step_is_the_last_or_the_one_before_the_exit() -> None:
    refused(with_test(step=0), r"tests\[0\]\.step must be the route's last step")


def test_the_test_step_enters_no_cheats() -> None:
    steps = landing()["steps"]
    steps[1]["cheats"] = ["all-tasks"]

    refused(landing(steps=steps), r"steps\[1\]\.cheats is not allowed")


def test_the_exit_step_enters_no_cheats() -> None:
    steps = landing()["steps"]
    steps[2]["cheats"] = ["all-tasks"]

    refused(landing(steps=steps), r"steps\[2\]\.cheats is not allowed")


def test_the_exit_step_wears_the_test_steps_costumes() -> None:
    steps = landing()["steps"]
    steps[1]["costumes"] = ["PLSA"]

    refused(landing(steps=steps), r"steps\[2\]\.costumes must be the test step's")


def test_expected_bytes_are_lower_case_hex() -> None:
    refused(with_test(expected={"offset": 48, "bytes": "AABB"}), r"tests\[0\]\.expected\.bytes must be lower-case hex")


def test_a_match_fraction_is_from_0_to_1() -> None:
    refused(with_test(min_match=1.5), r"tests\[0\]\.min_match must be from 0 to 1")


def test_a_window_is_longer_than_nothing() -> None:
    refused(landing(windows={"reset": {"unit": "guest-frames", "value": 0}}), r"windows\.reset\.value must be above 0")


@pytest.mark.parametrize("recording", ["C:/recordings/route-1", "/route-1", "../route-1", "store\\route-1"])
def test_a_recipe_names_a_folder_under_the_recordings_root(recording: str) -> None:
    refused(with_test(recipe={"recording": recording, "segment": 0, "load": 3}), r"tests\[0\]\.recipe\.recording")


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


def inject(**changes: Any) -> dict[str, Any]:
    base = json.loads((FIXTURES / "requests" / "inject.json").read_text(encoding="utf-8"))
    return base | changes


def with_inject_test(**changes: Any) -> dict[str, Any]:
    return inject(tests=[inject()["tests"][0] | changes])


def with_injection(**changes: Any) -> dict[str, Any]:
    injection = {"target": {"address": 4096}} | changes
    return with_inject_test(injections=[injection])


def test_an_inject_request_is_read_with_its_injections_and_default_windows() -> None:
    request = parse_request(inject(), XBOX_NTSC_U)

    assert request.kind == "inject"
    assert request.test == InjectTest(
        1,
        (
            Injection(Target("asset", 0x1A2B3C4D, 0)),
            Injection(Target("lookup", 0xBEEF, -56), words=(56,)),
            Injection(Target("address", None, 2863104), values=((4, bytes.fromhex("0102")),)),
        ),
    )
    assert request.windows == default_windows(XBOX_NTSC_U)


def test_an_inject_requests_manifest_copy_reads_back_the_same() -> None:
    request = parse_request(inject(), XBOX_NTSC_U)

    assert parse_request(request.to_json(), XBOX_NTSC_U) == request


def test_an_inject_requests_manifest_copy_spells_ids_and_addresses_as_the_file_does() -> None:
    request = parse_request(inject(), XBOX_NTSC_U)

    assert request.to_json()["tests"] == inject()["tests"]


def test_an_injection_is_explicit_with_values_and_the_footprint_otherwise() -> None:
    injections = parse_request(inject(), XBOX_NTSC_U).test.injections

    assert [injection.source for injection in injections] == ["footprint", "footprint", "explicit"]


def test_a_version_1_request_is_still_read() -> None:
    document = json.loads((FIXTURES / "requests" / "landing.json").read_text(encoding="utf-8"))

    assert parse_request(document, XBOX_NTSC_U).kind == "landing"


def test_an_inject_request_is_version_2() -> None:
    refused(inject(schema_version=1), r"schema_version")


def test_the_inject_step_must_exist() -> None:
    refused(with_inject_test(step=9), r"tests\[0\]\.step must be the index of a step, below 4")


def test_the_inject_step_enters_no_cheats() -> None:
    steps = inject()["steps"]
    steps[1]["cheats"] = ["all-tasks"]

    refused(inject(steps=steps), r"steps\[1\]\.cheats is not allowed")


def test_the_exit_after_the_inject_step_enters_no_cheats_and_wears_its_costumes() -> None:
    steps = inject()["steps"]
    steps[2]["costumes"] = ["PLSA"]

    refused(inject(steps=steps), r"steps\[2\]\.costumes must be the test step's")


def test_steps_may_follow_the_exit() -> None:
    assert len(parse_request(inject(), XBOX_NTSC_U).steps) == 4


def test_words_are_the_footprints_offsets() -> None:
    refused(with_injection(words=[57]), r"tests\[0\]\.injections\[0\]\.words has 57, which is not one of")


def test_words_and_values_are_not_both_given() -> None:
    refused(
        with_injection(words=[56], values=[{"offset": 0, "hex": "00"}]),
        r"tests\[0\]\.injections\[0\] has both words and values",
    )


@pytest.mark.parametrize("hex_text", ["abc", "AB", "zz"])
def test_explicit_values_are_lower_case_hex_of_whole_bytes(hex_text: str) -> None:
    refused(with_injection(values=[{"offset": 0, "hex": hex_text}]), r"hex")


def test_first_visit_only_needs_the_scenes_first_load() -> None:
    steps = inject()["steps"]

    refused(
        with_inject_test(step=3, first_visit_only=True) | {"steps": steps},
        r"tests\[0\]\.first_visit_only is not allowed: steps\[3\] is not the first load of TARG",
    )


def test_first_visit_only_on_the_first_load_is_read() -> None:
    request = parse_request(with_inject_test(first_visit_only=True), XBOX_NTSC_U)

    assert request.test.first_visit_only


def test_an_inject_request_holds_one_test() -> None:
    refused(inject(tests=inject()["tests"] * 2), "tests must hold exactly one test")
