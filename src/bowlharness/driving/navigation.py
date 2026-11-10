"""Walks a route's steps, giving the input each needs and confirming each against the game."""

import struct
import time
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum

from bowlharness.driving.cheats import Code, plan_codes, read_codes
from bowlharness.driving.costumes import extra_row_state, find_extras, plan_costumes
from bowlharness.driving.focus import find_focus, highlighted, row_ids
from bowlharness.driving.input import InputDriver
from bowlharness.driving.request import Request
from bowlharness.profiles.profile import PlatformProfile, Ready
from bowlharness.recording.observe import u32, worn_archives
from bowlharness.recording.recorder import Recorder
from bowlharness.target import Capability, Target, TargetError

DONE = "done"
FAILED = "failed"


class Phase(StrEnum):
    """Where the route is."""

    LOADING = "loading"
    READY = "ready"
    PAUSE = "pause"
    WORLD = "world"
    SLOT = "slot"
    CONFIRM = "confirm"
    WARPING = "warping"
    CHEATS = "cheats"
    MAIN_MENU = "main menu"
    HELD = "held"


class Screen(StrEnum):
    """Where the route is between boot and its first scene: a new game's, or a loaded save's."""

    LOGOS = "logos"
    TITLE = "title"
    MENU = "menu"
    NEW_GAME = "new game"
    LOAD_GAME = "load game"
    SAVE = "save"


NO_SAVE_CHOSEN = 0xFFFFFFFF


class Stage(StrEnum):
    """Where the entry of a step's cheat codes is."""

    MENU = "menu"
    OPEN = "open"
    HOLD = "hold"
    SETTLE = "settle"
    CODE = "code"
    EXTRAS = "extras"
    CHOOSE = "choose"
    BACK = "back"
    SHUT = "shut"
    LEAVE = "leave"
    CLOSE = "close"


@dataclass
class _Pending:
    """A press the navigator has given and is waiting to see the effect of."""

    action: str
    button: str
    read: Callable[[], int]
    satisfied: Callable[[int], bool]
    queued_poll: int
    queued_frame: int
    deadline: float | None = None
    attempts: int = 1


