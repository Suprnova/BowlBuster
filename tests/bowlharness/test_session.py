import json
from pathlib import Path

import pytest
from support import names

from bowlharness.mock import MockTarget
from bowlharness.recorder import Options
from bowlharness.scripted import ScriptedGame
from bowlharness.session import ENDED, PAUSED, Session
from bowlharness.target import TargetError


def open_session(game: ScriptedGame, tmp_path: Path, target: MockTarget | None = None, **kwargs) -> Session:
    return Session(
        target or game.build(kernel_loaded=True),
        game.profile,
        tmp_path / "out",
        Options(),
        run_stem="s",
        environment={"emulator": {"name": "xemu"}, "disc": {"image": "disc.iso"}},
        **kwargs,
    )


def events_of(tmp_path: Path, number: int) -> list[dict]:
    return [json.loads(line) for line in (tmp_path / "out" / f"s-{number}" / "events.jsonl").read_text().splitlines()]


def manifest_of(tmp_path: Path, number: int) -> dict:
    return json.loads((tmp_path / "out" / f"s-{number}" / "manifest.json").read_text())


def one_load() -> ScriptedGame:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.drawn()
    return game


def test_the_guest_is_paused_when_it_stops_and_a_person_can_stop_the_session(tmp_path: Path) -> None:
    session = open_session(one_load(), tmp_path)

    state = session.run()
    session.stop()

    manifest = manifest_of(tmp_path, 1)
    assert (state, session.ended) == (PAUSED, True)
    assert names(events_of(tmp_path, 1))[-1] == "pause"
    assert (manifest["complete"], manifest["ended"], manifest["attended"]) == (True, "stopped", True)


def test_resuming_is_logged_and_runs_the_guest_on(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    session = open_session(game, tmp_path)
    session.run()

    session.resume()

    assert names(events_of(tmp_path, 1))[-2:] == ["resume", "pause"]


def test_a_capture_in_a_pause_is_manual_and_labelled(tmp_path: Path) -> None:
    session = open_session(one_load(), tmp_path)
    session.run()

    capture_id = session.capture("before the warp")
    session.stop()

    manifest = manifest_of(tmp_path, 1)
    assert (capture_id, [c["label"] for c in manifest["captures"]]) == ("0-2-manual", ["before the warp"])
    assert (tmp_path / "out" / "s-1" / "captures" / "0-2-manual" / "complete").exists()


def test_a_read_in_a_pause_is_logged_without_its_bytes(tmp_path: Path) -> None:
    session = open_session(one_load(), tmp_path)
    session.run()

    data = session.read(0x2B76B8, 4)

    read = next(e for e in events_of(tmp_path, 1) if e["event"] == "read")
    assert (data, read["address"], read["length"]) == (b"\x02\x00\x00\x00", 0x2B76B8, 4)
    assert set(read) == {"seq", "segment", "frame", "event", "address", "length"}


def test_the_controls_need_a_paused_guest(tmp_path: Path) -> None:
    session = open_session(one_load(), tmp_path)
    session.run()
    session.stop()

    with pytest.raises(RuntimeError, match="ended"):
        session.capture("too late")


def test_a_reboot_ends_the_recording_and_opens_another(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.drawn()
    game.scene_init("BOOT", 1, caller=game.profile.boot_return)
    game.drawn()
    session = open_session(game, tmp_path)

    session.run()
    session.stop()

    first, second = manifest_of(tmp_path, 1), manifest_of(tmp_path, 2)
    assert session.recordings == 2
    assert (first["complete"], first["ended"], [load["scene"] for load in first["loads"]]) == (True, "reboot", ["ORIG"])
    assert [load["scene"] for load in second["loads"]] == ["BOOT"]
    assert (second["boot_path"], second["segments"][0]["reason"]) == ("reboot", "reboot")
    assert names(events_of(tmp_path, 2))[:3] == ["segment", "scene_init", "drawn"]
    assert "BOOT" not in [e.get("scene") for e in events_of(tmp_path, 1)]


def test_the_first_boot_scene_init_is_not_a_reboot(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("BOOT", 1, caller=game.profile.boot_return)
    session = open_session(game, tmp_path)

    session.run()

    assert session.recordings == 1


def test_the_environment_is_in_every_manifest(tmp_path: Path) -> None:
    session = open_session(one_load(), tmp_path, boot_path="attached")

    session.run()

    manifest = manifest_of(tmp_path, 1)
    assert (manifest["emulator"], manifest["boot_path"], manifest["segments"][0]["reason"]) == (
        {"name": "xemu"},
        "attached",
        "attach",
    )
    assert manifest["disc"] == {"platform": "xbox", "image": "disc.iso"}


def test_an_emulator_that_exits_interrupts_the_recording(tmp_path: Path) -> None:
    class Exiting(MockTarget):
        def run(self, timeout: float | None = None) -> bool:
            raise TargetError("connection closed")

    game = one_load()
    session = open_session(game, tmp_path, Exiting(game.script))

    session.run()

    manifest = manifest_of(tmp_path, 1)
    assert (manifest["complete"], manifest["interrupted"]) == (False, "emulator exited: connection closed")


def test_a_crash_ends_the_session_with_a_complete_recording(tmp_path: Path) -> None:
    game = one_load()
    game.bugcheck("KeBugCheck", 0x7B)
    session = open_session(game, tmp_path)

    state = session.run()

    manifest = manifest_of(tmp_path, 1)
    assert (state, manifest["complete"], manifest["ended"], manifest["crash"]["code"]) == (ENDED, True, "crash", 0x7B)


def test_a_hang_ends_the_session(tmp_path: Path) -> None:
    game = one_load()
    for frame in (10, 10, 10):
        game.idle(5, frame)
    session = open_session(game, tmp_path)

    state = session.run()

    manifest = manifest_of(tmp_path, 1)
    assert (state, manifest["ended"], manifest["hang"]["scene"]) == (ENDED, "hang", "ORIG")


def test_the_end_is_announced_once(tmp_path: Path) -> None:
    ends = []
    session = open_session(one_load(), tmp_path, on_end=lambda: ends.append(1))
    session.run()

    session.stop()
    session.stop()

    assert ends == [1]


def test_a_session_folder_that_exists_is_refused(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()

    with pytest.raises(FileExistsError):
        open_session(one_load(), tmp_path)
