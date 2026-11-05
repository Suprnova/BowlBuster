"""Presses buttons at the game's pad read."""

import struct
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from typing import Any

from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.observe import u32
from bowlharness.recording.recorder import Hit, Recorder
from bowlharness.target import Target

HARNESS = "harness"
MANUAL = "manual"
PERSON = "person"


@dataclass
class _Press:
    button: str
    mask: int
    source: str
    hold: int
    held: int = 0
    released: int = 0
    taken: int | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def row(self) -> dict[str, Any]:
        return {
            "button": self.button,
            "mask": self.mask,
            "source": self.source,
            "step": None,
            **self.context,
            "polls": self.held,
            "taken_frame": self.taken,
        }


class InputDriver:
    """Gives the game buttons by setting them in the controller state its pad read has just copied.

    The game copies that state afresh at every poll and builds its button dword from it, so a press touches no game
    state: it goes in the input ledger and the ``press`` events, never in the write ledger. A chord
    (:meth:`hold_chord`) is held at every poll until it is released, across the presses queued while it is held. A
    press is held for its polls and released for the profile's ``release_polls`` before the next begins, and a scene
    init cancels a press in progress and drops the queued ones, since no press is held across a load. A poll is a stop
    at the pad read of the active pad; every such stop counts, except one that finds the state holding what the driver
    wrote at the previous stop, which is the debugger reporting the same poll twice.

    Args:
        target: The guest to give input to.
        profile: The platform's addresses and constants.
        recorder: The recorder that logs the presses and gets the polls.
        watch_person: Whether to log the physical controller's presses, which marks the run attended.
        hold: How many polls a press is held for by default, or ``None`` for the profile's.
        release: How many polls a press is released for, or ``None`` for the profile's.
        on_poll: Called after each poll is counted and its press advanced.
    """

    def __init__(
        self,
        target: Target,
        profile: PlatformProfile,
        recorder: Recorder,
        *,
        watch_person: bool = False,
        hold: int | None = None,
        release: int | None = None,
        on_poll: Callable[[], None] | None = None,
    ) -> None:
        self._target = target
        self._profile = profile
        self._recorder = recorder
        self._watch_person = watch_person
        self._hold = hold or profile.input.hold_polls
        self._release = release or profile.input.release_polls
        self._on_poll = on_poll
        self._queue: deque[_Press] = deque()
        self._current: _Press | None = None
        self._person: _Press | None = None
        self._chord: _Press | None = None
        self._written: tuple[int, bytes] | None = None
        self.polls = 0

    def arm(self) -> None:
        """Starts giving input: observes the pad read and the scene inits that cancel a press."""
        self._recorder.arm_pad_read(self._poll)
        self._recorder.listen(self._event)

    @property
    def idle(self) -> bool:
        """Whether no press is queued or in progress."""
        return self._current is None and not self._queue

    def press(self, button: str, *, source: str = HARNESS, hold: int | None = None) -> None:
        """Queues a press of ``button`` (a name in the profile's buttons) for the next polls.

        Args:
            button: The button's name.
            source: Who asked for it: ``harness`` for a route's own, ``manual`` for a person at the console.
            hold: How many polls to hold it for, or ``None`` for the profile's.

        Raises:
            ValueError: ``button`` names no button, or ``hold`` is below 1.
        """
        mask = self._mask(button)
        if hold is not None and hold < 1:
            raise ValueError("a press must be held for at least 1 poll")
        self._queue.append(_Press(button, mask, source, hold or self._hold))

    def hold_chord(self, *buttons: str) -> None:
        """Holds ``buttons`` at every poll from the next, across the presses that follow, until :meth:`release_chord`.

        Raises:
            ValueError: A name is not a button, or a chord is already held.
        """
        if self._chord is not None:
            raise ValueError("a chord is already held")
        masks = [self._mask(button) for button in buttons]
        self._chord = _Press("+".join(buttons), sum(masks), HARNESS, 0)

    def release_chord(self) -> None:
        """Lets go of the chord and logs it as one press. Does nothing when none is held."""
        if (chord := self._chord) is not None:
            self._chord = None
            self._recorder.log_press({**chord.row, "cancelled": False})

    def _mask(self, button: str) -> int:
        profile = self._profile.input
        if (mask := getattr(profile.buttons, button, None)) is None:
            names = ", ".join(f.name for f in fields(profile.buttons))
            raise ValueError(f"invalid button {button!r}, options are {names}")
        return mask

    def _poll(self, hit: Hit) -> None:
        profile = self._profile.input
        port = hit.words[profile.port_word]
        if port != struct.unpack("b", self._target.read(self._profile.globals.active_port, 1))[0]:
            return
        address = profile.state_base + port * profile.state_size
        state = self._target.read(address, profile.state_size)
        if self._written == (address, state):
            return
        self._written = None
        self.polls += 1
        self._recorder.count_poll()
        physical = profile.held(state)
        if self._watch_person:
            self._follow_person(physical)
        self._advance(port, address, state, physical)
        if self._on_poll:
            self._on_poll()

    def _advance(self, port: int, address: int, state: bytes, physical: int) -> None:
        value = physical
        if (chord := self._chord) is not None:
            if chord.held == 0:
                chord.context = self._context()
            chord.held += 1
            value |= chord.mask
        if self._current is None and self._queue:
            self._current = self._queue.popleft()
        if (press := self._current) is not None:
            value |= self._step(port, press)
        if value != physical:
            written = self._profile.input.holding(state, value)
            self._target.write(address, written)
            self._written = (address, written)

    def _step(self, port: int, press: _Press) -> int:
        """Moves a press one poll on and returns the buttons it gives at this poll."""
        if press.held < press.hold:
            if press.held == 0:
                press.context = self._context()
            else:
                self._look_for_the_edge(port, press)
            press.held += 1
            return press.mask
        if press.released == 0:
            self._look_for_the_edge(port, press)
            self._recorder.log_press({**press.row, "cancelled": False})
        press.released += 1
        if press.released >= self._release:
            self._current = None
        return 0

    def _context(self) -> dict[str, Any]:
        read = self._target.read
        return {
            "game_mode": u32(read, self._profile.globals.game_mode),
            "play_state": u32(read, self._profile.globals.play_state),
            "control_off": u32(read, self._profile.navigation.control_off),
            "sent_poll": self.polls,
            "sent_frame": self._recorder.frame(),
        }

    def _look_for_the_edge(self, port: int, press: _Press) -> None:
        """Notes the frame the game took a press: the pad record shows the previous poll's pressed edge."""
        profile = self._profile.input
        record = profile.record_base + port * profile.record_stride
        if press.taken is None and u32(self._target.read, record + profile.pressed_offset) & press.mask:
            press.taken = self._recorder.frame()

    def _follow_person(self, physical: int) -> None:
        """Logs the physical controller's buttons as one press when they are let go."""
        if physical:
            if self._person is None:
                self._person = _Press("", 0, PERSON, 0, context=self._context())
            self._person.mask |= physical
            self._person.held += 1
        elif (person := self._person) is not None:
            self._person = None
            buttons = self._profile.input.buttons
            named = [f.name for f in fields(buttons) if person.mask & getattr(buttons, f.name)]
            person.button = "+".join(named) or f"{person.mask:#x}"
            self._recorder.log_press({**person.row, "cancelled": False})

    def _event(self, event: str, fields: dict[str, object]) -> None:
        if event != "scene_init":
            return
        self._queue.clear()
        if (chord := self._chord) is not None:
            self._chord = None
            self._recorder.log_press({**chord.row, "cancelled": True})
        if (press := self._current) is None:
            return
        self._current = None
        if 0 < press.held <= press.hold and press.released == 0:
            self._recorder.log_press({**press.row, "cancelled": True})
