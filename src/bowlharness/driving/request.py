"""The record request: a route for the harness to drive, read from a file and checked."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.recorder import Options

SCHEMA_VERSION = 1
KIND = "record"
STARTS = ("new-game", "booted")
_FIELDS = {"schema_version", "request_id", "kind", "start", "steps", "observe", "input", "client"}
_CHEAT = re.compile(r"[XY]( [XY]){7}")


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
        cheats: The cheat codes entered while it is in play, as the X and Y presses separated by spaces.
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
    """Checks a request document. Raises ``ValueError`` naming the field at fault."""
    fields = _object(document, "request", _FIELDS)
    if fields.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    if fields.get("kind") != KIND:
        raise ValueError(f"kind {fields.get('kind')!r} is not supported, only {KIND!r}")
    if not isinstance(request_id := fields.get("request_id"), str) or not request_id:
        raise ValueError("request_id must be a non-empty string")
    start = _object(fields.get("start"), "start", {"from"}).get("from")
    if start not in STARTS:
        raise ValueError(f"start.from must be one of {', '.join(STARTS)}")
    raw_steps = fields.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("steps must be a non-empty list")
    steps = tuple(_step(raw, index, profile) for index, raw in enumerate(raw_steps))
    observe = _object(fields.get("observe", {}), "observe", {"heap_events", "cutoff_captures", "capture_budget"})
    budget = observe.get("capture_budget")
    if budget is not None and (not isinstance(budget, int) or isinstance(budget, bool) or budget < 0):
        raise ValueError("observe.capture_budget must be null or a count")
    options = Options(
        heap_events=_scenes(observe.get("heap_events", "all"), "observe.heap_events"),
        cutoff_captures=_scenes(observe.get("cutoff_captures", "none"), "observe.cutoff_captures"),
        capture_budget=budget,
    )
    pad = _object(fields.get("input", {}), "input", {"hold", "release"})
    return RecordRequest(
        request_id,
        start,
        steps,
        options,
        _polls(pad.get("hold", profile.input.hold_polls), "input.hold"),
        _polls(pad.get("release", profile.input.release_polls), "input.release"),
        fields.get("client"),
    )


def _object(value: Any, name: str, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    if unknown := sorted(set(value) - allowed):
        raise ValueError(f"{name} has an unknown field {unknown[0]!r}")
    return value


def _polls(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be at least 1 poll")
    return value


def _tag(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 4:
        raise ValueError(f"{name} must be a four-character tag")
    return value.upper()


def _scenes(value: Any, name: str) -> bool | frozenset[str]:
    match value:
        case "all":
            return True
        case "none":
            return False
        case list():
            return frozenset(_tag(item, name) for item in value)
    raise ValueError(f'{name} must be "all", "none" or a list of scenes')


def _step(raw: Any, index: int, profile: PlatformProfile) -> Step:
    name = f"steps[{index}]"
    fields = _object(raw, name, {"scene", "menu", "costumes", "cheats"})
    menu = None
    if "menu" in fields:
        if index == 0:
            raise ValueError(f"{name}.menu is not allowed: the start loads the first step")
        menu = _menu(fields["menu"], f"{name}.menu")
    elif index > 0:
        raise ValueError(f"{name}.menu is required: the pause menu warps to every step after the first")
    costumes = tuple(_tag(tag, f"{name}.costumes") for tag in _list(fields.get("costumes", []), f"{name}.costumes"))
    prefixes = [tag[:3] for tag in costumes if tag[:3] in profile.costumes.tag_prefixes]
    if len(set(prefixes)) != len(prefixes):
        raise ValueError(f"{name}.costumes has more than one costume for a character")
    cheats = tuple(_cheat(code, f"{name}.cheats") for code in _list(fields.get("cheats", []), f"{name}.cheats"))
    return Step(_tag(fields.get("scene"), f"{name}.scene"), menu, costumes, cheats)


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _menu(raw: Any, name: str) -> Menu:
    fields = _object(raw, name, {"world", "slot"})
    world, slot = fields.get("world"), fields.get("slot")
    for label, number in (("world", world), ("slot", slot)):
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise ValueError(f"{name}.{label} must be a number from 1")
    return Menu(world, slot)


def _cheat(code: Any, name: str) -> str:
    if not isinstance(code, str) or not _CHEAT.fullmatch(code):
        raise ValueError(f"{name} must be eight X and Y presses separated by spaces")
    return code
