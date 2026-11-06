"""Requests: a route for the harness to drive, and the landing test, control or inject test at its target, read and
checked."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from bowlharness.contract.documents import read_document
from bowlharness.contract.generated import common_schema, request_schema
from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.recorder import Options

SCHEMA_VERSION = 1
INJECT_SCHEMA_VERSION = 2
RECORD = "record"
LANDING = "landing"
CONTROL = "control"
INJECT = "inject"
ASSET = "asset"
LIVE = "live"
LOOKUP = "lookup"
ADDRESS = "address"
FOOTPRINT = "footprint"
EXPLICIT = "explicit"
GUEST_FRAMES = "guest-frames"
WALL_SECONDS = "wall-seconds"
DEFAULT_MIN_MATCH = 0.9


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
class Window:
    """A length of time: ``value`` guest frames, or ``value`` wall-clock seconds."""

    unit: str
    value: float


@dataclass(frozen=True)
class Windows:
    """How long a test step is watched.

    Attributes:
        render: From the first stale write, or a control's draw.
        reset: From the first reset.
        write_timeout: From players done, the longest wait for the first stale write or for control.
    """

    render: Window
    reset: Window
    write_timeout: Window


@dataclass(frozen=True)
class Recipe:
    """The recorded load that places a landing.

    Attributes:
        recording: The recording's folder, relative to the recordings root, with forward slashes.
        segment: The segment that holds the load.
        load: The load's counter.
    """

    recording: str
    segment: int
    load: int


@dataclass(frozen=True)
class LandingTest:
    """A landing placed at a step.

    Attributes:
        step: The target step's index.
        recipe: The recorded load whose requests place it.
        op: The block's position in that load's request list.
        delta: The signed byte offset of ``S`` in the block.
        offset: Where the expected window starts, from ``S``.
        expected: The bytes the window must hold.
        min_match: The fraction of them that must match.
    """

    step: int
    recipe: Recipe
    op: int
    delta: int
    offset: int
    expected: bytes
    min_match: float = DEFAULT_MIN_MATCH


@dataclass(frozen=True)
class ControlTest:
    """A step watched as a landing's would be, with nothing placed."""

    step: int


@dataclass(frozen=True)
class Target:
    """Where an injection's ``S`` would be: the anchor its writes are laid against.

    Attributes:
        kind: ``asset``, ``live``, ``lookup`` or ``address``.
        id: The object's id; ``None`` for an address.
        offset: Signed bytes from the object; for an address, the address itself.
    """

    kind: str
    id: int | None
    offset: int


@dataclass(frozen=True)
class Injection:
    """Words written at a target.

    Attributes:
        target: Where ``S`` would be.
        words: The footprint's words to write, by their offsets from the anchor; ``None`` for all of them.
        values: Explicit bytes by offset from the anchor, in place of the footprint; ``None`` for the footprint.
    """

    target: Target
    words: tuple[int, ...] | None = None
    values: tuple[tuple[int, bytes], ...] | None = None

    @property
    def source(self) -> str:
        """``explicit`` when the bytes are the request's own, otherwise ``footprint``."""
        return FOOTPRINT if self.values is None else EXPLICIT


@dataclass(frozen=True)
class InjectTest:
    """Injections applied to the loads of a scene, starting at a step.

    Attributes:
        step: The target step's index, whose load is injected first.
        injections: What is written in each injected load.
        first_visit_only: Whether only the target step's load is injected, not the later loads of its scene.
    """

    step: int
    injections: tuple[Injection, ...]
    first_visit_only: bool = False


@dataclass(frozen=True)
class Request:
    """A request with every default filled in.

    Attributes:
        request_id: The request's durable identity.
        kind: ``record``, ``landing``, ``control`` or ``inject``.
        start: ``new-game`` to begin at the main menu's New Game, or ``booted`` when the disc boots into the first step.
        steps: The scenes to load, in order.
        options: What to observe.
        hold: How many polls a press is held for.
        release: How many polls it is released for.
        client: An opaque value the harness returns unread.
        test: The request's one test; ``None`` in a record.
        windows: The test's windows; ``None`` in a record.
    """

    request_id: str
    kind: str
    start: str
    steps: tuple[Step, ...]
    options: Options
    hold: int
    release: int
    client: Any = None
    test: LandingTest | ControlTest | InjectTest | None = None
    windows: Windows | None = None

    def to_json(self) -> dict[str, Any]:
        """The request as a manifest records it: the file's spelling, defaults included."""
        return {
            "schema_version": INJECT_SCHEMA_VERSION if self.kind == INJECT else SCHEMA_VERSION,
            "request_id": self.request_id,
            "kind": self.kind,
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
            **({"tests": [_test_json(self.test)]} if self.test else {}),
            **({"windows": _windows_json(self.windows)} if self.windows else {}),
            "observe": {
                "heap_events": _selection(self.options.heap_events),
                "cutoff_captures": _selection(self.options.cutoff_captures),
                "capture_budget": self.options.capture_budget,
            },
            "input": {"hold": self.hold, "release": self.release},
            "client": self.client,
        }


