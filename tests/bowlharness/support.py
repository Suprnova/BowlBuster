import json
from pathlib import Path

from scripted import ScriptedGame

from bowlharness.backends.mock import MockTarget
from bowlharness.recording.recorder import Options, Recorder


def run(game: ScriptedGame, directory: Path, options: Options | None = None) -> tuple[Recorder, MockTarget]:
    target = game.build()
    recorder = Recorder(target, game.profile, directory, "run-1", options or Options())
    recorder.start("attach")
    target.run()
    return recorder, target


def record(game: ScriptedGame, directory: Path, options: Options | None = None) -> tuple[list[dict], dict, MockTarget]:
    recorder, target = run(game, directory, options)
    recorder.finish()
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    return events, json.loads((directory / "manifest.json").read_text()), target


def names(events: list[dict]) -> list[str]:
    return [event["event"] for event in events]


def three_loads() -> ScriptedGame:
    game = ScriptedGame()
    game.scene_init("ORIG", 2, extras={1: 1, 4: 1}, last_block=(0x5C0100, 0x40))
    game.alloc(0, 0x40, 0x10, 0x5C0140)
    game.layer_alloc(0x3000, 0x5C2000, "TARG", layers=4, index=1)
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
