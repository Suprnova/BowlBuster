import json
import struct
from pathlib import Path

from scripted import ScriptedGame

from bowlharness.backends.mock import MockTarget
from bowlharness.recording.recorder import Options, Recorder

SPHERE = 0x317234
STATIC = 0x31722C


def writing_at_players_done(game: ScriptedGame, directory: Path, address: int, data: bytes) -> MockTarget:
    """Records ``game``, writing ``data`` at ``address`` through the recorder when players are done."""
    target = game.build()
    recorder = Recorder(target, game.profile, directory, "run-1", Options())

    def at(event: str, fields: dict[str, object]) -> None:
        if event == "players_done":
            recorder.write("bowl-storage", "sphere", address, data)

    recorder.listen(at)
    recorder.start("attach")
    target.run()
    recorder.finish()
    return target


def events(directory: Path) -> list[dict]:
    return [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]


def manifest(directory: Path) -> dict:
    return json.loads((directory / "manifest.json").read_text())


def test_a_write_is_an_event_and_a_ledger_row_with_its_old_and_new_bytes(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.watch(SPHERE, 0x5C0500)
    game.players_done()

    writing_at_players_done(game, tmp_path, SPHERE, struct.pack("<I", 0x5C1000))

    write = next(event for event in events(tmp_path) if event["event"] == "write")
    assert (write["class"], write["target"], write["address"], write["old"], write["new"]) == (
        "bowl-storage",
        "sphere",
        SPHERE,
        "00055c00",
        "00105c00",
    )
    assert manifest(tmp_path)["write_ledger"] == [
        {key: write[key] for key in ("seq", "class", "target", "address", "old", "new")}
    ]


def test_the_write_reaches_the_guest_at_the_stop_it_was_made_at(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.players_done()

    target = writing_at_players_done(game, tmp_path, SPHERE, struct.pack("<I", 0x5C1000))

    assert (target.writes, target.write_stops) == (
        [(SPHERE, struct.pack("<I", 0x5C1000))],
        [game.profile.points.players_done.entry[0]],
    )


def test_a_game_write_after_a_harness_write_reports_the_harness_value_as_old(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.players_done()
    game.watch(SPHERE, 0x5C2000)

    writing_at_players_done(game, tmp_path, SPHERE, struct.pack("<I", 0x5C1000))

    watch = next(event for event in events(tmp_path) if event["event"] == "watch")
    assert (watch["old"], watch["new"]) == (0x5C1000, 0x5C2000)


def test_a_write_that_covers_part_of_a_watched_dword_keeps_the_whole_dword(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.watch(SPHERE, 0x5C0500)
    game.players_done()
    game.watch(SPHERE, 0x5C2000)

    writing_at_players_done(game, tmp_path, SPHERE + 1, b"\x10")

    watch = [event for event in events(tmp_path) if event["event"] == "watch"][-1]
    assert watch["old"] == 0x5C1000


def test_a_run_with_no_write_has_an_empty_ledger(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.players_done()
    target = game.build()
    recorder = Recorder(target, game.profile, tmp_path, "run-1", Options())

    recorder.start("attach")
    target.run()
    recorder.finish()

    assert (manifest(tmp_path)["write_ledger"], target.writes) == ([], [])