class Navigator:
    """Follows a request's steps through the game, one step at a time.

    A step is reached once its scene has initialised and its player is ready, by the signal of the scene's class, for
    the class's settle count of frames. Until then the navigator presses A through whatever can be skipped, and never in
    play afterwards. A reached step then enters its cheat codes, and those that leave the next step's costumes worn, in
    the Options menu: X from the pause menu, then L and R held, then the code's X and Y presses, each confirmed by the
    game's count of them and the code by its bit in the cheat mask. A code that doesn't take is entered again from a
    cleared history, up to the profile's resend limit. B leaves Options as soon as the codes are in. From the step it
    goes to the next through the pause menu: Start, the world, the slot, then A to select the task and confirm it, once
    the menu has become active, each A once the menu has counted the last. Each press is confirmed by a value the game
    changes. A press the game didn't take is
    sent again: Start up to the profile's resend limit, and a press in a menu, which ignores input for a while after it
    opens or after Options closes, until the menu's ready time has passed. Since A is the one press that does harm in
    Options, the As go only after a press in the pause menu has been confirmed since Options closed; a cursor already on
    the task is moved off it and back. The navigator is clocked by the driver's polls and the recorder's events.

    The route ends ``done`` when every step is reached, or ``failed`` at the first step that isn't, which it logs with
    the reason: ``scene change`` (another scene initialised), ``costume mismatch`` (the load wears other costumes than
    the step names), ``stalled`` (a press never took effect), ``menu unreachable`` (the menu doesn't hold the step's
    scene at its world and slot, or the confirmed warp never began) or ``unsupported`` (a code or costume no cheat
    gives, or a route the target can't be driven along).

    Attributes:
        warp_retries: How many times a confirmed warp that didn't begin was confirmed again, over the whole route.
        reason: Why the step that failed failed, once one has.

    Args:
        target: The guest, which the navigator interrupts when the route ends.
        profile: The platform's addresses and constants.
        recorder: The recorder that logs the steps.
        request: The route.
        held_step: A step that is held once reached, until ``release`` says it may be left: a test step, watched
            through its windows.
        release: Whether the held step may be left.
        save_slot: The slot, from 1, of the save a ``save`` start loads; the run's storage holds it there.
    """

    def __init__(
        self,
        target: Target,
        profile: PlatformProfile,
        recorder: Recorder,
        request: Request,
        *,
        held_step: int | None = None,
        release: Callable[[], bool] = lambda: True,
        save_slot: int | None = None,
    ) -> None:
        self._held_step = held_step
        self._save_slot = save_slot
        self._planned: deque[str] = deque()
        self._chosen = False
        self._chose_row = False
        self._flags: list[int] = []
        self._extras_row = 0
        self._presses_left = 0
        self._entered = False
        self._release = release
        self._target = target
        self._profile = profile
        self._recorder = recorder
        self._request = request
        self._driver: InputDriver | None = None
        self._phase = Phase.LOADING
        self._screen = Screen.LOGOS
        self._index = 0
        self._polls = 0
        self._players_frame: int | None = None
        self._since: int | None = None
        self._undrawn = False
        self._busy_since: int | None = None
        self._presses = 0
        self._game_opened = False
        self._trusted = False
        self._pending: _Pending | None = None
        self._menu_opened = 0.0
        self._menu_proven = True
        self._confirm: tuple[int, int] | None = None
        self._exit: tuple[int, int] | None = None
        self._retries = 0
        self._accepted = 0
        self.warp_retries = 0
        self._quiet = 0
        self._signal = ""
        self._codes: deque[Code] = deque()
        self._extras: deque[int] = deque()
        self._controller = 0
        self._stage = Stage.MENU
        self._number = 0
        self._attempt = 0
        self._mark = 0
        self._expected = 0
        self._after_pause = Phase.WORLD
        self.outcome: str | None = None
        self.result: str | None = None
        self.reason: str | None = None

    @property
    def step(self) -> int:
        """The index of the step being reached or left."""
        return self._index

    def use(self, driver: InputDriver) -> None:
        """Gives the navigator the driver it presses with."""
        self._driver = driver

    def start(self) -> None:
        """Checks that the route can be driven at all, and fails it if not."""
        needed = {Capability.BREAKPOINTS, Capability.MEMORY_WRITE}
        if not needed <= self._target.capabilities or (self._request.start == "save" and self._save_slot is None):
            self._fail("unsupported")
        elif self._request.start in ("new-game", "save"):
            self._phase = Phase.MAIN_MENU
            self._enter(Screen.LOGOS)

    def on_event(self, event: str, fields: dict[str, object]) -> None:
        """Follows the recorder's events."""
        if self.outcome is not None:
            return
        if event == "scene_init":
            self._scene_init()
        elif event == "scene_exit" and self._phase in (Phase.CONFIRM, Phase.WARPING):
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
            case Phase.CONFIRM:
                self._accept()
            case Phase.WARPING:
                self._warping()
            case Phase.CHEATS:
                self._cheats()
            case Phase.MAIN_MENU:
                self._main_menu()
            case Phase.HELD if self._release():
                self._reached(self._signal)

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
        if self._phase is Phase.MAIN_MENU and self._recorder.scene == self._profile.boot_scene:
            return
        if self._phase not in (Phase.LOADING, Phase.CONFIRM, Phase.WARPING, Phase.MAIN_MENU) or (
            self._recorder.scene != self._request.steps[self._index].scene
        ):
            self._fail("scene change")
            return
        if self._phase in (Phase.CONFIRM, Phase.WARPING) and self._confirm and self._exit:
            self._log_navigation("warp", "a", self._confirm, self._exit)
        worn = {archive for archive in worn_archives(self._target.read, self._profile.costumes).values() if archive}
        if worn != set(self._request.steps[self._index].costumes):
            self._fail("costume mismatch")
            return
        self._phase = Phase.READY
        self._pending = None
        self._players_frame = None
        self._since = None
        self._undrawn = False
        self._busy_since = None
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
            self._menu_opened = time.monotonic()
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
        self._signal = signal
        if self._index == self._held_step and not self._release():
            self._phase = Phase.HELD
            return
        last = self._index + 1 == len(self._request.steps)
        following = None if last else self._request.steps[self._index + 1].costumes
        read = self._target.read
        try:
            codes = plan_codes(read, self._profile, self._request.steps[self._index].cheats)
            extras: tuple[int, ...] = ()
            if following is not None:
                mask = self._read(self._profile.costumes.cheat_mask)
                for code in codes:
                    mask = code.apply(mask)
                plan = plan_costumes(read, self._profile, read_codes(read, self._profile), mask, following)
                codes, extras = [*codes, *plan.codes], plan.extras
        except ValueError:
            self._fail("unsupported")
            return
        self._codes, self._extras = deque(codes), deque(extras)
        if not self._codes and not self._extras:
            self._finish_step(menu_open=self._game_opened)
            return
        self._stage = Stage.MENU
        self._number = self._attempt = 0
        self._after_pause = Phase.CHEATS
        self._menu_opened = time.monotonic()
        self._phase = Phase.CHEATS if self._game_opened else Phase.PAUSE

    def _finish_step(self, *, menu_open: bool) -> None:
        self._recorder.record_step(
            self._index, "reached", presses=self._recorder.presses - self._presses, signal=self._signal
        )
        if self._index + 1 == len(self._request.steps):
            self._end(DONE)
            self.result = DONE
            return
        self._flags = []
        self._index += 1
        step = self._request.steps[self._index]
        assert step.menu is not None
        if self._menu_scene(step.menu.world - 1, step.menu.slot - 1) != step.scene:
            self._fail("menu unreachable")
            return
        self._after_pause = Phase.WORLD
        self._menu_opened = time.monotonic()
        self._trusted = menu_open and not self._game_opened
        self._phase = Phase.WORLD if menu_open else Phase.PAUSE

    def _menu_scene(self, world: int, slot: int) -> str:
        navigation = self._profile.navigation
        address = navigation.menu_scenes + world * navigation.menu_row_stride + slot * navigation.menu_slot_stride
        return self._target.read(address, 4).decode("ascii", "replace")

    def _begin(
        self, action: str, button: str, address: int, satisfied: Callable[[int], bool], *, patient: bool = False
    ) -> None:
        self._begin_reading(action, button, lambda: self._read(address), satisfied, patient=patient)

    def _begin_reading(
        self,
        action: str,
        button: str,
        read: Callable[[], int],
        satisfied: Callable[[int], bool],
        *,
        patient: bool = False,
    ) -> None:
        deadline = time.monotonic() + self._profile.navigation.ready_seconds if patient else None
        self._pending = _Pending(action, button, read, satisfied, self._polls, self._recorder.frame(), deadline)
        self._press(button)

    def _begin_down(self, action: str) -> None:
        """Presses Down in a menu, confirmed by the highlight leaving the row it was on."""
        before = highlighted(self._target.read, self._flags)
        self._begin_reading(
            action, "down", lambda: highlighted(self._target.read, self._flags), lambda now: now != before, patient=True
        )

    def _taken(self) -> bool:
        """Whether the pending press took effect, which is then logged."""
        pending = self._pending
        assert pending is not None
        if not pending.satisfied(pending.read()):
            return False
        self._log_navigation(pending.action, pending.button, (pending.queued_frame, pending.queued_poll), None)
        self._pending = None
        return True

    def _overdue(self) -> bool:
        """Whether the pending press has had its polls to show an effect and the driver has nothing left to give."""
        assert self._pending is not None
        if self._pending.action == "pause" and self._player_busy():
            return False
        return self._polls - self._pending.queued_poll >= self._profile.navigation.action_polls and self._driver_idle

    def _player_busy(self) -> bool:
        """Whether Start would be ignored: the player is out of control in a step it reached in control, as it is
        while it dies. This holds for at most the scene classes' stall length, so a player that never recovers still
        ends the step ``stalled``."""
        if self._signal == "control_off" or self._read(self._profile.navigation.control_off) == 0:
            self._busy_since = None
            return False
        frame = self._recorder.frame()
        self._busy_since = frame if self._busy_since is None else self._busy_since
        return frame - self._busy_since < self._profile.scene_classes.stall_frames

    def _confirmed(self) -> bool:
        """Whether the pending press took effect; sends it again when it hasn't, and fails the step if that keeps up.

        A patient press is sent again until the menu's ``ready_seconds`` have passed, since a menu ignores input for a
        time it measures in real time; any other press is sent again up to the resend limit.
        """
        if self._taken():
            return True
        if self._overdue():
            pending = self._pending
            assert pending is not None
            if self._exhausted(pending):
                self._fail("stalled")
            else:
                pending.attempts += 1
                pending.queued_poll, pending.queued_frame = self._polls, self._recorder.frame()
                self._press(pending.button)
        return False

    def _exhausted(self, pending: _Pending) -> bool:
        if pending.deadline is None:
            return pending.attempts > self._profile.input.resend_limit
        return time.monotonic() >= pending.deadline

    def _pause(self) -> None:
        modes = self._profile.navigation.modes
        if self._pending is None:
            if not self._player_busy():
                self._begin("pause", "start", self._profile.globals.game_mode, lambda mode: mode == modes.pause_menu)
        elif self._confirmed():
            self._trusted = True
            self._menu_opened = time.monotonic()
            self._phase = self._after_pause

    def _world(self) -> None:
        navigation = self._profile.navigation
        menu = self._request.steps[self._index].menu
        assert menu is not None
        if self._pending is not None:
            if self._confirmed():
                self._trusted = self._menu_proven = True
            return
        if self._read(navigation.menu_active) == 0:
            if self._menu_late():
                self._fail("stalled")
            return
        world, target = self._read(navigation.menu_world), menu.world - 1
        if self._trusted and world == target:
            if self._menu_proven:
                self._phase = Phase.SLOT
                self._slot()
            else:
                self._begin(
                    "world", "up" if world else "down", navigation.menu_world, lambda now: now != world, patient=True
                )
            return
        start = world if self._trusted else navigation.menu_start_world
        button = "down" if start <= target else "up"
        self._begin("world", button, navigation.menu_world, lambda now: now != world, patient=True)

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
            self._accepted = 0
            self._phase = Phase.CONFIRM
            self._accept()
            return
        button = "right" if slot < target else "left"
        self._begin("slot", button, navigation.menu_slot, lambda now: now != slot, patient=True)

    def _accept(self) -> None:
        """Presses A to select the task and confirm its warp, each A once the menu has counted the one before."""
        navigation = self._profile.navigation
        assert self._confirm is not None
        if self._polls - self._confirm[1] >= navigation.warp_polls:
            self._fail("stalled")
            return
        if self._read(self._profile.globals.game_mode) != navigation.modes.pause_menu:
            self._pending = None
            self._phase = Phase.WARPING
            return
        if self._pending is not None:
            if not self._confirmed():
                return
            self._accepted += 1
            if self._accepted == navigation.confirm_presses:
                self._phase = Phase.WARPING
                return
        if (screen := self._pause_screen()) is None:
            if self._menu_late():
                self._fail("stalled")
            return
        accepted = screen + navigation.screens.accepted
        before = self._read(accepted)
        self._begin("confirm", "a", accepted, lambda now: now != before, patient=True)

    def _pause_screen(self) -> int | None:
        """The pause menu's screen, found by its name among those around the active one, nearest first, or ``None``.

        A place that can't be read holds no screen.
        """
        screens = self._profile.navigation.screens
        active = self._read(self._profile.navigation.menu_active)
        for step in sorted(range(-screens.reach, screens.reach + 1), key=abs):
            screen = (active + step * screens.stride) & 0xFFFFFFFF
            with suppress(TargetError):
                if self._read(screen + screens.name) == screens.pause_menu:
                    return screen
        return None

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
            self.warp_retries += 1
            self._quiet = 0
            self._press("a")

    def _enter(self, screen: Screen) -> None:
        self._screen = screen
        self._menu_opened = time.monotonic()
        self._pending = None
        self._recorder.log_event("screen", name=screen.value)

    def _main_menu(self) -> None:
        """Takes the game from its boot logos to the load of the first step: A through the logos, Start at the title,
        then A until a new game's load begins, or Load Game and the save's slot. Each screen is left on the game's
        signal, and a screen that never is ends the step ``stalled``, the last ``screen`` event naming it."""
        navigation = self._profile.navigation
        match self._screen:
            case Screen.LOGOS:
                if self._read(self._profile.globals.game_mode) == navigation.modes.menu:
                    self._enter(Screen.TITLE)
                elif self._read(navigation.movie_flag) == navigation.movie_playing and self._driver_idle:
                    self._press("a")
            case Screen.TITLE:
                if self._pending is None:
                    before = self._read(navigation.title_start)
                    self._begin("title", "start", navigation.title_start, lambda now: now != before)
                elif self._confirmed():
                    self._enter(Screen.MENU)
                    return
            case Screen.MENU:
                if self._read(navigation.menu_active):
                    if self._save_slot is None:
                        self._enter(Screen.NEW_GAME)
                    else:
                        self._flags = find_focus(self._target.read, self._profile)
                        if self._flags:
                            self._enter(Screen.LOAD_GAME)
                            self._begin_down("menu")
                        else:
                            self._fail("unsupported")
                    return
            case Screen.NEW_GAME:
                if self._driver_idle:
                    self._press("a")
            case Screen.LOAD_GAME:
                pending = self._pending
                if pending is not None and self._confirmed():
                    if pending.button == "down":
                        self._begin(
                            "menu", "a", self._profile.globals.game_mode, lambda m: m == navigation.modes.load_game
                        )
                    else:
                        assert self._save_slot is not None
                        self._plan(Screen.SAVE, ["down"] * (self._save_slot - 1) + ["a"])
                    return
            case Screen.SAVE if not self._chosen:
                if (chosen := self._read(navigation.chosen_save)) != NO_SAVE_CHOSEN:
                    self._chose(chosen + 1)
                    return
                self._press_planned()
        if self._menu_late():
            self._fail("stalled")

    def _plan(self, screen: Screen, buttons: list[str]) -> None:
        """Enters ``screen`` and queues presses that nothing confirms, each ``action_polls`` after the one before."""
        self._enter(screen)
        self._planned = deque(buttons)
        self._mark = self._polls

    def _press_planned(self) -> None:
        if self._planned and self._driver_idle and self._polls - self._mark >= self._profile.navigation.action_polls:
            self._press(self._planned.popleft())
            self._mark = self._polls

    def _chose(self, slot: int) -> None:
        """Load Game took an A on ``slot``, and the save in it is loading: the save's, or the step fails."""
        self._planned.clear()
        self._chosen = True
        self._recorder.log_event("save_slot", slot=slot, wanted=self._save_slot)
        if slot != self._save_slot:
            self._fail("stalled")

    def _menu_late(self) -> bool:
        """Whether the wait for a menu has outlasted the time the profile allows."""
        return time.monotonic() - self._menu_opened >= self._profile.navigation.ready_seconds

    def _cheats(self) -> None:
        """Enters the step's codes in the Options menu, then leaves it for the pause menu."""
        navigation = self._profile.navigation
        match self._stage:
            case Stage.MENU:
                if self._read(navigation.menu_active):
                    self._press_for_screen("x")
                    self._stage = Stage.OPEN
                elif self._menu_late():
                    self._fail("stalled")
            case Stage.OPEN:
                if self._confirmed():
                    if self._codes:
                        self._stage = Stage.HOLD
                    else:
                        self._open_extras()
            case Stage.HOLD if self._driver_idle:
                assert self._driver is not None
                self._driver.hold_chord("l", "r")
                self._mark = self._polls
                self._stage = Stage.SETTLE
            case Stage.SETTLE:
                held = self._read(self._read(self._profile.input.active_record) + self._profile.input.held_offset)
                if held & navigation.cheats.held == navigation.cheats.held:
                    self._mark = self._polls
                    self._stage = Stage.CODE
                elif self._polls - self._mark >= navigation.action_polls:
                    self._fail("stalled")
            case Stage.CODE:
                self._enter_code()
            case Stage.LEAVE if self._driver_idle:
                assert self._driver is not None
                self._driver.release_chord()
                if self._extras:
                    self._open_extras()
                    return
                if self._index + 1 == len(self._request.steps):
                    self._finish_step(menu_open=True)
                    return
                self._press_for_screen("b")
                self._stage = Stage.CLOSE
            case Stage.CLOSE:
                if self._confirmed():
                    self._menu_proven = False
                    self._finish_step(menu_open=True)
            case Stage.EXTRAS:
                self._reach_extras()
            case Stage.CHOOSE:
                self._choose_extra()
            case Stage.BACK:
                if self._confirmed():
                    play = self._profile.navigation.modes.pause_menu
                    self._begin("pause", "b", self._profile.globals.game_mode, lambda mode: mode != play, patient=True)
                    self._stage = Stage.SHUT
            case Stage.SHUT:
                if self._confirmed():
                    self._finish_step(menu_open=False)

    def _reach_extras(self) -> None:
        """Presses Down until the highlight is on the Extras row, each press confirmed by the highlight moving, then A,
        which nothing confirms: the first cursor press waits ``action_polls`` for the screen to open. Options opens on
        the row it was left on, so the presses needed vary; a highlight that never reaches the row in one lap ends
        the step ``stalled``."""
        if self._pending is not None:
            self._confirmed()
        elif not self._driver_idle:
            return
        elif self._entered:
            if self._polls - self._mark >= self._profile.navigation.action_polls:
                self._stage = Stage.CHOOSE
        elif highlighted(self._target.read, self._flags) == self._extras_row:
            self._press("a")
            self._entered, self._mark = True, self._polls
        elif self._presses_left:
            self._presses_left -= 1
            self._begin_down("options")
        else:
            self._fail("stalled")

    def _open_extras(self) -> None:
        """Finds the Extras screen and the Options rows, and starts for the Extras row."""
        extras = self._profile.navigation.extras
        if (controller := find_extras(self._target.read, self._profile)) is None:
            self._fail("unsupported")
            return
        flags = find_focus(self._target.read, self._profile)
        if not flags:
            self._fail("unsupported")
            return
        self._controller, self._flags = controller, flags
        ids = row_ids(self._target.read, self._profile, flags)
        if extras.options_id not in ids:
            self._fail("unsupported")
            return
        self._extras_row = 1 << ids.index(extras.options_id)
        self._presses_left, self._entered = len(flags), False
        self._stage = Stage.EXTRAS

    def _choose_extra(self) -> None:
        """Moves the Extras cursor to the next row to choose, each move confirmed by the cursor, and chooses it with A,
        confirmed by the row's state byte; then leaves for the pause menu."""
        extras = self._profile.navigation.extras
        if self._pending is not None:
            if self._confirmed() and self._chose_row:
                self._chose_row = False
                self._extras.popleft()
            return
        if not self._extras:
            self._press_for_screen("b")
            self._stage = Stage.BACK
            return
        if not self._driver_idle:
            return
        cursor = self._target.read(self._controller + extras.row, 2)
        columns = self._target.read(self._controller + extras.columns, 1)[0] or 1
        row = self._extras[0]
        target = divmod(row, columns)
        if (cursor[0], cursor[1]) == target:
            address = self._profile.costumes.extras + row * self._profile.costumes.extra_stride
            before = extra_row_state(self._target.read, self._profile, row)
            self._chose_row = True
            self._begin(
                "extra", "a", address, lambda _: extra_row_state(self._target.read, self._profile, row) != before
            )
            return
        if cursor[0] != target[0]:
            button = "down" if cursor[0] < target[0] else "up"
        else:
            button = "right" if cursor[1] < target[1] else "left"
        before_cursor = self._read(self._controller + extras.row)
        self._begin("extra", button, self._controller + extras.row, lambda now: now != before_cursor)

    def _press_for_screen(self, button: str) -> None:
        """Presses a button that opens or closes a menu screen, confirmed by the screen count changing."""
        address = self._profile.navigation.menu_screens
        before = self._read(address)
        self._begin("options", button, address, lambda now: now != before, patient=True)

    def _enter_code(self) -> None:
        """Presses the first code's buttons one at a time, each confirmed by the game's count of them.

        The last press is confirmed by the cheat mask taking the code's bit. A press that shows no effect abandons the
        attempt: the history is let clear, and the code is entered again from its start.
        """
        cheats, mask = self._profile.navigation.cheats, self._profile.costumes.cheat_mask
        code = self._codes[0]
        if self._pending is not None:
            if self._taken():
                self._number += 1
                if self._number == len(code.presses):
                    self._codes.popleft()
                    self._number = self._attempt = 0
                    self._stage = Stage.CODE if self._codes else Stage.LEAVE
            elif self._overdue():
                self._pending = None
                self._number = 0
                self._mark = self._polls
                self._attempt += 1
                if self._attempt > self._profile.input.resend_limit:
                    self._fail("stalled")
            return
        if self._number == 0:
            if self._read(cheats.count):
                if self._polls - self._mark >= cheats.clear_polls:
                    self._fail("stalled")
                return
            self._expected = code.apply(self._read(mask))
        number, expected = self._number + 1, self._expected
        if number == len(code.presses):
            self._begin("cheat", code.presses[self._number], mask, lambda now: now == expected)
        else:
            self._begin("cheat", code.presses[self._number], cheats.count, lambda now: now == number)

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
        self.reason = reason
        self._end(FAILED)
        self.result = f"{FAILED}: step {self._index} ({self._request.steps[self._index].scene}), {reason}"

    def _end(self, outcome: str) -> None:
        self.outcome = outcome
        self._target.interrupt()
