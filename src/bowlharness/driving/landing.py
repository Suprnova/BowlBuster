"""A landing test at its step: placed at the scene init, checked and written at players done, confirmed at the first
stale write."""

import json
import struct
from collections.abc import Callable
from pathlib import Path
from typing import Any

from bowlharness.contract.documents import read_document
from bowlharness.contract.generated import common_schema
from bowlharness.contract.generated import result_schema as schema
from bowlharness.driving.placer import NotPlaced, Placer
from bowlharness.driving.request import LandingTest
from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.observe import heap0_state
from bowlharness.recording.recorder import Recorder
from bowlharness.target import Target

BOWL_STORAGE = "bowl-storage"
NOT_PLACED = "not placed"
LAYOUT_MISMATCH = "layout mismatch"
INTERRUPTED = "interrupted"


class Landing:
    """Places one landing test and writes its stale pointer, following the recorder's events at the test step.

    1. At the target's scene init, the heap that event logged goes to the placer. A load it can't place ends the run
       ``not placed``.
    2. At players done, the window at ``S`` plus the expected offset is compared with the expected bytes. Below the
       test's match fraction the run ends ``layout mismatch`` with nothing written; otherwise the sphere, the flag and,
       when it is at or below the profile's threshold, the scale are written, each through :meth:`Recorder.write`.
    3. At the first stale write, the pointer the game wrote through is compared with the placed one, and the live
       heap's cursor and depth are kept beside the ones the placer predicted. A different pointer is a harness fault:
       the game read a pointer the harness wrote.

    A fault of the harness, the placer's or a handler's, ends the run ``interrupted`` with the fault as the cause.

    Args:
        target: The guest.
        profile: The platform's addresses and constants.
        recorder: The recorder whose events it follows, and which makes its writes.
        test: The landing test.
        placer: Where ``S`` comes from.
        recordings: The recordings root the test's recipe is under.
        step: The navigator's current step.

    Attributes:
        verdict: The outcome and cause the landing ended the run with, or ``None`` while it hasn't.
    """

    def __init__(
        self,
        target: Target,
        profile: PlatformProfile,
        recorder: Recorder,
        test: LandingTest,
        placer: Placer,
        recordings: Path,
        step: Callable[[], int],
    ) -> None:
        self._target = target
        self._profile = profile
        self._recorder = recorder
        self._test = test
        self._placer = placer
        self._recordings = recordings
        self._step = step
        self._heap: dict[str, Any] | None = None
        self._s: int | None = None
        self._predicted: tuple[int, int] | None = None
        self._match: float | None = None
        self._window: bytes | None = None
        self._written = False
        self._first_write: schema.StaleWrite | None = None
        self._live_top: tuple[int, int] | None = None
        self.verdict: tuple[str, str | None] | None = None

    @property
    def live_window(self) -> str | None:
        """The window as players done found it, in hex, or ``None`` before it was read."""
        return None if self._window is None else self._window.hex()

    def placement(self) -> schema.Placement | None:
        """The placement record, or ``None`` when the target's scene init never came."""
        if self._heap is None:
            return None
        return schema.Placement(
            s=self._s,
            heap=read_document(common_schema.HeapState, self._heap, "heap"),
            match=self._match,
            first_write=self._first_write,
            predicted_top=_top(self._predicted),
            live_top=_top(self._live_top),
        )

    def on_event(self, event: str, fields: dict[str, object]) -> None:
        """Follows the recorder's events."""
        if self.verdict is not None or self._step() != self._test.step:
            return
        try:
            match event:
                case "scene_init" if self._heap is None:
                    self._place(fields)
                case "players_done" if self._s is not None and self._window is None:
                    self._check_and_write()
                case "first_stale_write" if self._written and self._first_write is None:
                    self._confirm(fields)
        except Exception as error:
            self._end(INTERRUPTED, f"harness fault: {error}")

    def _place(self, fields: dict[str, object]) -> None:
        heap = fields["heap"]
        assert isinstance(heap, dict)
        self._heap = heap
        recipe = self._test.recipe
        placed = self._placer.place(
            self._recordings / recipe.recording,
            recipe.segment,
            recipe.load,
            heap,
            self._test.op,
            self._test.delta,
            self._recorder.directory,
        )
        if isinstance(placed, NotPlaced):
            self._end(NOT_PLACED, None)
            return
        self._s, self._predicted = placed.s, placed.top

    def _check_and_write(self) -> None:
        assert self._s is not None
        expected = self._test.expected
        self._window = self._target.read((self._s + self._test.offset) & 0xFFFFFFFF, len(expected))
        self._match = sum(live == wanted for live, wanted in zip(self._window, expected, strict=True)) / len(expected)
        if self._match < self._test.min_match:
            self._end(LAYOUT_MISMATCH, None)
            return
        storage = self._profile.bowl_storage
        self._recorder.write(BOWL_STORAGE, "sphere", self._profile.globals.sphere, struct.pack("<I", self._s))
        self._recorder.write(BOWL_STORAGE, "flag", storage.flag, bytes([storage.flag_set]))
        (scale,) = struct.unpack("<f", self._target.read(storage.scale, 4))
        if scale <= storage.scale_threshold:
            self._recorder.write(BOWL_STORAGE, "scale", storage.scale, struct.pack("<f", storage.scale_value))
        self._written = True

    def _confirm(self, fields: dict[str, object]) -> None:
        s = fields["s"]
        assert isinstance(s, int)
        self._first_write = schema.StaleWrite(s=s, frame=self._recorder.frame())
        heap = heap0_state(self._target.read, self._profile.heap)
        self._live_top = (heap["states"][heap["depth"]]["cursor"], heap["depth"])
        if s != self._s:
            raise ValueError(f"the game wrote through {s:#x}, not the placed {self._s:#x}")

    def _end(self, outcome: str, cause: str | None) -> None:
        self.verdict = (outcome, cause)
        self._target.interrupt()


def _top(top: tuple[int, int] | None) -> common_schema.Top | None:
    return None if top is None else common_schema.Top(cursor=top[0], depth=top[1])


class FixedHold:
    """Holds a test step for its render window's frames, counted from the step's players done.

    It stands in for the stage tracker, which decides when a test step's windows have closed.

    Args:
        recorder: The recorder whose events and frames it follows.
        step: The test step's index.
        frames: How many frames to hold it for.
        current: The navigator's current step.
    """

    def __init__(self, recorder: Recorder, step: int, frames: int, current: Callable[[], int]) -> None:
        self._recorder = recorder
        self._step = step
        self._frames = frames
        self._current = current
        self._from: int | None = None

    def on_event(self, event: str, fields: dict[str, object]) -> None:
        """Marks the frame of the test step's players done."""
        if event == "players_done" and self._current() == self._step and self._from is None:
            self._from = self._recorder.frame()

    def release(self) -> bool:
        """Whether the test step may be left."""
        return self._from is not None and self._recorder.frame() - self._from >= self._frames


def check_recipe(test: LandingTest, recordings: Path, platform: str) -> None:
    """Checks, before a session starts, that a landing's recipe is a recording made on the session's platform.

    Raises:
        ValueError: The recipe has no manifest, or was recorded on another platform.
    """
    recipe = test.recipe.recording
    try:
        recorded = json.loads((recordings / recipe / "manifest.json").read_text(encoding="utf-8"))["disc"]["platform"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError(f"the recipe {recipe} is not a recording under {recordings}: {error}") from error
    if recorded != platform:
        raise ValueError(f"the recipe {recipe} was recorded on {recorded}, not {platform}")
