# Generated from schema/ by scripts/generate_contract.py. Do not edit; change the schema and run it again.

from dataclasses import dataclass
from typing import Any, Literal

from .common_schema import (
    HeapState,
    Hex,
    Injection,
    InputPolicy,
    Observe,
    Scene,
    Sha256,
    Top,
    Window,
)


@dataclass(frozen=True, kw_only=True)
class Moment:
    """
    A point in the run, in wall-clock time and in guest frames.
    """

    wall: str
    """
    UTC, as an ISO 8601 timestamp.
    """
    frame: int | None
    """
    The guest's frame counter, or null when the guest couldn't be read.
    """


type Outcome = Literal[
    "survived",
    "crash",
    "hang",
    "stalled",
    "no write",
    "no control",
    "layout mismatch",
    "not placed",
    "not injected",
    "scene change",
    "costume mismatch",
    "menu unreachable",
    "unsupported",
    "interrupted",
]
"""
How the run ended, from what the harness observed.
"""


@dataclass(frozen=True, kw_only=True)
class CounterBasis:
    """
    The boot scene and the load counter it has, which turn a counter into a load number.
    """

    boot_scene: Scene
    boot_counter: int


@dataclass(frozen=True, kw_only=True)
class Emulator:
    """
    The emulator and its configuration.
    """

    name: str
    version: str | None
    commit: str | None
    date: str | None
    executable_sha256: Sha256 | None
    """
    Null when the harness attached to an emulator it didn't start.
    """
    config_sha256: Sha256
    controller: str | None
    """
    The controller bound to port 1.
    """


@dataclass(frozen=True, kw_only=True)
class Disc:
    """
    The disc image.
    """

    image: str | None
    image_sha256: Sha256 | None


@dataclass(frozen=True, kw_only=True)
class Storage:
    """
    The storage image.
    """

    image: str | None
    bytes: int | None


@dataclass(frozen=True, kw_only=True)
class WindowRecord:
    """
    A window as configured, and the frames and seconds it took; both null when it never opened.
    """

    configured: Window
    frames: int | None
    seconds: float | None


@dataclass(frozen=True, kw_only=True)
class PlacementTool:
    """
    The published copy of bowlbuster that placed the landings.
    """

    path: str
    """
    Where the pinned copy is.
    """
    build: str
    """
    What its --version printed.
    """
    sha256: Sha256
    """
    The hash of its executable.
    """


@dataclass(frozen=True, kw_only=True)
class StepRecord:
    """
    How a step of the route went.
    """

    index: int
    scene: Scene
    status: Literal["reached", "failed", "not reached"]
    reason: str | None
    """
    Why a failed step failed.
    """
    signal: str | None
    """
    What said a reached step's player was ready.
    """
    frame: int | None
    """
    The frame the step ended at; null when it wasn't reached.
    """
    presses: int
    """
    How many presses the harness gave during it.
    """


@dataclass(frozen=True, kw_only=True)
class Load:
    """
    A load the run saw.
    """

    recording: str
    segment: int
    counter: int
    scene: Scene
    costumes: dict[str, str | None]
    """
    The tag of the player archive each character wore, by character; null for none.
    """


@dataclass(frozen=True, kw_only=True)
class InjectionOutcome:
    """
    One injection in one load.
    """

    index: int
    """
    The injection's position in the test's injections.
    """
    source: Literal["footprint", "explicit"]
    """
    footprint: the profile's words, or the picked ones. explicit: the request's own bytes.
    """
    timing: Literal["after-player-init", "at-first-draw"]
    """
    after-player-init: written at players done. at-first-draw: written at the load's first drawn frame.
    """
    anchor: int | None
    """
    Where the target resolved to; null when the load never got that far.
    """
    seqs: list[int]
    """
    The seq of each of its write events, in the write ledger.
    """


@dataclass(frozen=True, kw_only=True)
class StaleWrite:
    """
    A stale write: the pointer the game wrote through, and when.
    """

    s: int
    frame: int


@dataclass(frozen=True, kw_only=True)
class Stage:
    """
    A stage of the target load's timeline.
    """

    stage: Literal["loading", "held", "in control", "render", "reset", "exit", "paused"]
    from_: int
    """
    The frame it began at.
    """
    to: int | None
    """
    The frame it ended at; null when the run ended inside it.
    """
    status: Literal["complete", "cut", "failed"]
    """
    complete; cut when the run ended inside it; failed when the harness couldn't finish it.
    """
    reason: str | None
    """
    Why a failed stage failed.
    """


