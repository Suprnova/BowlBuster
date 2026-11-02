import json
import os
from pathlib import Path

from scripted import ScriptedGame
from support import names, record, run, three_loads

from bowlharness.backends.mock import MockTarget
from bowlharness.profiles import XBOX_NTSC_U
from bowlharness.recording.recorder import DuplicateFilter, Hit, Options, Recorder
from bowlharness.target import TargetError


def test_three_loads_produce_the_expected_stream_and_manifest(tmp_path: Path) -> None:
    events, manifest, _ = record(three_loads(), tmp_path)

    assert [(e["seq"], e["event"]) for e in events] == [
        (0, "segment"),
        (1, "scene_init"),
        (2, "alloc"),
        (3, "alloc"),
        (4, "drawn"),
        (5, "scene_exit"),
        (6, "scene_init"),
        (7, "push"),
        (8, "model"),
        (9, "drawn"),
        (10, "scene_exit"),
        (11, "scene_init"),
        (12, "drawn"),
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
    assert events[3]["layer"] == {"archive": "TARG", "layer": 1}
    assert events[8]["nodes"] == 5
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
            "first_seq": 6,
            "costumes": {"spongebob": "PLSD", "patrick": None},
        },
        {
            "segment": 0,
            "counter": 4,
            "scene": "TARG",
            "first_seq": 11,
            "costumes": {"spongebob": None, "patrick": "PLPA"},
        },
    ]
    assert manifest["complete"] is True
    assert manifest["passive"] is True
    assert manifest["write_ledger"] == []


