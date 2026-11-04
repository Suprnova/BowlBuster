import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from scripted import COMPACT, ScriptedGame

from bowlharness.backends.mock import MockTarget
from bowlharness.driving.placer import Placer
from bowlharness.driving.request import Request, parse_request
from bowlharness.profiles import XBOX_NTSC_U
from bowlharness.recording.recorder import Options, Recorder
from bowlharness.session.driven import DrivenSession


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


DIGEST = "ab" * 32
ENVIRONMENT = {
    "emulator": {"name": "xemu", "version": "0.8.0", "config_sha256": "cd" * 32, "controller": "pad"},
    "disc": {"image": "disc.iso", "image_sha256": "ef" * 32},
    "storage": {"image": "hdd.qcow2", "bytes": 1024},
    "gdb": "16.3",
    "host": "Windows-11",
}
PAUSE_MENU = XBOX_NTSC_U.navigation.modes.pause_menu
FAST = replace(
    COMPACT,
    navigation=replace(COMPACT.navigation, ready_seconds=0.2, action_polls=15),
    scene_classes=replace(COMPACT.scene_classes, stall_frames=20),
)


def polls(game: ScriptedGame, count: int, **kwargs: int) -> None:
    for _ in range(count):
        game.pad_poll(**kwargs)


def level(game: ScriptedGame, scene: str, counter: int) -> None:
    """A scene loading and settling into play, with a few frames of play to spare."""
    game.scene_init(scene, counter)
    game.players_done()
    polls(game, 11)


def warp(game: ScriptedGame, presses: list[tuple[str, tuple[int, int]]], scene: str, counter: int, old: str) -> None:
    """Start, the cursor presses, A three times, and the load of ``scene``."""
    game.await_press("start", after=PAUSE_MENU)
    for button, cursor in presses:
        game.await_press(button, cursor=cursor, mode=PAUSE_MENU)
    for _ in range(3):
        game.await_press("a", mode=PAUSE_MENU, after=PAUSE_MENU)
    game.scene_exit(old, counter - 1)
    level(game, scene, counter)


def route(*steps: str | tuple[str, int, int], start: str = "booted") -> Request:
    """A record request through ``steps``: a scene, or a scene with its menu world and slot (numbered from 1)."""
    parsed = []
    for index, step in enumerate(steps):
        scene, *menu = (step,) if isinstance(step, str) else step
        entry: dict[str, Any] = {"scene": scene}
        if index:
            world, slot = menu or (index + 1, 1)
            entry["menu"] = {"world": world, "slot": slot}
        parsed.append(entry)
    return request(parsed, start)


def request(steps: list[dict[str, Any]], start: str = "booted") -> Request:
    """A record request through steps written as the request file writes them."""
    document = {
        "schema_version": 1,
        "request_id": "route-1",
        "kind": "record",
        "start": {"from": start},
        "steps": steps,
    }
    return parse_request(document, XBOX_NTSC_U)


def drive(
    game: ScriptedGame, directory: Path, request: Request, placer: Placer | None = None
) -> tuple[DrivenSession, dict[str, Any]]:
    """Drives the scripted game along the request and returns the session and the recording's manifest.

    A landing's recipes are under ``directory / "recordings"``.
    """
    target = MockTarget(game.script, {**game.kernel_image(), game.profile.globals.frame: bytes(4)})
    session = DrivenSession(
        target,
        game.profile,
        directory / "out",
        request,
        DIGEST,
        run_stem="s",
        environment=ENVIRONMENT,
        harness="0.1.0+test",
        placer=placer,
        recordings=directory / "recordings",
    )
    session.run()
    return session, json.loads((directory / "out" / "s-1" / "manifest.json").read_text())


def driven_events(directory: Path) -> list[dict]:
    return [json.loads(line) for line in (directory / "out" / "s-1" / "events.jsonl").read_text().splitlines()]
