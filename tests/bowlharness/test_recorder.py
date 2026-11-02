import json
import os
from pathlib import Path

from bowlharness.mock import MockTarget
from bowlharness.profiles import XBOX_NTSC_U
from bowlharness.recorder import DuplicateFilter, Hit, Options, Recorder
from bowlharness.scripted import ScriptedGame


def record(game: ScriptedGame, directory: Path, options: Options | None = None) -> tuple[list[dict], dict, MockTarget]:
    target = game.build()
    recorder = Recorder(target, XBOX_NTSC_U, directory, "run-1", options or Options())
    recorder.start("attach")
    target.run()
    recorder.finish()
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    return events, json.loads((directory / "manifest.json").read_text()), target


def names(events: list[dict]) -> list[str]:
    return [event["event"] for event in events]


def three_loads() -> ScriptedGame:
    game = ScriptedGame()
    game.scene_init("ORIG", 2, extras={1: 1, 4: 1}, last_block=(0x5C0100, 0x40))
    game.alloc(0, 0x40, 0x10, 0x5C0140)
    game.drawn()
    game.scene_exit("ORIG", 2)
    game.scene_init("TARG", 3, depth=1, extras={2: 1}, cheats=0x2000000)
    game.push(0, 0)
    game.model(0x3000, 5, 0x40)
    game.drawn()
    game.scene_exit("TARG", 3)
    game.scene_init("TARG", 4, cheats=0x10000000)
    game.drawn()
    return game


def test_three_loads_produce_the_expected_stream_and_manifest(tmp_path: Path) -> None:
    events, manifest, _ = record(three_loads(), tmp_path)

    assert [(e["seq"], e["event"]) for e in events] == [
        (0, "segment"),
        (1, "scene_init"),
        (2, "alloc"),
        (3, "drawn"),
        (4, "scene_exit"),
        (5, "scene_init"),
        (6, "push"),
        (7, "model"),
        (8, "drawn"),
        (9, "scene_exit"),
        (10, "scene_init"),
        (11, "drawn"),
    ]
    assert events[1] == {
        "seq": 1,
        "segment": 0,
        "frame": 1,
        "event": "scene_init",
        "scene": "ORIG",
        "caller": 0x528B6,
        "counter": 2,
        "heap": {
            "depth": 0,
            "states": [{"cursor": 0x5C0130, "blocks": 1, "used": 0x100, "wasted": 0}],
            "last_block": {"address": 0x5C0100, "size": 0x40},
        },
    }
    assert events[2] == {
        "seq": 2,
        "segment": 0,
        "frame": 2,
        "event": "alloc",
        "heap": 0,
        "size": 0x40,
        "alignment": 0x10,
        "address": 0x5C0140,
        "caller": 0x1000,
    }
    assert events[7]["nodes"] == 5
    assert manifest["loads"] == [
        {
            "segment": 0,
            "counter": 2,
            "scene": "ORIG",
            "first_seq": 1,
            "costumes": {"spongebob": "PLSB", "patrick": "PLP1"},
        },
        {
            "segment": 0,
            "counter": 3,
            "scene": "TARG",
            "first_seq": 5,
            "costumes": {"spongebob": "PLSD", "patrick": None},
        },
        {
            "segment": 0,
            "counter": 4,
            "scene": "TARG",
            "first_seq": 10,
            "costumes": {"spongebob": None, "patrick": "PLPA"},
        },
    ]
    assert manifest["complete"] is True
    assert manifest["passive"] is True
    assert manifest["write_ledger"] == []


