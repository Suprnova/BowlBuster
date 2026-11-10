# Generated from schema/ by scripts/generate_contract.py. Do not edit; change the schema and run it again.

from dataclasses import dataclass
from typing import Any, Literal

from .common_schema import Injection, InputPolicy, Observe, Scene, Window

type RequestId = str
"""
The request's durable identity.
"""


@dataclass(frozen=True, kw_only=True)
class BootStart:
    """
    A start from the boot, with nothing loaded.
    """

    from_: Literal["new-game", "booted"]
    """
    new-game: the main menu's New Game, then the first step's load. booted: the disc boots straight into the first step's scene.
    """


@dataclass(frozen=True, kw_only=True)
class SaveStart:
    """
    A start from a save in the harness's save library, loaded through the main menu's Load Game. Since schema_version 3.
    """

    from_: Literal["save"]
    save: str
    """
    The save's name in the library. The first step is the scene it loads into.
    """


@dataclass(frozen=True, kw_only=True)
class Menu:
    """
    Where the pause menu warps to a step: its world and task slot, numbered from 1 as the menu numbers them.
    """

    world: int
    """
    The world.
    """
    slot: int
    """
    The task slot.
    """


type CheatName = Literal["all-tasks", "all-moves", "all-moves-upgraded", "all-health", "double-manliness"]
"""
A cheat a step enters, by name. The platform profile gives each name its bit in the cheat mask.
"""


@dataclass(frozen=True, kw_only=True)
class Step:
    """
    A scene the route loads.
    """

    scene: Scene
    menu: Menu | None = None
    """
    Where the pause menu warps to the step. Every step but the first has one; the start loads the first.
    """
    costumes: list[Scene] | None = None
    """
    The tags of the player archives the step's load wears, at most one per character; none when left out.
    """
    cheats: list[CheatName] | None = None
    """
    The cheats entered while the step's level is in play.
    """


type Steps = list[Step]
"""
The scenes to load, in order.
"""


@dataclass(frozen=True, kw_only=True)
class Windows:
    """
    How long a test step is watched. Each left out takes the harness's default.
    """

    render: Window | None = None
    """
    From the first stale write, or a control's draw. Default: 20 s of guest frames.
    """
    reset: Window | None = None
    """
    From the first reset. Default: 15 s of guest frames.
    """
    write_timeout: Window | None = None
    """
    From players done, the longest wait for the first stale write or for control. Default: 120 wall seconds.
    """


@dataclass(frozen=True, kw_only=True)
class Recipe:
    """
    The recorded load whose requests place the landing, as bowlbuster place addresses it.
    """

    recording: str
    """
    The recording's folder, relative to the harness's recordings root, with forward slashes.
    """
    segment: int
    """
    The segment that holds the load.
    """
    load: int
    """
    The load's counter.
    """


@dataclass(frozen=True, kw_only=True)
class Expected:
    """
    The window checked at players done before anything is written.
    """

    offset: int
    """
    Where the window starts, counted from S.
    """
    bytes: str
    """
    The bytes the window holds in the recipe's cutoff capture. Their count is the window's length.
    """


@dataclass(frozen=True, kw_only=True)
class LandingTest:
    """
    A landing placed at one step of the route.
    """

    step: int
    """
    The index of the target step.
    """
    recipe: Recipe
    op: int
    """
    The block's position in the recipe load's request list.
    """
    delta: int
    """
    The signed byte offset of S in the block.
    """
    expected: Expected
    min_match: float | None = None
    """
    The fraction of the expected window that must match. Default: 0.9.
    """


@dataclass(frozen=True, kw_only=True)
class ControlTest:
    """
    A step watched as a landing test's would be, with nothing placed.
    """

    step: int
    """
    The index of the target step.
    """


@dataclass(frozen=True, kw_only=True)
class InjectTest:
    """
    Injections applied to the loads of a scene, starting at one step of the route.
    """

    step: int
    """
    The index of the target step, whose load is injected first.
    """
    injections: list[Injection]
    first_visit_only: bool | None = None
    """
    Inject the target step's load only, not the later loads of its scene. Default: false.
    """


type Start = BootStart | SaveStart
"""
How the run reaches its first step.
"""


@dataclass(frozen=True, kw_only=True)
class RecordRequest:
    """
    A route to drive and record, load by load.
    """

    schema_version: Literal[1, 2, 3]
    request_id: RequestId
    kind: Literal["record"]
    start: Start
    steps: Steps
    observe: Observe | None = None
    input: InputPolicy | None = None
    client: Any | None = None
    """
    An opaque value the harness returns unread.
    """


@dataclass(frozen=True, kw_only=True)
class LandingRequest:
    """
    A route to a target step, a landing placed there, and an exit step after it.
    """

    schema_version: Literal[1, 2, 3]
    request_id: RequestId
    kind: Literal["landing"]
    start: Start
    steps: Steps
    tests: list[LandingTest]
    """
    The one test the request runs.
    """
    windows: Windows | None = None
    observe: Observe | None = None
    input: InputPolicy | None = None
    client: Any | None = None
    """
    An opaque value the harness returns unread.
    """


@dataclass(frozen=True, kw_only=True)
class ControlRequest:
    """
    A route to a target step, watched with nothing placed, and an exit step after it.
    """

    schema_version: Literal[1, 2, 3]
    request_id: RequestId
    kind: Literal["control"]
    start: Start
    steps: Steps
    tests: list[ControlTest]
    """
    The one test the request runs.
    """
    windows: Windows | None = None
    observe: Observe | None = None
    input: InputPolicy | None = None
    client: Any | None = None
    """
    An opaque value the harness returns unread.
    """


@dataclass(frozen=True, kw_only=True)
class InjectRequest:
    """
    A route to a target step, injections written there, and an exit step after it.
    """

    schema_version: Literal[2, 3]
    request_id: RequestId
    kind: Literal["inject"]
    start: Start
    steps: Steps
    tests: list[InjectTest]
    """
    The one test the request runs.
    """
    windows: Windows | None = None
    observe: Observe | None = None
    input: InputPolicy | None = None
    client: Any | None = None
    """
    An opaque value the harness returns unread.
    """


type Request = RecordRequest | LandingRequest | ControlRequest | InjectRequest
"""
A request for the harness to run: a route to record, a landing test, a control, or an inject test.
"""