def _test_json(test: LandingTest | ControlTest | InjectTest) -> dict[str, Any]:
    if isinstance(test, ControlTest):
        return {"step": test.step}
    if isinstance(test, InjectTest):
        return {
            "step": test.step,
            "injections": [injection_json(injection) for injection in test.injections],
            "first_visit_only": test.first_visit_only,
        }
    recipe = test.recipe
    return {
        "step": test.step,
        "recipe": {"recording": recipe.recording, "segment": recipe.segment, "load": recipe.load},
        "op": test.op,
        "delta": test.delta,
        "expected": {"offset": test.offset, "bytes": test.expected.hex()},
        "min_match": test.min_match,
    }


def injection_json(injection: Injection) -> dict[str, Any]:
    """The injection as a request file spells it."""
    target = injection.target
    spelled = (
        {ADDRESS: target.offset}
        if target.kind == ADDRESS
        else {target.kind: {"id": f"0x{target.id:08X}", "offset": target.offset}}
    )
    return {
        "target": spelled,
        **({"words": list(injection.words)} if injection.words is not None else {}),
        **(
            {"values": [{"offset": offset, "hex": data.hex()} for offset, data in injection.values]}
            if injection.values is not None
            else {}
        ),
    }


def _windows_json(windows: Windows) -> dict[str, Any]:
    named = {"render": windows.render, "reset": windows.reset, "write_timeout": windows.write_timeout}
    return {name: {"unit": window.unit, "value": window.value} for name, window in named.items()}


def _selection(scenes: bool | frozenset[str]) -> str | list[str]:
    if isinstance(scenes, bool):
        return "all" if scenes else "none"
    return sorted(scenes)


def default_windows(profile: PlatformProfile) -> Windows:
    """The windows a request names none of: render 20 s and reset 15 s of guest frames, writes 120 wall seconds."""
    return Windows(
        render=Window(GUEST_FRAMES, 20 * profile.frame_rate),
        reset=Window(GUEST_FRAMES, 15 * profile.frame_rate),
        write_timeout=Window(WALL_SECONDS, 120),
    )


def read_request(path: Path, profile: PlatformProfile) -> tuple[Request, str]:
    """Reads and checks a request from a file.

    Returns:
        The request, and the SHA-256 of the file's bytes.

    Raises:
        ValueError: The file is not a valid request; the message names the field.
    """
    data = path.read_bytes()
    try:
        document = json.loads(data)
    except ValueError as error:
        raise ValueError(f"{path.name} is not valid JSON: {error}") from error
    return parse_request(document, profile), hashlib.sha256(data).hexdigest()


