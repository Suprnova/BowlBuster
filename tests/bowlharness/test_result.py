import json
from pathlib import Path
from typing import Any

import pytest
from contract import schema_errors
from scripted import ScriptedGame
from support import DIGEST, drive, route

from bowlharness.contract.documents import read_document, write_document
from bowlharness.contract.generated import result_schema
from bowlharness.profiles import XBOX_NTSC_U
from bowlharness.recording.result import harness_version, moment, write_result
from bowlharness.session.session import PAUSED


def loaded(scene: str = "ORIG", polls: int = 14) -> ScriptedGame:
    game = ScriptedGame()
    game.scene_init(scene, 1)
    game.players_done()
    for _ in range(polls):
        game.pad_poll()
    return game


def result(directory: Path) -> dict[str, Any]:
    return json.loads((directory / "out" / "result.json").read_text(encoding="utf-8"))


def test_a_done_route_survives(tmp_path: Path) -> None:
    drive(loaded(), tmp_path, route("ORIG"))

    written = result(tmp_path)

    assert (written["outcome"], written["cause"], written["run"], written["attempt"]) == (
        "survived",
        None,
        "route-1-a1",
        1,
    )
    assert schema_errors(written, "result") == []


def test_the_manifest_states_what_a_reproduction_restores(tmp_path: Path) -> None:
    request, game = route("ORIG"), loaded()
    drive(game, tmp_path, request)

    manifest = result(tmp_path)["manifest"]

    assert (manifest["harness"], manifest["platform"], manifest["profile"], manifest["request_sha256"]) == (
        "0.1.0+test",
        game.profile.name,
        game.profile.digest,
        DIGEST,
    )
    assert (manifest["recordings"], manifest["setup"], manifest["input"]) == (
        ["s-1"],
        "booted",
        request.to_json()["input"],
    )
    assert (manifest["observation"], manifest["windows"], manifest["placement_tool"]) == (
        request.to_json()["observe"],
        None,
        None,
    )
    assert [(load["recording"], load["scene"]) for load in manifest["loads"]] == [("s-1", "ORIG")]
    assert manifest["save"] is None


def test_a_failed_step_gives_its_reason_as_the_outcome(tmp_path: Path) -> None:
    drive(loaded("TARG"), tmp_path, route("ORIG"))

    written = result(tmp_path)

    assert (written["outcome"], written["manifest"]["steps"][0]["reason"]) == ("scene change", "scene change")
    assert schema_errors(written, "result") == []


def test_a_crash_gives_its_record_and_keeps_its_registers_and_stack_in_memory(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 1)
    game.bugcheck("KeBugCheckEx", 0x1E, 0xC0000005, 0x182BC5, 1, 0x41414140)

    drive(game, tmp_path, route("ORIG"))

    written = result(tmp_path)
    crash = written["crash"]
    assert (written["outcome"], crash["access"], crash["accessed"]) == ("crash", "write", 0x41414140)
    assert "registers" not in written["crash"] and written["memory"]["crash"]["stack"]
    assert schema_errors(written, "result") == []


def test_a_session_a_person_stopped_is_interrupted(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 1)
    session, _ = drive(game, tmp_path, route("ORIG"))
    assert session.run() == PAUSED

    session.stop()

    written = result(tmp_path)
    assert (written["outcome"], written["cause"]) == ("interrupted", "stopped")
    assert schema_errors(written, "result") == []


def test_a_reboot_interrupts_the_route(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 1)
    game.scene_init("MNUS", 1, caller=XBOX_NTSC_U.boot_return)
    game.pad_poll()

    drive(game, tmp_path, route("ORIG"))

    assert (result(tmp_path)["outcome"], result(tmp_path)["cause"]) == ("interrupted", "reboot")


def test_a_press_is_in_the_result_with_the_recording_it_was_given_in(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 1)
    game.players_done()
    for _ in range(3):
        game.pad_poll(physical=XBOX_NTSC_U.input.buttons.a)
    for _ in range(14):
        game.pad_poll()

    drive(game, tmp_path, route("ORIG"))

    written = result(tmp_path)
    assert [(row["recording"], row["source"]) for row in written["input_ledger"]] == [("s-1", "person")]
    assert written["attended"] is True


def test_a_result_reads_back_as_the_type_it_was_written_from(tmp_path: Path) -> None:
    drive(loaded(), tmp_path, route("ORIG"))

    read = read_document(result_schema.Result, result(tmp_path), "result")

    assert write_document(read) == result(tmp_path)


def test_a_version_2_result_without_a_save_still_reads(tmp_path: Path) -> None:
    drive(loaded(), tmp_path, route("ORIG"))
    written = result(tmp_path)
    del written["manifest"]["save"]
    written["schema_version"] = 2

    read = read_document(result_schema.Result, written, "result")

    assert (read.schema_version, read.manifest.save) == (2, None) and schema_errors(written, "result") == []


def test_a_result_is_never_rewritten(tmp_path: Path) -> None:
    drive(loaded(), tmp_path, route("ORIG"))
    read = read_document(result_schema.Result, result(tmp_path), "result")

    with pytest.raises(FileExistsError):
        write_result(tmp_path / "out" / "result.json", read)


def test_the_harness_version_names_the_commit_it_runs_from() -> None:
    assert harness_version().startswith("0.1.0+")


def test_the_harness_version_outside_a_repository_is_the_projects(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")

    assert harness_version(tmp_path) == "1.2.3"


def test_a_moment_is_utc_to_the_second() -> None:
    assert moment(5).wall.endswith("Z") and moment(5).frame == 5
