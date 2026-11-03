"""Walks a route's steps, giving the input each needs and confirming each against the game."""

import struct
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from bowlharness.driving.input import InputDriver
from bowlharness.driving.request import RecordRequest
from bowlharness.profiles.profile import PlatformProfile, Ready
from bowlharness.recording.observe import u32
from bowlharness.recording.recorder import Recorder
from bowlharness.target import Capability, Target

DONE = "done"
FAILED = "failed"


class Phase(StrEnum):
    """Where the route is."""

    LOADING = "loading"
    READY = "ready"
    PAUSE = "pause"
    WORLD = "world"
    SLOT = "slot"
    WARPING = "warping"


@dataclass
class _Pending:
    """A press the navigator has given and is waiting to see the effect of."""

    action: str
    button: str
    address: int
    satisfied: Callable[[int], bool]
    queued_poll: int
    queued_frame: int
    attempts: int = 1


class Navigator:
    """Follows a request's steps through the game, one step at a time.

    A step is reached once its scene has initialised and its player is ready, by the signal of the scene's class, for
    the class's settle count of frames. Until then the navigator presses A through whatever can be skipped, and never in
    play afterwards. From a reached step it goes to the next through the pause menu: Start, the world, the slot, then A
    to select the task and confirm it, once the menu has become active. Each press is confirmed by a global the game
    changes, and a press the game didn't take is sent again, up to the profile's resend limit. The navigator is clocked
    by the driver's polls and the recorder's events.

    The route ends ``done`` when every step is reached, or ``failed`` at the first step that isn't, which it logs with
    the reason: ``scene change`` (another scene initialised), ``stalled`` (a press never took effect),
    ``menu unreachable`` (the menu doesn't hold the step's scene at its world and slot, or the confirmed warp never
    began) or ``unsupported``.

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
        self._driver: InputDriver | None = None
        self._phase = Phase.LOADING
        self._index = 0
        self._polls = 0
        self._players_frame: int | None = None
        self._since: int | None = None
        self._undrawn = False
        self._presses = 0
        self._game_opened = False
        self._trusted = False
        self._pending: _Pending | None = None
        self._menu_opened = 0
        self._confirm: tuple[int, int] | None = None
        self._retries = 0
        self._quiet = 0
        self._exit: tuple[int, int] | None = None
        self.outcome: str | None = None
        self.result: str | None = None

    def use(self, driver: InputDriver) -> None:
        """Gives the navigator the driver it presses with."""
        self._driver = driver

    def start(self) -> None:
        """Checks that the route can be driven at all, and fails it if not."""
        needed = {Capability.BREAKPOINTS, Capability.MEMORY_WRITE}
        steps = self._request.steps
        if (
            not needed <= self._target.capabilities
            or self._request.start != "booted"
            or any(step.cheats or step.costumes for step in steps)
        ):
            self._fail("unsupported")

    def on_event(self, event: str) -> None:
        """Follows the recorder's events."""
        if self.outcome is not None:
            return
        if event == "scene_init":
            self._scene_init()
        elif event == "scene_exit" and self._phase is Phase.WARPING:
            self._exit = (self._recorder.frame(), self._polls)
        elif event == "players_done" and self._phase is Phase.READY:
            self._players_frame = self._recorder.frame()

    def on_poll(self) -> None:
        """Does what the route needs next, once per poll of the controller."""
        if self.outcome is not None:
            return
        self._polls += 1
        match self._phase:
            case Phase.READY:
                self._ready()
            case Phase.PAUSE:
                self._pause()
            case Phase.WORLD:
                self._world()
            case Phase.SLOT:
                self._slot()
            case Phase.WARPING:
                self._warping()

    def _read(self, address: int) -> int:
        return u32(self._target.read, address)

    @property
    def _driver_idle(self) -> bool:
        assert self._driver is not None
        return self._driver.idle

    def _press(self, button: str) -> None:
        assert self._driver is not None
        self._driver.press(button)

    def _scene_init(self) -> None:
        if self._phase not in (Phase.LOADING, Phase.WARPING) or (
            self._recorder.scene != self._request.steps[self._index].scene
        ):
            self._fail("scene change")
            return
        if self._phase is Phase.WARPING and self._confirm and self._exit:
            self._log_navigation("confirm", "a", self._confirm, self._exit)
        self._phase = Phase.READY
        self._players_frame = None
        self._since = None
        self._undrawn = False
        self._game_opened = False
        self._presses = self._recorder.presses

    def _ready(self) -> None:
        navigation, modes = self._profile.navigation, self._profile.navigation.modes
        mode = self._read(self._profile.globals.game_mode)
        control_off = self._read(navigation.control_off)
        movie = self._read(navigation.movie_flag) == navigation.movie_playing
        cutscene = self._players_frame is not None and mode == modes.play and control_off != 0
        if (movie or cutscene) and self._driver_idle:
            self._press("b" if control_off & navigation.talk_box else "a")
        if mode == modes.pause_menu:
            self._game_opened = True
            self._menu_opened = self._polls
            self._reached("pause_menu")
        elif self._players_frame is not None:
            self._wait_for_the_player(control_off)

    def _wait_for_the_player(self, control_off: int) -> None:
        classes = self._profile.scene_classes
        scene_class = classes.of(self._request.steps[self._index].scene)
        navigation = self._profile.navigation
        frame = self._recorder.frame()
        assert self._players_frame is not None
        playing = self._read(self._profile.globals.play_state) == navigation.playing
        in_control = playing and control_off == 0
        drawn = struct.unpack("B", self._target.read(navigation.render_gate, 1))[0] != 0
        if frame - self._players_frame >= classes.stall_frames:
            if scene_class.ready is Ready.DRAWN_AND_CONTROL and not drawn and not self._undrawn:
                self._undrawn = True
                self._recorder.log_event("undrawn", scene=self._recorder.scene, counter=self._recorder.counter)
            if scene_class.ready is not Ready.FIRST_FRAME and not in_control:
                self._recorder.log_event("control_off", scene=self._recorder.scene, counter=self._recorder.counter)
                self._reached("control_off")
                return
        ready = {
            Ready.FIRST_FRAME: frame > self._players_frame,
            Ready.CONTROL: in_control,
            Ready.DRAWN_AND_CONTROL: in_control and (drawn or self._undrawn),
        }[scene_class.ready]
        if not ready:
            self._since = None
            return
        self._since = frame if self._since is None else self._since
        if frame - self._since >= scene_class.settle_frames:
            self._reached(scene_class.ready.value)

    def _reached(self, signal: str) -> None:
        self._recorder.record_step(
            self._index, "reached", presses=self._recorder.presses - self._presses, signal=signal
        )
        if self._index + 1 == len(self._request.steps):
            self._end(DONE)
            self.result = DONE
            return
        self._index += 1
        step = self._request.steps[self._index]
        assert step.menu is not None
        if self._menu_scene(step.menu.world - 1, step.menu.slot - 1) != step.scene:
            self._fail("menu unreachable")
            return
        self._trusted = False
        self._phase = Phase.WORLD if self._game_opened else Phase.PAUSE

    def _menu_scene(self, world: int, slot: int) -> str:
        navigation = self._profile.navigation
        address = navigation.menu_scenes + world * navigation.menu_row_stride + slot * navigation.menu_slot_stride
        return self._target.read(address, 4).decode("ascii", "replace")

    def _begin(self, action: str, button: str, address: int, satisfied: Callable[[int], bool]) -> None:
        self._pending = _Pending(action, button, address, satisfied, self._polls, self._recorder.frame())
        self._press(button)

    def _confirmed(self) -> bool:
        """Whether the pending press took effect; sends it again when it hasn't, and fails the step if that keeps up."""
        pending = self._pending
        assert pending is not None
        if pending.satisfied(self._read(pending.address)):
            self._log_navigation(pending.action, pending.button, (pending.queued_frame, pending.queued_poll), None)
            self._pending = None
            return True
        if self._polls - pending.queued_poll >= self._profile.navigation.action_polls and self._driver_idle:
            if pending.attempts > self._profile.input.resend_limit:
                self._fail("stalled")
            else:
                pending.attempts += 1
                pending.queued_poll = self._polls
                self._press(pending.button)
        return False

    def _pause(self) -> None:
        modes = self._profile.navigation.modes
        if self._pending is None:
            self._begin("pause", "start", self._profile.globals.game_mode, lambda mode: mode == modes.pause_menu)
        elif self._confirmed():
            self._trusted = True
            self._menu_opened = self._polls
            self._phase = Phase.WORLD

    def _world(self) -> None:
        navigation = self._profile.navigation
        menu = self._request.steps[self._index].menu
        assert menu is not None
        if self._pending is not None:
            if self._confirmed():
                self._trusted = True
            return
        if self._read(navigation.menu_active) == 0:
            if self._polls - self._menu_opened >= navigation.menu_ready_polls:
                self._fail("stalled")
            return
        world, target = self._read(navigation.menu_world), menu.world - 1
        if self._trusted and world == target:
            self._phase = Phase.SLOT
            self._slot()
            return
        start = world if self._trusted else navigation.menu_start_world
        self._begin("world", "down" if start <= target else "up", navigation.menu_world, lambda now: now != world)

    def _slot(self) -> None:
        navigation = self._profile.navigation
        menu = self._request.steps[self._index].menu
        assert menu is not None
        if self._pending is not None:
            self._confirmed()
            return
        slot, target = self._read(navigation.menu_slot), menu.slot - 1
        if slot == target:
            self._confirm = (self._recorder.frame(), self._polls)
            self._retries = 0
            self._quiet = 0
            self._exit = None
            for _ in range(self._profile.navigation.confirm_presses):
                self._press("a")
            self._phase = Phase.WARPING
            return
        self._begin("slot", "right" if slot < target else "left", navigation.menu_slot, lambda now: now != slot)

    def _warping(self) -> None:
        """Waits for the warp to begin, pressing A again only after the time it normally takes has passed."""
        assert self._confirm is not None
        navigation = self._profile.navigation
        if self._exit is not None:
            return
        self._quiet = self._quiet + 1 if self._driver_idle else 0
        if self._polls - self._confirm[1] >= navigation.warp_polls:
            self._fail("menu unreachable")
        elif (
            self._quiet >= navigation.warp_wait_polls
            and self._retries < self._profile.input.resend_limit
            and self._read(self._profile.globals.game_mode) == navigation.modes.pause_menu
        ):
            self._retries += 1
            self._quiet = 0
            self._press("a")

    def _log_navigation(self, action: str, button: str, sent: tuple[int, int], taken: tuple[int, int] | None) -> None:
        taken_frame, taken_poll = taken or (self._recorder.frame(), self._polls)
        self._recorder.log_event(
            "navigation",
            step=self._index,
            action=action,
            input=button,
            sent={"frame": sent[0], "poll": sent[1]},
            taken={"frame": taken_frame, "poll": taken_poll},
        )

    def _fail(self, reason: str) -> None:
        self._recorder.record_step(self._index, "failed", reason, presses=self._recorder.presses - self._presses)
        self._end(FAILED)
        self.result = f"{FAILED}: step {self._index} ({self._request.steps[self._index].scene}), {reason}"

    def _end(self, outcome: str) -> None:
        self.outcome = outcome
        self._target.interrupt()