@dataclass(frozen=True, kw_only=True)
class Crash:
    """
    A bugcheck. Its registers and stack words are in memory.
    """

    kind: Literal["KeBugCheck", "KeBugCheckEx"]
    code: int
    params: list[int]
    arch: str
    return_addresses: list[int]
    instruction: int | None
    """
    The faulting instruction of an unhandled exception.
    """
    access: Literal["read", "write"] | None
    """
    An access violation's kind.
    """
    accessed: int | None
    """
    The address an access violation accessed.
    """
    scene: Scene | None
    counter: int | None
    capture: str | None
    """
    The crash's capture, if it was taken.
    """
    stage: str | None
    """
    The stage it happened in; null in a record.
    """


@dataclass(frozen=True, kw_only=True)
class EventReference:
    """
    An event of a recording.
    """

    seq: int
    event: str


@dataclass(frozen=True, kw_only=True)
class Reset:
    """
    A scene reset.
    """

    frame: int
    counter: int | None
    cause: Literal["game"]
    """
    Who caused it.
    """


@dataclass(frozen=True, kw_only=True)
class Integrity:
    """
    What would make the run invalid. A run is valid when it raised no flag.
    """

    flags: list[
        Literal[
            "stage after crash",
            "not in play at write",
            "over 240 s",
            "over 3 resets",
            "warp retried",
            "events dropped",
            "control never given",
            "match below 0.9",
        ]
    ]


@dataclass(frozen=True, kw_only=True)
class Effects:
    """
    What the run changed in the game's state. Not observed until the observed fields are confirmed.
    """

    observed: bool
    """
    Whether the harness looked.
    """
    reason: str | None
    """
    Why it didn't.
    """


@dataclass(frozen=True, kw_only=True)
class Write:
    """
    A write the harness made. The bytes it replaced are in memory, by the row's seq.
    """

    recording: str
    seq: int
    """
    The seq of its write event.
    """
    class_: Literal["bowl-storage", "inject"]
    target: str
    """
    What was written: sphere, flag or scale; for an injection, its target and the offset written, such as asset 0x1A2B3C4D+0x38.
    """
    address: int
    new: Hex


@dataclass(frozen=True, kw_only=True)
class Press:
    """
    A press, as the recording's input ledger holds it.
    """

    recording: str
    button: str
    mask: int
    source: Literal["harness", "manual", "person"]
    step: int | None
    game_mode: int
    play_state: int
    control_off: int
    sent_poll: int
    sent_frame: int
    polls: int
    taken_frame: int | None
    cancelled: bool


@dataclass(frozen=True, kw_only=True)
class Capture:
    """
    A capture the run took.
    """

    recording: str
    id: str
    trigger: str
    label: str | None
    counter: int
    scene: Scene | None


@dataclass(frozen=True, kw_only=True)
class DroppedCapture:
    """
    A capture the budget refused.
    """

    recording: str
    trigger: str
    label: str | None
    scene: Scene | None


@dataclass(frozen=True, kw_only=True)
class OldBytes:
    """
    The bytes a write replaced.
    """

    recording: str
    seq: int
    bytes: Hex


@dataclass(frozen=True, kw_only=True)
class CrashMemory:
    """
    A crash's registers, by name, and its stack words from the stack pointer.
    """

    registers: dict[str, int]
    stack: list[int]


@dataclass(frozen=True, kw_only=True)
class Windows:
    """
    Each window as configured and as taken.
    """

    render: WindowRecord
    reset: WindowRecord
    write_timeout: WindowRecord


@dataclass(frozen=True, kw_only=True)
class Placement:
    """
    Where the landing was placed, and whether the game wrote where it was placed.
    """

    s: int | None
    """
    The sphere written; null when place placed nothing.
    """
    heap: HeapState
    """
    The live heap handed to place.
    """
    match: float | None
    """
    The fraction of the expected window that matched; null when it wasn't checked.
    """
    first_write: StaleWrite | None
    """
    The game's first stale write; null when none came.
    """
    predicted_top: Top | None
    """
    The cursor and depth place --top predicted; null when the recipe has no cutoff.
    """
    live_top: Top | None
    """
    The live cursor and depth at the first stale write; null when none came.
    """


@dataclass(frozen=True, kw_only=True)
class InjectedLoad:
    """
    What the test did in one load.
    """

    counter: int
    """
    The load's counter.
    """
    scene: Scene
    injections: list[InjectionOutcome]