def test_pop_reports_the_heap_it_entered_with_and_the_depth_it_returned(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.pop(heap=0, depth=3)

    events, _, _ = record(game, tmp_path)

    assert [(e["heap"], e["depth"]) for e in events if e["event"] == "pop"] == [(0, 3)]


def test_failed_model_allocation_reports_no_nodes(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.model(instance=0, nodes=0, flags=0x40)

    events, _, _ = record(game, tmp_path)

    assert [(e["instance"], e["nodes"], e["bypass"]) for e in events if e["event"] == "model"] == [(0, 0, False)]


def test_pool_free_and_grow_are_logged(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.grow(0, 0x20)
    game.pool_free(0x3000)

    events, _, _ = record(game, tmp_path)

    assert [(e["event"], e.get("size"), e.get("instance")) for e in events[2:]] == [
        ("grow", 0x20, None),
        ("pool_free", None, 0x3000),
    ]


def test_heap_events_off_still_logs_the_scene_init_heap_state(tmp_path: Path) -> None:
    game = three_loads()

    events, _, _ = record(game, tmp_path, Options(heap_events=False))

    assert names(events) == [
        "segment",
        "scene_init",
        "drawn",
        "scene_exit",
        "scene_init",
        "drawn",
        "scene_exit",
        "scene_init",
        "drawn",
    ]
    assert all("heap" in e for e in events if e["event"] == "scene_init")


def test_heap_events_for_listed_scenes_only(tmp_path: Path) -> None:
    game = three_loads()

    events, _, _ = record(game, tmp_path, Options(heap_events=frozenset({"TARG"})))

    assert [e["event"] for e in events if e["event"] in {"alloc", "push", "model"}] == ["push", "model"]


def test_drawn_is_logged_once_per_load(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.drawn()
    game.drawn()
    game.scene_init("TARG", 3)
    game.drawn()

    events, _, _ = record(game, tmp_path)

    assert names(events).count("drawn") == 2


def test_a_counter_jump_logs_a_gap(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.scene_init("TARG", 5)

    events, _, _ = record(game, tmp_path)

    assert [(e["counter"], e["expected"]) for e in events if e["event"] == "counter_gap"] == [(5, 3)]


def test_a_boot_after_a_load_is_not_a_gap(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 4)
    game.scene_init("BOOT", 1, caller=XBOX_NTSC_U.boot_return)

    events, _, _ = record(game, tmp_path)

    assert "counter_gap" not in names(events)


def test_a_failed_read_counts_one_dropped_event_and_recording_goes_on(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.stop(XBOX_NTSC_U.points.grow.entry[0], (0, 0, 0), esp=0x9000)
    game.grow(0, 0x20)

    events, manifest, _ = record(game, tmp_path)

    assert (manifest["events_dropped"], names(events)) == (1, ["segment", "scene_init", "grow"])


def test_a_repeated_stop_is_discarded_and_counted(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.grow(0, 0x20)
    game.grow(0, 0x20)

    events, manifest, _ = record(game, tmp_path)

    assert (manifest["duplicates_discarded"], names(events).count("grow")) == (1, 1)


def test_a_repeated_stop_is_kept_at_an_exempt_address() -> None:
    hit = Hit({"esp": 1, "eax": 2}, (3,))
    duplicates = DuplicateFilter(frozenset({0x54380}))

    assert [duplicates.discards(0x54380, hit), duplicates.discards(0x54380, hit)] == [False, False]


def test_a_passive_run_writes_nothing_to_the_guest(tmp_path: Path) -> None:
    _, _, target = record(three_loads(), tmp_path)

    assert target.writes == []


def test_an_interrupted_recording_is_incomplete_and_says_why(tmp_path: Path) -> None:
    target = ScriptedGame().build()
    recorder = Recorder(target, XBOX_NTSC_U, tmp_path, "run-1", Options())
    recorder.start("attach")

    recorder.finish(interrupted="emulator exited")

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert (manifest["complete"], manifest["interrupted"]) == (False, "emulator exited")


def test_manifest_is_incomplete_until_the_recording_ends(tmp_path: Path) -> None:
    target = ScriptedGame().build()
    recorder = Recorder(target, XBOX_NTSC_U, tmp_path, "run-1", Options())

    recorder.start("attach")

    assert json.loads((tmp_path / "manifest.json").read_text())["complete"] is False


FIXTURE = Path(__file__).parents[1] / "BowlBuster.Tests" / "Recordings" / "Fixtures" / "synthetic"


def test_the_committed_fixture_is_what_the_recorder_writes(tmp_path: Path) -> None:
    record(three_loads(), tmp_path)

    if os.environ.get("BOWL_UPDATE_FIXTURE"):
        FIXTURE.mkdir(parents=True, exist_ok=True)
        for name in ("manifest.json", "events.jsonl"):
            (FIXTURE / name).write_bytes((tmp_path / name).read_bytes())

    for name in ("manifest.json", "events.jsonl"):
        assert (tmp_path / name).read_bytes() == (FIXTURE / name).read_bytes()
