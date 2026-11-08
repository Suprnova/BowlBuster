import json
import struct
from dataclasses import replace
from pathlib import Path
from typing import Any

from contract import schema_errors
from scripted import PAD_STATE, ScriptedGame
from support import FAST, drive, level, polls
from test_injection import ASSET, ID, TABLE, memory
from test_landing import trip

from bowlharness.driving.request import Request, parse_request

PROFILE = replace(FAST, objects=replace(FAST.objects, lookup_count=16))
STORAGE = PROFILE.bowl_storage
ADDRESS = 0x2B1000
ENTRY = TABLE + 7 * PROFILE.objects.lookup_stride
FOOTPRINT = [struct.pack("<f", value) for _, value in STORAGE.footprint]
ASSET_TARGET = {"asset": {"id": f"0x{ID:08X}", "offset": 0}}
LOOKUP_TARGET = {"lookup": {"id": f"0x{ID:08X}", "offset": -0x38}}


def request(injections: list[dict[str, Any]], *, revisit: bool = False, first_visit_only: bool = False) -> Request:
    steps = [
        {"scene": "ORIG"},
        {"scene": "TARG", "menu": {"world": 2, "slot": 1}},
        {"scene": "EXIT", "menu": {"world": 3, "slot": 1}},
        *([{"scene": "TARG", "menu": {"world": 2, "slot": 1}}] if revisit else []),
    ]
    document = {
        "schema_version": 2,
        "request_id": "inject-targ-1",
        "kind": "inject",
        "start": {"from": "booted"},
        "steps": steps,
        "tests": [{"step": 1, "injections": injections, "first_visit_only": first_visit_only}],
        "windows": {"render": {"unit": "guest-frames", "value": 5}},
    }
    return parse_request(document, PROFILE)


def inject_game(*, revisit: bool = False, lost: bool = False, **world: Any) -> ScriptedGame:
    """ORIG to TARG and on to EXIT, and back with `revisit`, where `lost` leaves the target no base."""
    room = {address: bytes(1) for start in (ASSET, ADDRESS) for address in range(start, start + 0x100)}
    content = room | memory(profile=PROFILE, **world)
    game = ScriptedGame(PROFILE)
    game.menu_scenes({(0, 0): "ORIG", (1, 0): "TARG", (2, 0): "EXIT"})
    level(game, "ORIG", 1)
    trip(game, (1, 0), "TARG", 2, "ORIG")
    game.players_done(content)
    game.pad_poll()
    game.drawn()
    polls(game, 40)
    trip(game, (2, 0), "EXIT", 3, "TARG")
    game.players_done()
    polls(game, 12)
    if revisit:
        trip(game, (1, 0), "TARG", 4, "EXIT")
        game.players_done(memory(profile=PROFILE, base_id=0xBEEF) if lost else content)
        game.pad_poll()
        game.drawn()
        polls(game, 12)
    return game


def harness_writes(session: Any) -> list[tuple[int, bytes]]:
    return [(address, data) for address, data in session._target.writes if address != PAD_STATE]


def stops(session: Any) -> list[int]:
    writes = zip(session._target.writes, session._target.write_stops, strict=True)
    return [stop for (address, _), stop in writes if address != PAD_STATE]


def test_an_asset_is_written_at_players_done_and_a_lookup_at_the_first_draw(tmp_path: Path) -> None:
    injections = [{"target": ASSET_TARGET}, {"target": LOOKUP_TARGET, "words": [0x38]}]

    session, manifest = drive(inject_game(), tmp_path, request(injections))

    footprint = STORAGE.footprint
    assert harness_writes(session) == [
        *((ASSET + offset, bytes(struct.pack("<f", value))) for offset, value in footprint),
        (ENTRY, bytes(4)),
    ]
    assert stops(session) == [PROFILE.points.players_done.entry[0]] * 4 + [PROFILE.points.drawn.entry[0]]
    assert [row["class"] for row in manifest["write_ledger"]] == ["inject"] * 5


def test_the_ledger_names_each_write_and_keeps_the_old_bytes(tmp_path: Path) -> None:
    injections = [{"target": ASSET_TARGET, "words": [0x58]}, {"target": LOOKUP_TARGET, "words": [0x38]}]

    _, manifest = drive(inject_game(), tmp_path, request(injections))

    rows = manifest["write_ledger"]
    assert [row["target"] for row in rows] == [f"asset 0x{ID:08X}+0x58", f"lookup 0x{ID:08X}+0x0"]
    assert rows[1]["old"] == struct.pack("<I", ID).hex()


def test_words_write_only_the_words_picked(tmp_path: Path) -> None:
    injections = [{"target": ASSET_TARGET, "words": [0x5C, 0x38]}]

    session, _ = drive(inject_game(), tmp_path, request(injections))

    assert harness_writes(session) == [(ASSET + 0x38, bytes(4)), (ASSET + 0x5C, FOOTPRINT[2])]


