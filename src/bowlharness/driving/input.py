"""Presses buttons at the game's pad read."""

import struct
from collections import deque
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
    """Gives the game buttons by ORing them into the button dword its pad read has just filled.

    The game rebuilds that dword at every poll, so a press touches no game state: it goes in the input ledger and the
    ``press`` events, never in the write ledger. A press is held for its polls and released for the profile's
    ``release_polls`` before the next begins, and a scene init cancels a press in progress, since no press is held
    across a load. A poll is a stop at the pad read of the active pad that read a pad; every such stop counts.

    Args:
        target: The guest to give input to.
        profile: The platform's addresses and constants.
        recorder: The recorder that logs the presses and gets the polls.
        watch_person: Whether to log the physical controller's presses, which marks the run attended.
    """

    def __init__(
        self, target: Target, profile: PlatformProfile, recorder: Recorder, *, watch_person: bool = False
    ) -> None:
        self._target = target
        self._profile = profile
        self._recorder = recorder
        self._watch_person = watch_person
        self._queue: deque[_Press] = deque()
        self._current: _Press | None = None
        self._person: _Press | None = None
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
        profile = self._profile.input
        if (mask := getattr(profile.buttons, button, None)) is None:
            names = ", ".join(f.name for f in fields(profile.buttons))
            raise ValueError(f"no button {button!r}; the buttons are {names}")
        if hold is not None and hold < 1:
            raise ValueError("a press is held for at least 1 poll")
        self._queue.append(_Press(button, mask, source, hold or profile.hold_polls))

    def _poll(self, hit: Hit) -> None:
        profile = self._profile.input
        active = struct.unpack("b", self._target.read(self._profile.globals.active_port, 1))[0]
        if hit.result == 0 or hit.words[profile.port_word] != active:
            return
        self.polls += 1
        self._recorder.count_poll()
        buffer = hit.words[profile.buffer_word]
        physical = u32(self._target.read, buffer)
        if self._watch_person:
            self._follow_person(physical)
        self._advance(hit, buffer, physical)

    def _advance(self, hit: Hit, buffer: int, physical: int) -> None:
        if self._current is None and self._queue:
            self._current = self._queue.popleft()
        if (press := self._current) is None:
            return
        if press.held < press.hold:
            if press.held == 0:
                press.context = self._context()
            else:
                self._look_for_the_edge(hit, press)
            self._target.write(buffer, struct.pack("<I", physical | press.mask))
            press.held += 1
            return
        if press.released == 0:
            self._look_for_the_edge(hit, press)
            self._recorder.log_press({**press.row, "cancelled": False})
        press.released += 1
        if press.released >= self._profile.input.release_polls:
            self._current = None

    def _context(self) -> dict[str, Any]:
        read = self._target.read
        return {
            "game_mode": u32(read, self._profile.globals.game_mode),
            "play_state": u32(read, self._profile.globals.play_state),
            "control_off": u32(read, self._profile.navigation.control_off),
            "sent_poll": self.polls,
            "sent_frame": self._recorder.frame(),
        }

    def _look_for_the_edge(self, hit: Hit, press: _Press) -> None:
        """Notes the frame the game took a press: the pad record shows the previous poll's pressed edge."""
        profile = self._profile.input
        record = hit.words[profile.record_word]
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

    def _event(self, event: str) -> None:
        if event != "scene_init" or (press := self._current) is None:
            return
        self._current = None
        if 0 < press.held <= press.hold and press.released == 0:
            self._recorder.log_press({**press.row, "cancelled": True})
