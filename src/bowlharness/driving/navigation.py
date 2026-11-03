"""Walks a route's steps, confirming each against the game."""

import struct

from bowlharness.driving.request import RecordRequest
from bowlharness.profiles.profile import PlatformProfile, Ready
from bowlharness.recording.observe import u32
from bowlharness.recording.recorder import Recorder
from bowlharness.target import Capability, Target

DONE = "done"
FAILED = "failed"


class Navigator:
    """Follows a request's steps through the game, one step at a time.

    A step is reached once its scene has initialised and its player is ready, by the signal of the scene's class, for
    the class's settle count of frames. The navigator is clocked by the recorder's events and the driver's polls. It
    ends the route as ``done`` when every step is reached, or ``failed`` at the first step that isn't, which it logs
    with the reason: ``scene change`` (another scene initialised), ``stalled`` (the player wasn't ready within the
    profile's stall limit) or ``unsupported``.

    Args:
        target: The guest, which the navigator interrupts when the route ends.
        profile: The platform's addresses and constants.
        recorder: The recorder that logs the steps.
        request: The route.
    """

    def __init__(self, target: Target, profile: PlatformProfile, recorder: Recorder, request: RecordRequest) -> None:
        self._target = target
        self._profile = profile
        self._recorder = recorder
        self._request = request
        self._index = 0
        self._loaded = False
        self._players_frame: int | None = None
        self._since: int | None = None
        self._presses = 0
        self.outcome: str | None = None
        self.result: str | None = None

    def start(self) -> None:
        """Checks that the route can be driven at all, and fails it if not."""
        needed = {Capability.BREAKPOINTS, Capability.MEMORY_WRITE}
        if (
            not needed <= self._target.capabilities
            or self._request.start != "booted"
            or self._request.steps[0].cheats
            or self._request.steps[0].costumes
        ):
            self._fail("unsupported")

    def on_event(self, event: str) -> None:
        """Follows the recorder's events."""
        if self.outcome is not None:
            return
        if event == "scene_init":
            self._scene_init()
        elif event == "players_done" and self._loaded:
            self._players_frame = self._recorder.frame()

    def on_poll(self) -> None:
        """Checks whether the player is ready, once per poll of the controller."""
        if self.outcome is not None or self._players_frame is None:
            return
        scene_class = self._profile.scene_classes.of(self._request.steps[self._index].scene)
        frame = self._recorder.frame()
        if frame - self._players_frame >= self._profile.scene_classes.stall_frames:
            self._fail("stalled")
        elif not self._signal(scene_class.ready, frame):
            self._since = None
        else:
            self._since = frame if self._since is None else self._since
            if frame - self._since >= scene_class.settle_frames:
                self._reached()

    def _scene_init(self) -> None:
        if self._loaded or self._recorder.scene != self._request.steps[self._index].scene:
            self._fail("scene change")
            return
        self._loaded = True
        self._presses = self._recorder.presses

    def _signal(self, ready: Ready, frame: int) -> bool:
        navigation = self._profile.navigation
        read = self._target.read
        if ready is Ready.FIRST_FRAME:
            return self._players_frame is not None and frame > self._players_frame
        playing = u32(read, self._profile.globals.play_state) == navigation.playing
        in_control = u32(read, navigation.control_off) == 0
        if ready is Ready.CONTROL:
            return playing and in_control
        drawn = struct.unpack("B", read(navigation.render_gate, 1))[0] != 0
        return playing and in_control and drawn

    def _reached(self) -> None:
        self._recorder.record_step(self._index, "reached", presses=self._recorder.presses - self._presses)
        self._index += 1
        self._loaded = False
        self._players_frame = None
        self._since = None
        if self._index == len(self._request.steps):
            self._end(DONE)
            self.result = DONE
        else:
            self._fail("unsupported")

    def _fail(self, reason: str) -> None:
        self._recorder.record_step(self._index, "failed", reason, presses=self._recorder.presses - self._presses)
        self._end(FAILED)
        self.result = f"{FAILED}: step {self._index} ({self._request.steps[self._index].scene}), {reason}"

    def _end(self, outcome: str) -> None:
        self.outcome = outcome
        self._target.interrupt()
