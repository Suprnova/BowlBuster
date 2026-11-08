"""The stages of a test step's load and its windows, followed from the recorder's events and the controller's polls."""

import struct
import time
from collections.abc import Callable
from dataclasses import dataclass

from bowlharness.contract.generated import common_schema
from bowlharness.contract.generated import result_schema as schema
from bowlharness.driving.request import GUEST_FRAMES, LANDING, Window, Windows
from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.observe import u32
from bowlharness.recording.recorder import Recorder
from bowlharness.target import Target

LOADING, HELD, IN_CONTROL, RENDER, RESET, EXIT, PAUSED = (
    "loading",
    "held",
    "in control",
    "render",
    "reset",
    "exit",
    "paused",
)
COMPLETE, CUT, FAILED, OPEN = "complete", "cut", "failed", "open"
NO_WRITE, NO_CONTROL = "no write", "no control"
LONGEST_RUN_SECONDS = 240
MOST_RESETS = 3


@dataclass
class _Entry:
    stage: str
    start: int
    started: float
    end: int | None = None
    ended: float | None = None
    status: str = OPEN
    reason: str | None = None


class StageTracker:
    """Follows the test step's load through its stages, and decides when its windows have closed.

    The stages are those of a load: ``loading`` from the scene init to players done; then ``held`` while the player is
    undrawn or out of control, ``in control`` while drawn and in control, and ``paused`` while the game is paused, each
    entered again whenever it changes; ``render``, the render window, from the first stale write (a control's from the
    draw); ``reset``, the reset window, from the game's first reset, which ends the render window; and ``exit``, from
    leaving the step to the next scene init. Each change is a ``stage`` event. The windows have closed once the render
    window has, no reset window is open and the player has had control.

    A landing whose first stale write hasn't come by the write timeout, counted from players done, ends the run
    ``no write``; a run whose player hasn't had control by then ends it ``no control``. Either takes a capture, within
    the budget.

    Args:
        target: The guest.
        profile: The platform's addresses and constants.
        recorder: The recorder whose events it follows and logs to.
        kind: The request's kind: ``landing``, ``control`` or ``inject``.
        step: The test step's index.
        windows: The test step's windows.
        current: The navigator's current step.
        exits: Whether an exit step follows the test step. Without one, no exit stage opens.
        clock: The wall clock, in seconds.

    Attributes:
        verdict: The outcome the tracker ended the run with, and its cause; ``None`` while it hasn't.
        crash_stage: The stage a crash happened in, or ``None`` without one.
        resets: Every reset of the target load: its frame and counter.
    """

    def __init__(
        self,
        target: Target,
        profile: PlatformProfile,
        recorder: Recorder,
        kind: str,
        step: int,
        windows: Windows,
        current: Callable[[], int],
        *,
        exits: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._exits = exits
        self._target = target
        self._profile = profile
        self._recorder = recorder
        self._kind = kind
        self._step = step
        self._windows = windows
        self._current = current
        self._clock = clock
        self._entries: list[_Entry] = []
        self._state: _Entry | None = None
        self._render: _Entry | None = None
        self._reset: _Entry | None = None
        self._exit: _Entry | None = None
        self._players: tuple[int, float] | None = None
        self._loaded: float | None = None
        self._ended: float | None = None
        self._taken: tuple[int, float] | None = None
        self._controlled = False
        self._written = False
        self._not_in_play = False
        self._done = False
        self._crashed: int | None = None
        self.verdict: tuple[str, str | None] | None = None
        self.crash_stage: str | None = None
        self.resets: list[schema.Reset] = []

    def on_event(self, event: str, fields: dict[str, object]) -> None:
        """Follows the recorder's events."""
        if self._done:
            return
        if event == "scene_init" and self._exit is not None:
            self._close(self._exit, COMPLETE)
            self._finish()
            return
        if event == "crash":
            self._at_crash()
        if event in ("crash", "hang"):
            self._finish(CUT)
            return
        if self._current() != self._step:
            return
        match event:
            case "scene_init" if self._state is None and not self._entries:
                self._loaded = self._clock()
                self._state = self._open(LOADING)
            case "players_done" if self._players is None:
                self._players = (self._recorder.frame(), self._clock())
                self._enter(HELD)
            case "drawn" if self._kind != LANDING and self._render is None:
                self._open_render()
            case "first_stale_write" if self._kind == LANDING and not self._written:
                self._written = True
                self._not_in_play = not self._in_play()
                self._open_render()
            case "reset":
                self._game_reset()

    def on_poll(self) -> None:
        """Brings the stages up to date, once per poll of the controller."""
        if self._done or self.verdict is not None or self._players is None or self._exit is not None:
            return
        if self._current() != self._step:
            return
        self._follow_state()
        for entry, window in ((self._render, self._windows.render), (self._reset, self._windows.reset)):
            if entry is not None and entry.status == OPEN and self._elapsed(window, entry.start, entry.started):
                self._close(entry, COMPLETE)
        self._check_timeout()

    def release(self) -> bool:
        """Whether the test step may be left: its windows have closed. The first ``True`` opens the exit stage."""
        if self._exit is not None or (self._done and self.verdict is None and not self._exits):
            return True
        rendered = self._render is not None and self._render.status != OPEN
        resetting = self._reset is not None and self._reset.status == OPEN
        if not rendered or resetting or not self._controlled or self.verdict is not None:
            return False
        if self._state is not None:
            self._close(self._state, COMPLETE)
            self._state = None
        if self._exits:
            self._exit = self._open(EXIT)
        else:
            self._finish(COMPLETE)
        return True

    def fail_exit(self, reason: str) -> None:
        """Marks the exit stage failed: the warp out of the test step didn't happen, which is a finding, not a fault."""
        if self._exit is not None and self._exit.status == OPEN:
            self._close(self._exit, FAILED, reason)

    @property
    def exit_failed(self) -> bool:
        """Whether the exit stage failed."""
        return self._exit is not None and self._exit.status == FAILED

    def finish(self) -> None:
        """Ends the tracking: every stage still open was cut short by the run's end."""
        self._finish(CUT)

    def stages(self) -> list[schema.Stage]:
        """The stages, in the order they were entered."""
        return [
            schema.Stage(stage=entry.stage, from_=entry.start, to=entry.end, status=entry.status, reason=entry.reason)
            for entry in self._entries
        ]

    def windows(self) -> schema.Windows:
        """The test step's windows, as configured and as taken."""
        write = self._taken
        if write is not None and self._players is not None:
            write = (write[0] - self._players[0], write[1] - self._players[1])
        return schema.Windows(
            render=_record(self._windows.render, self._took(self._render)),
            reset=_record(self._windows.reset, self._took(self._reset)),
            write_timeout=_record(self._windows.write_timeout, write),
        )

    def flags(
        self, *, match: float | None, events_dropped: int, warp_retries: int, test_ended: bool = False
    ) -> list[str]:
        """The integrity flags of 15.1 the run raised; a run is valid when there are none.

        ``test_ended`` says the request's own test ended the run before the player had control, as ``not injected``
        does, so that the player never having control is no sign of a fault.
        """
        raised = []
        if self._crashed is not None and any(entry.start > self._crashed for entry in self._entries):
            raised.append("stage after crash")
        if self._not_in_play:
            raised.append("not in play at write")
        if self._loaded is not None and (self._ended or self._clock()) - self._loaded > LONGEST_RUN_SECONDS:
            raised.append("over 240 s")
        if len(self.resets) > MOST_RESETS:
            raised.append("over 3 resets")
        if warp_retries:
            raised.append("warp retried")
        if events_dropped:
            raised.append("events dropped")
        if self._kind != LANDING and self._entries and not self._controlled and not test_ended:
            raised.append("control never given")
        if match is not None and match < 0.9:
            raised.append("match below 0.9")
        return raised

    def _frame(self) -> int:
        return self._recorder.frame()

    def _open(self, stage: str) -> _Entry:
        entry = _Entry(stage, self._frame(), self._clock())
        self._entries.append(entry)
        self._recorder.log_event("stage", stage=stage, status=OPEN, reason=None)
        return entry

    def _close(self, entry: _Entry, status: str, reason: str | None = None) -> None:
        entry.end = None if status == CUT else self._frame()
        entry.ended, entry.status, entry.reason = self._clock(), status, reason
        self._recorder.log_event("stage", stage=entry.stage, status=status, reason=reason)

    def _enter(self, stage: str) -> None:
        if self._state is not None and self._state.stage == stage:
            return
        if self._state is not None:
            self._close(self._state, COMPLETE)
        self._state = self._open(stage)
        self._controlled |= stage == IN_CONTROL

    def _open_render(self) -> None:
        if self._render is None and self._reset is None:
            self._render = self._open(RENDER)
            self._taken = (self._frame(), self._clock())

    def _game_reset(self) -> None:
        counter = self._recorder.counter
        self.resets.append(schema.Reset(frame=self._frame(), counter=counter, cause="game"))
        if self._reset is not None:
            return
        if self._render is not None and self._render.status == OPEN:
            self._close(self._render, COMPLETE)
        self._reset = self._open(RESET)

    def _follow_state(self) -> None:
        navigation, read = self._profile.navigation, self._target.read
        mode = u32(read, self._profile.globals.game_mode)
        if mode in navigation.modes.paused:
            self._enter(PAUSED)
            return
        drawn = struct.unpack("B", read(navigation.render_gate, 1))[0] != 0
        control = (
            u32(read, self._profile.globals.play_state) == navigation.playing and u32(read, navigation.control_off) == 0
        )
        self._enter(IN_CONTROL if drawn and control else HELD)

    def _in_play(self) -> bool:
        read, navigation = self._target.read, self._profile.navigation
        return (
            u32(read, self._profile.globals.game_mode) == navigation.modes.play
            and u32(read, self._profile.globals.play_state) == navigation.playing
        )

    def _elapsed(self, window: Window, frame: int, started: float) -> bool:
        if window.unit == GUEST_FRAMES:
            return self._frame() - frame >= window.value
        return self._clock() - started >= window.value

    def _check_timeout(self) -> None:
        assert self._players is not None
        if not self._elapsed(self._windows.write_timeout, *self._players):
            return
        if self._kind == LANDING and not self._written:
            self._end(NO_WRITE)
        elif not self._controlled:
            self._end(NO_CONTROL)

    def _end(self, outcome: str) -> None:
        self.verdict = (outcome, None)
        self._recorder.capture(outcome.replace(" ", "-"))
        self._finish(CUT)
        self._target.interrupt()

    def _at_crash(self) -> None:
        frame = self._crashed = self._frame()
        if any(frame - reset.frame <= self._profile.frame_rate for reset in self.resets):
            self.crash_stage = RESET
            return
        open_entries = [entry for entry in self._entries if entry.status == OPEN]
        windows = [entry for entry in open_entries if entry.stage in (RENDER, RESET, EXIT)]
        chosen = (windows or open_entries or [None])[-1]
        self.crash_stage = chosen.stage if chosen else None

    @staticmethod
    def _took(entry: _Entry | None) -> tuple[int, float] | None:
        if entry is None or entry.end is None or entry.ended is None:
            return None
        return entry.end - entry.start, entry.ended - entry.started

    def _finish(self, status: str = CUT) -> None:
        if self._done:
            return
        self._done = True
        self._ended = self._clock()
        for entry in self._entries:
            if entry.status == OPEN:
                self._close(entry, status)


def _record(window: Window, taken: tuple[int, float] | None) -> schema.WindowRecord:
    configured = common_schema.Window(unit=window.unit, value=window.value)
    return schema.WindowRecord(
        configured=configured, frames=None if taken is None else taken[0], seconds=None if taken is None else taken[1]
    )