def parse_request(document: Any, profile: PlatformProfile) -> Request:
    """Checks a request document. Raises ``ValueError`` naming the field at fault.

    The document is read into the schema's types first; what follows checks what the types don't state.
    """
    request = read_document(request_schema.Request, document, "request")
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
    test, windows = None, None
    if not isinstance(request, request_schema.RecordRequest) and len(request.tests) != 1:
        raise ValueError("tests must hold exactly one test")
    if isinstance(request, request_schema.InjectRequest):
        test = _inject_test(request.tests[0], steps, profile)
        windows = _windows(request.windows or request_schema.Windows(), profile)
    elif isinstance(request, request_schema.LandingRequest | request_schema.ControlRequest):
        test = _test(request.tests[0], steps)
        windows = _windows(request.windows or request_schema.Windows(), profile)
    return Request(
        request.request_id,
        request.kind,
        request.start.from_,
        steps,
        options,
        _polls(profile.input.hold_polls if pad.hold is None else pad.hold, "input.hold"),
        _polls(profile.input.release_polls if pad.release is None else pad.release, "input.release"),
        request.client,
        test,
        windows,
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


def _test(
    test: request_schema.LandingTest | request_schema.ControlTest, steps: tuple[Step, ...]
) -> LandingTest | ControlTest:
    index, last = test.step, len(steps) - 1
    if index not in (last, last - 1):
        raise ValueError("tests[0].step must be the route's last step, or the one before its exit step")
    _check_exit(steps, index)
    if isinstance(test, request_schema.ControlTest):
        return ControlTest(index)
    return LandingTest(index, _recipe(test.recipe), test.op, test.delta, *_expected(test), _min_match(test))


def _check_exit(steps: tuple[Step, ...], index: int) -> None:
    if steps[index].cheats:
        raise ValueError(f"steps[{index}].cheats is not allowed: nothing may open the pause menu inside the windows")
    exit_index = index + 1
    if exit_index < len(steps):
        if steps[exit_index].cheats:
            raise ValueError(f"steps[{exit_index}].cheats is not allowed: the run ends at the exit step's scene init")
        if steps[exit_index].costumes != steps[index].costumes:
            raise ValueError(f"steps[{exit_index}].costumes must be the test step's, so leaving it changes no costume")


def _inject_test(test: request_schema.InjectTest, steps: tuple[Step, ...], profile: PlatformProfile) -> InjectTest:
    index = test.step
    if index >= len(steps):
        raise ValueError(f"tests[0].step must be the index of a step, below {len(steps)}")
    _check_exit(steps, index)
    first_visit_only = bool(test.first_visit_only)
    if first_visit_only and any(step.scene == steps[index].scene for step in steps[:index]):
        raise ValueError(
            f"tests[0].first_visit_only is not allowed: steps[{index}] is not the first load of {steps[index].scene}"
        )
    injections = tuple(_injection(item, f"tests[0].injections[{n}]", profile) for n, item in enumerate(test.injections))
    return InjectTest(index, injections, first_visit_only)


def _injection(injection: common_schema.Injection, name: str, profile: PlatformProfile) -> Injection:
    if injection.words is not None and injection.values is not None:
        raise ValueError(f"{name} has both words and values; give one")
    words = None
    if injection.words is not None:
        footprint = [offset for offset, _ in profile.bowl_storage.footprint]
        unknown = [word for word in injection.words if word not in footprint]
        if unknown:
            raise ValueError(f"{name}.words has {unknown[0]}, which is not one of the footprint's offsets {footprint}")
        words = tuple(injection.words)
    values = None
    if injection.values is not None:
        values = tuple((value.offset, _value_bytes(value, f"{name}.values")) for value in injection.values)
    return Injection(_target(injection.target), words, values)


def _value_bytes(value: common_schema.Value, name: str) -> bytes:
    try:
        data = bytes.fromhex(value.hex)
    except ValueError:
        data = b""
    if not data or value.hex != data.hex():
        raise ValueError(f"{name}.hex must be lower-case hex, two digits per byte")
    return data


def _target(target: Any) -> Target:
    if isinstance(target, common_schema.AddressTarget):
        return Target(ADDRESS, None, target.address)
    kind = next(kind for kind in (ASSET, LIVE, LOOKUP) if hasattr(target, kind))
    found = getattr(target, kind)
    return Target(kind, int(found.id, 16), found.offset)


def _recipe(recipe: request_schema.Recipe) -> Recipe:
    path = PurePosixPath(recipe.recording)
    foreign = any(character in recipe.recording for character in "\\:")
    if not recipe.recording or foreign or path.is_absolute() or ".." in path.parts:
        raise ValueError("tests[0].recipe.recording must be a folder under the recordings root, with forward slashes")
    if recipe.segment < 0 or recipe.load < 0:
        raise ValueError("tests[0].recipe.segment and load must be counts")
    return Recipe(recipe.recording, recipe.segment, recipe.load)


def _expected(test: request_schema.LandingTest) -> tuple[int, bytes]:
    try:
        window = bytes.fromhex(test.expected.bytes)
    except ValueError:
        window = b""
    if not window or test.expected.bytes != window.hex():
        raise ValueError("tests[0].expected.bytes must be lower-case hex, two digits per byte")
    return test.expected.offset, window


def _min_match(test: request_schema.LandingTest) -> float:
    found = DEFAULT_MIN_MATCH if test.min_match is None else test.min_match
    if not 0 <= found <= 1:
        raise ValueError("tests[0].min_match must be from 0 to 1")
    return found


def _windows(windows: request_schema.Windows, profile: PlatformProfile) -> Windows:
    defaults = default_windows(profile)
    found = {}
    for name in ("render", "reset", "write_timeout"):
        window = getattr(windows, name)
        if window is not None and window.value <= 0:
            raise ValueError(f"windows.{name}.value must be above 0")
        found[name] = getattr(defaults, name) if window is None else Window(window.unit, window.value)
    return Windows(**found)