def test_values_write_the_explicit_bytes(tmp_path: Path) -> None:
    injections = [{"target": {"address": ADDRESS}, "values": [{"offset": 4, "hex": "0102"}]}]

    session, manifest = drive(inject_game(), tmp_path, request(injections))

    assert harness_writes(session) == [(ADDRESS + 4, b"\x01\x02")]
    assert manifest["write_ledger"][0]["target"] == "address 0x2b1004"


def test_a_revisit_of_the_scene_is_injected_again(tmp_path: Path) -> None:
    session, manifest = drive(inject_game(revisit=True), tmp_path, request([{"target": ASSET_TARGET}], revisit=True))

    assert len(harness_writes(session)) == 8
    assert [load.counter for load in session._injector.loads] == [2, 4]


def test_first_visit_only_injects_the_target_steps_load_alone(tmp_path: Path) -> None:
    injections = [{"target": ASSET_TARGET}]

    session, _ = drive(inject_game(revisit=True), tmp_path, request(injections, revisit=True, first_visit_only=True))

    assert len(harness_writes(session)) == 4


def test_a_target_the_load_lacks_ends_the_run_not_injected_with_nothing_written(tmp_path: Path) -> None:
    injections = [{"target": ASSET_TARGET}, {"target": {"asset": {"id": "0xBEEF", "offset": 0}}}]

    session, manifest = drive(inject_game(), tmp_path, request(injections))

    assert session._injector.verdict == ("not injected", "no base")
    assert (harness_writes(session), manifest["write_ledger"]) == ([], [])


def test_a_later_loads_missing_target_keeps_the_writes_already_made(tmp_path: Path) -> None:
    game = inject_game(revisit=True, lost=True)

    session, _ = drive(game, tmp_path, request([{"target": ASSET_TARGET}], revisit=True))

    assert session._injector.verdict == ("not injected", "no base")
    assert len(harness_writes(session)) == 4


def test_an_inject_run_is_watched_as_a_control_is(tmp_path: Path) -> None:
    drive(inject_game(), tmp_path, request([{"target": ASSET_TARGET}]))

    written = json.loads((tmp_path / "out" / "result.json").read_text(encoding="utf-8"))
    assert [stage["stage"] for stage in written["stages"]][:3] == ["loading", "held", "in control"]
    assert "render" in [stage["stage"] for stage in written["stages"]]
    assert written["placement"] is None


def result(directory: Path) -> dict[str, Any]:
    return json.loads((directory / "out" / "result.json").read_text(encoding="utf-8"))


def test_an_inject_result_validates_and_records_the_test_and_each_loads_anchors(tmp_path: Path) -> None:
    injections = [{"target": ASSET_TARGET}, {"target": LOOKUP_TARGET, "words": [0x38]}]

    drive(inject_game(revisit=True), tmp_path, request(injections, revisit=True))

    written = result(tmp_path)
    first, second = written["injection"]["loads"]
    assert schema_errors(written, "result") == []
    assert (written["schema_version"], written["kind"], written["outcome"]) == (2, "inject", "survived")
    assert [(i["target"], i["words"]) for i in written["injection"]["injections"]] == [
        (ASSET_TARGET, None),
        (LOOKUP_TARGET, [0x38]),
    ]
    assert (first["counter"], first["scene"], second["counter"]) == (2, "TARG", 4)
    assert [(i["index"], i["timing"], i["anchor"]) for i in first["injections"]] == [
        (0, "after-player-init", ASSET),
        (1, "at-first-draw", ENTRY - 0x38),
    ]
    assert [seq for i in first["injections"] for seq in i["seqs"]] == [
        row["seq"] for row in written["write_ledger"][:5]
    ]


def test_a_missing_target_is_a_not_injected_result_with_its_reason(tmp_path: Path) -> None:
    injections = [{"target": {"asset": {"id": "0xBEEF", "offset": 0}}}]

    drive(inject_game(), tmp_path, request(injections))

    written = result(tmp_path)
    assert schema_errors(written, "result") == []
    assert (written["outcome"], written["cause"], written["write_ledger"]) == ("not injected", "no base", [])
    assert written["integrity"]["flags"] == []
    assert written["injection"]["loads"][0]["injections"][0]["anchor"] is None


def test_explicit_values_are_recorded_as_explicit(tmp_path: Path) -> None:
    injections = [{"target": {"address": ADDRESS}, "values": [{"offset": 0, "hex": "01"}]}]

    drive(inject_game(), tmp_path, request(injections))

    assert result(tmp_path)["injection"]["loads"][0]["injections"][0]["source"] == "explicit"