@dataclass(frozen=True, kw_only=True)
class Hang:
    """
    A guest that made no progress.
    """

    stalled: float
    """
    Seconds without progress.
    """
    last_frame: int
    last_event: EventReference | None
    scene: Scene | None
    counter: int | None
    capture: str | None


@dataclass(frozen=True, kw_only=True)
class Memory:
    """
    Every game byte the result holds. The rest of a result can be shared; this block is never committed.
    """

    live_window: Hex | None
    """
    The window at S+expected.offset as players done found it; null when it wasn't read.
    """
    old_bytes: list[OldBytes]
    """
    The bytes each write replaced.
    """
    crash: CrashMemory | None
    """
    The crash's registers and stack words; null without a crash.
    """


@dataclass(frozen=True, kw_only=True)
class Manifest:
    """
    Everything a reproduction of the run must restore.
    """

    harness: str
    """
    The harness's version.
    """
    platform: str
    """
    The platform, as the profile names it.
    """
    profile: Sha256
    """
    The hash of the platform profile.
    """
    counter_basis: CounterBasis
    emulator: Emulator
    disc: Disc
    storage: Storage
    gdb: str
    """
    The version of the gdb that hosted the harness.
    """
    host: str
    """
    The host's operating system.
    """
    boot_path: Literal["boot", "attached"]
    """
    How the run's first recording began.
    """
    request_sha256: Sha256
    """
    The hash of the request file's bytes.
    """
    setup: Literal["new-game", "booted"]
    """
    How the game was set up: the request's start.
    """
    observation: Observe
    input: InputPolicy
    windows: Windows | None
    """
    The test step's windows; null in a record.
    """
    placement_tool: PlacementTool | None
    """
    The placement tool the session pinned; null when it had none.
    """
    recordings: list[str]
    """
    The run ids of the recordings the run made, in order: a reboot ends one and opens the next.
    """
    steps: list[StepRecord]
    """
    How each step of the route went.
    """
    loads: list[Load]
    """
    Every load the run saw.
    """
    events_dropped: int
    """
    How many events the recordings lost.
    """


@dataclass(frozen=True, kw_only=True)
class InjectionRecord:
    """
    An inject test as requested, and the loads it injected.
    """

    injections: list[Injection]
    """
    The test's injections as requested.
    """
    first_visit_only: bool
    loads: list[InjectedLoad]
    """
    The loads injected, in order: the target step's, then each later load of its scene.
    """


@dataclass(frozen=True, kw_only=True)
class Result:
    """
    What one attempt at a request did, written once when the run ends and never changed. A field that doesn't apply is null, or sits in a group that says why.
    """

    schema_version: Literal[1, 2]
    """
    2 since the inject kind; 1 results are still read.
    """
    run: str
    """
    The run's id: the request's id and the attempt, <request>-a<attempt>.
    """
    request: str
    """
    The id of the request the run attempted.
    """
    attempt: int
    """
    Which attempt at the request this is, from 1.
    """
    kind: Literal["record", "landing", "control", "inject"]
    """
    The request's kind.
    """
    instance: str | None
    """
    The emulator instance that ran it, or null for a run no queue claimed.
    """
    started: Moment
    ended: Moment
    outcome: Outcome
    cause: str | None
    """
    Why an interrupted run was cut short (stopped, lost, a harness fault), or why a target was not injected; null for any other outcome.
    """
    manifest: Manifest
    placement: Placement | None
    """
    The landing's placement; null in a record or a control.
    """
    stages: list[Stage]
    """
    The stages the target load went through, in order, each time it entered one; empty in a record.
    """
    crash: Crash | None
    """
    The crash record when the outcome is crash, else null.
    """
    hang: Hang | None
    """
    The hang record when the outcome is hang, else null.
    """
    resets: list[Reset]
    """
    Every scene reset of the target load, in order.
    """
    integrity: Integrity
    effects: Effects
    write_ledger: list[Write]
    """
    Every write the harness made to guest memory, in order.
    """
    input_ledger: list[Press]
    """
    Every press, in the order they were given.
    """
    attended: bool
    """
    Whether a person took part in the run.
    """
    captures: list[Capture]
    """
    The captures the run took.
    """
    captures_dropped: list[DroppedCapture]
    """
    The captures the budget refused.
    """
    client: Any
    """
    The request's client value, as received.
    """
    memory: Memory
    injection: InjectionRecord | None = None
    """
    The inject test and what it did to each load; null in any other kind. Absent in a version 1 result.
    """