def test_a_layer_block_names_its_archive_and_layer(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.layer_alloc(0x3000, 0x5C2000, "TARG", layers=4, index=2)

    events, _, _ = record(game, tmp_path)

    assert events[-1]["layer"] == {"archive": "TARG", "layer": 2}


def test_an_asset_directory_block_has_no_layer(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.layer_alloc(0x600, 0x5C2000, "TARG", layers=4, index=2, directory=True)

    events, _, _ = record(game, tmp_path)

    assert "layer" not in events[-1]


def test_a_layer_block_with_no_layer_loading_is_logged_without_one(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.layer_alloc(0x3000, 0x5C2000, "TARG", layers=4, index=2)
    game.stop(
        XBOX_NTSC_U.points.alloc.returns[-1],
        (XBOX_NTSC_U.layers.site, 0, 8, 0x40, 0, 0, XBOX_NTSC_U.layers.layer_return),
    )

    events, manifest, _ = record(game, tmp_path)

    assert (manifest["events_dropped"], names(events)[-2:]) == (0, ["alloc", "alloc"])


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
    hit = Hit(0x54380, None, {"esp": 1, "eax": 2}, (3,))
    duplicates = DuplicateFilter(frozenset({0x54380}))

    assert [duplicates.discards(hit), duplicates.discards(hit)] == [False, False]


def test_a_passive_run_writes_nothing_to_the_guest(tmp_path: Path) -> None:
    _, _, target = record(three_loads(), tmp_path)

    assert target.writes == []


def test_an_interrupted_recording_is_incomplete_and_says_why(tmp_path: Path) -> None:
    recorder, _ = run(ScriptedGame(), tmp_path)

    recorder.finish(interrupted="emulator exited")

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert (manifest["complete"], manifest["interrupted"]) == (False, "emulator exited")


def test_manifest_is_incomplete_until_the_recording_ends(tmp_path: Path) -> None:
    run(ScriptedGame(), tmp_path)

    assert json.loads((tmp_path / "manifest.json").read_text())["complete"] is False


def test_the_leaked_player_entity_is_logged(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.entity(0x5C4000)

    events, _, _ = record(game, tmp_path)

    assert [e["address"] for e in events if e["event"] == "entity"] == [0x5C4000]


def test_players_done_logs_the_scene_the_counter_and_the_bowl_statics(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.players_done()

    events, _, _ = record(game, tmp_path)

    done = events[-1]
    assert (done["event"], done["scene"], done["counter"]) == ("players_done", "ORIG", 2)
    assert done["bowl"] == {"address": 0x31722C, "words": list(range(1, 11))}


def test_scene_id_is_read_from_the_scene_object(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.scene_id(0x1234)

    events, _, _ = record(game, tmp_path)

    assert [(e["scene"], e["counter"], e["id"]) for e in events if e["event"] == "scene_id"] == [("ORIG", 2, 0x1234)]


def test_first_stale_write_is_logged_once_per_load(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.stale_write(0x5C1000)
    game.stale_write(0x5C1000)
    game.scene_init("TARG", 3)
    game.stale_write(0x5C2000)

    events, _, _ = record(game, tmp_path)

    writes = [e for e in events if e["event"] == "first_stale_write"]
    assert [(w["scene"], w["counter"], w["s"]) for w in writes] == [("ORIG", 2, 0x5C1000), ("TARG", 3, 0x5C2000)]
    assert writes[0]["bowl"]["address"] == 0x31722C


def test_a_watched_write_logs_the_old_and_new_values_the_instruction_and_a_stack(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.watch(0x2B13EC, 3, pc=0x9601)
    game.watch(0x2B13EC, 4, pc=0x9602)

    events, _, _ = record(game, tmp_path)

    watches = [e for e in events if e["event"] == "watch"]
    assert [(w["address"], w["old"], w["new"], w["pc"]) for w in watches] == [
        (0x2B13EC, 0, 3, 0x9601),
        (0x2B13EC, 3, 4, 0x9602),
    ]
    assert watches[0]["stack"] == list(range(1, 18))


def test_consecutive_identical_watched_writes_are_all_logged(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.watch(0x2B13EC, 3)
    game.watch(0x2B13EC, 3)

    events, manifest, _ = record(game, tmp_path)

    assert (names(events).count("watch"), manifest["duplicates_discarded"]) == (2, 0)


def test_watches_are_armed_once(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.scene_init("TARG", 3)
    game.watch(0x317234, 7)

    events, _, _ = record(game, tmp_path)

    assert names(events).count("watch") == 1


def test_a_reset_logs_the_counter(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.reset()

    events, _, _ = record(game, tmp_path)

    assert [e["counter"] for e in events if e["event"] == "reset"] == [2]


FIXTURE = Path(__file__).parents[1] / "BowlBuster.Tests" / "Recordings" / "Fixtures" / "synthetic"


def pinned_profile(directory: Path) -> None:
    """Replaces the profile's hash with a fixed one, so the fixture changes only with the recording's format."""
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["profile"] = "synthetic"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")


def files_under(directory: Path) -> dict[Path, bytes]:
    return {path.relative_to(directory): path.read_bytes() for path in sorted(directory.rglob("*")) if path.is_file()}


def test_the_committed_fixture_is_what_the_recorder_writes(tmp_path: Path) -> None:
    record(three_loads(), tmp_path, Options(cutoff_captures=frozenset({"ORIG"})))
    pinned_profile(tmp_path)
    written = files_under(tmp_path)

    if os.environ.get("BOWL_UPDATE_FIXTURE"):
        for stale in files_under(FIXTURE).keys() - written.keys():
            (FIXTURE / stale).unlink()
        for relative, content in written.items():
            (FIXTURE / relative).parent.mkdir(parents=True, exist_ok=True)
            (FIXTURE / relative).write_bytes(content)

    assert written == files_under(FIXTURE)


def capture_dir(directory: Path, capture_id: str) -> Path:
    return directory / "captures" / capture_id


def test_the_cutoff_capture_holds_both_ranges_and_the_state_at_the_stop(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2, depth=1)
    game.drawn()

    events, manifest, _ = record(game, tmp_path, Options(cutoff_captures=True))

    directory = capture_dir(tmp_path, "0-2-cutoff")
    capture = json.loads((directory / "manifest.json").read_text())
    assert [e["id"] for e in events if e["event"] == "capture"] == ["0-2-cutoff"]
    assert (directory / "complete").exists()
    assert (directory / "data.bin").read_bytes() == bytes(i % 251 for i in range(0x40))
    assert (directory / "heap0.bin").read_bytes() == bytes(i % 241 for i in range(0x200))
    assert (capture["scene"], capture["counter"], capture["platform"], capture["arch"]) == ("ORIG", 2, "xbox", "x86")
    assert capture["heap"]["depth"] == 1
    assert capture["bowl"]["words"][0] == 1
    assert manifest["captures"] == [
        {"id": "0-2-cutoff", "trigger": "cutoff", "label": None, "counter": 2, "scene": "ORIG"}
    ]


def test_cutoff_captures_follow_the_scene_list(tmp_path: Path) -> None:
    game = three_loads()

    _, manifest, _ = record(game, tmp_path, Options(cutoff_captures=frozenset({"TARG"})))

    assert [c["id"] for c in manifest["captures"]] == ["0-3-cutoff", "0-4-cutoff"]


def test_a_capture_over_the_budget_is_dropped_and_listed(tmp_path: Path) -> None:
    game = three_loads()

    events, manifest, _ = record(game, tmp_path, Options(cutoff_captures=True, capture_budget=1))

    assert [c["id"] for c in manifest["captures"]] == ["0-2-cutoff"]
    assert [(c["trigger"], c["scene"]) for c in manifest["captures_dropped"]] == [("cutoff", "TARG")] * 2
    assert sorted(path.name for path in (tmp_path / "captures").iterdir()) == ["0-2-cutoff"]
    assert names(events).count("capture") == 1


def test_a_capture_that_fails_midway_is_absent(tmp_path: Path) -> None:
    class FailingDump(MockTarget):
        def dump(self, address: int, length: int, path: Path) -> None:
            super().dump(address, length, path)
            raise TargetError("the emulator stopped answering")

    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.drawn()
    target = FailingDump(game.script)
    recorder = Recorder(target, game.profile, tmp_path, "run-1", Options(cutoff_captures=True))
    recorder.start("attach")
    target.run()
    recorder.finish()

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert (manifest["captures"], manifest["events_dropped"]) == ([], 1)
    assert not capture_dir(tmp_path, "0-2-cutoff").exists()


def test_a_manual_capture_marks_the_run_attended_and_repeats_get_their_own_ids(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    recorder, _ = run(game, tmp_path)

    ids = [recorder.capture("manual", "before the warp"), recorder.capture("manual", "after")]
    recorder.finish()

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert ids == ["0-2-manual", "0-2-manual-2"]
    assert (manifest["attended"], [c["label"] for c in manifest["captures"]]) == (True, ["before the warp", "after"])


def test_an_unattended_recording_has_no_captures_unless_asked(tmp_path: Path) -> None:
    _, manifest, _ = record(three_loads(), tmp_path)

    assert (manifest["captures"], manifest["attended"], (tmp_path / "captures").exists()) == ([], False, False)


def test_the_observation_level_records_the_capture_options(tmp_path: Path) -> None:
    _, manifest, _ = record(ScriptedGame(), tmp_path, Options(cutoff_captures=frozenset({"TARG"}), capture_budget=5))

    assert manifest["observation"] == {"heap_events": True, "cutoff_captures": ["TARG"], "capture_budget": 5}


def test_a_stop_the_guest_is_held_at_is_observed_when_asked(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_exit("ORIG", 2)
    target = game.build()
    target.run()
    recorder = Recorder(target, game.profile, tmp_path, "run-1", Options())
    recorder.start("attach")

    recorder.replay_current_stop()
    recorder.finish()

    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert [(e["event"], e.get("scene")) for e in events] == [("segment", None), ("scene_exit", "ORIG")]


def test_a_guest_held_where_no_point_is_armed_observes_nothing(tmp_path: Path) -> None:
    game = ScriptedGame()
    game.scene_init("ORIG", 2)
    game.idle(5, 10)
    target = game.build()
    target.run()
    recorder = Recorder(target, game.profile, tmp_path, "run-1", Options())
    recorder.start("attach")

    recorder.replay_current_stop()

    assert recorder.event_count == 1
