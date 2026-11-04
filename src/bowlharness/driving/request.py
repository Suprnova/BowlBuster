"""The record request: a route for the harness to drive, read from a file and checked."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bowlharness.contract.documents import read_document
from bowlharness.contract.generated import common_schema, request_schema
from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.recorder import Options

SCHEMA_VERSION = 1
KIND = "record"
UNSUPPORTED_KINDS = ("landing", "control")


@dataclass(frozen=True)
class Menu:
    """A task in the pause menu, numbered from 1 as the menu numbers them."""

    world: int
    slot: int


@dataclass(frozen=True)
class Step:
    """A scene the route loads.

    Attributes:
        scene: The scene's four-character tag.
        menu: Where the pause menu warps to it; ``None`` for the first step, which the start loads.
        costumes: The archive tags its load wears, at most one per character.
        cheats: The cheats entered while it is in play, by the names the platform profile gives them.
    """

    scene: str
    menu: Menu | None = None
    costumes: tuple[str, ...] = ()
    cheats: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecordRequest:
    """A route to drive and record, with every default filled in.

    Attributes:
        request_id: The request's durable identity.
        start: ``new-game`` to begin at the main menu's New Game, or ``booted`` when the disc boots into the first step.
        steps: The scenes to load, in order.
        options: What to observe.
        hold: How many polls a press is held for.
        release: How many polls it is released for.
        client: An opaque value the harness returns unread.
    """

    request_id: str
    start: str
    steps: tuple[Step, ...]
    options: Options
    hold: int
    release: int
    client: Any = None

    def to_json(self) -> dict[str, Any]:
        """The request as a manifest records it: the file's spelling, defaults included."""
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": self.request_id,
            "kind": KIND,
            "start": {"from": self.start},
            "steps": [
                {
                    "scene": step.scene,
                    **({"menu": {"world": step.menu.world, "slot": step.menu.slot}} if step.menu else {}),
                    "costumes": list(step.costumes),
                    "cheats": list(step.cheats),
                }
                for step in self.steps
            ],
            "observe": {
                "heap_events": _selection(self.options.heap_events),
                "cutoff_captures": _selection(self.options.cutoff_captures),
                "capture_budget": self.options.capture_budget,
            },
            "input": {"hold": self.hold, "release": self.release},
            "client": self.client,
        }


def _selection(scenes: bool | frozenset[str]) -> str | list[str]:
    if isinstance(scenes, bool):
        return "all" if scenes else "none"
    return sorted(scenes)


def read_request(path: Path, profile: PlatformProfile) -> tuple[RecordRequest, str]:
    """Reads and checks a record request.

    Returns:
        The request, and the SHA-256 of the file's bytes.

    Raises:
        ValueError: The file is not a valid record request; the message names the field.
    """
    data = path.read_bytes()
    try:
        document = json.loads(data)
    except ValueError as error:
        raise ValueError(f"{path.name} is not valid JSON: {error}") from error
    return parse_request(document, profile), hashlib.sha256(data).hexdigest()


def parse_request(document: Any, profile: PlatformProfile) -> RecordRequest:
    """Checks a request document. Raises ``ValueError`` naming the field at fault.

    The document is read into the schema's types first; what follows checks what the types don't state.
    """
    if isinstance(document, dict) and (kind := document.get("kind")) in UNSUPPORTED_KINDS:
        raise ValueError(f"kind {kind!r} is not supported, only {KIND!r}")
    request = read_document(request_schema.RecordRequest, document, "request")
    if not request.request_id:
        raise ValueError("request_id must be a non-empty string")
    if not request.steps:
        raise ValueError("steps must be a non-empty list")
    steps = tuple(_step(step, index, profile) for index, step in enumerate(request.steps))
    observe = request.observe or common_schema.Observe()
    budget = observe.capture_budget
    if budget is not None and budget < 0:
        raise ValueError("observe.capture_budget must be null or a count")
    options = Options(
        heap_events=_scenes(observe.heap_events or "all", "observe.heap_events"),
        cutoff_captures=_scenes(observe.cutoff_captures or "none", "observe.cutoff_captures"),
        capture_budget=budget,
    )
    pad = request.input or common_schema.InputPolicy()
    return RecordRequest(
        request.request_id,
        request.start.from_,
        steps,
        options,
        _polls(profile.input.hold_polls if pad.hold is None else pad.hold, "input.hold"),
        _polls(profile.input.release_polls if pad.release is None else pad.release, "input.release"),
        request.client,
    )


def _polls(value: int, name: str) -> int:
    if value < 1:
        raise ValueError(f"{name} must be at least 1 poll")
    return value


def _tag(value: str, name: str) -> str:
    if len(value) != 4:
        raise ValueError(f"{name} must be a four-character tag")
    return value.upper()


def _scenes(value: common_schema.SceneSelection, name: str) -> bool | frozenset[str]:
    if isinstance(value, list):
        return frozenset(_tag(item, name) for item in value)
    return value == "all"


def _step(step: request_schema.Step, index: int, profile: PlatformProfile) -> Step:
    name = f"steps[{index}]"
    if step.menu is not None and index == 0:
        raise ValueError(f"{name}.menu is not allowed: the start loads the first step")
    if step.menu is None and index > 0:
        raise ValueError(f"{name}.menu is required: the pause menu warps to every step after the first")
    menu = None if step.menu is None else _menu(step.menu, f"{name}.menu")
    costumes = tuple(_tag(tag, f"{name}.costumes") for tag in step.costumes or ())
    prefixes = [tag[:3] for tag in costumes if tag[:3] in profile.costumes.tag_prefixes]
    if len(set(prefixes)) != len(prefixes):
        raise ValueError(f"{name}.costumes has more than one costume for a character")
    cheats = tuple(_cheat(cheat, f"{name}.cheats", profile) for cheat in step.cheats or ())
    return Step(_tag(step.scene, f"{name}.scene"), menu, costumes, cheats)


def _menu(menu: request_schema.Menu, name: str) -> Menu:
    for label, number in (("world", menu.world), ("slot", menu.slot)):
        if number < 1:
            raise ValueError(f"{name}.{label} must be a number from 1")
    return Menu(menu.world, menu.slot)


def _cheat(cheat: str, name: str, profile: PlatformProfile) -> str:
    if profile.navigation.cheats.bit(cheat) is None:
        raise ValueError(f"{name} has an unknown cheat {cheat!r}")
    return cheat
