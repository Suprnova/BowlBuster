"""An inject test at its loads: targets resolved and words written at their timings, following the recorder's events."""

import struct
from collections.abc import Callable
from dataclasses import dataclass, field

from bowlharness.driving.injection import Resolved, resolve
from bowlharness.driving.request import ADDRESS, ASSET, Injection, InjectTest
from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.recorder import Recorder
from bowlharness.target import Target

INJECT = "inject"
NOT_INJECTED = "not injected"
INTERRUPTED = "interrupted"
AFTER_PLAYER_INIT = "after-player-init"
AT_FIRST_DRAW = "at-first-draw"


@dataclass
class Injected:
    """One injection as one load received it.

    Attributes:
        injection: The request's injection.
        anchor: Where its target resolved to; ``None`` until it has.
        timing: ``after-player-init`` or ``at-first-draw``.
        seqs: The ``seq`` of each write event it made.
    """

    injection: Injection
    timing: str
    anchor: int | None = None
    seqs: list[int] = field(default_factory=list)


@dataclass
class InjectedLoad:
    """A load the test injects: its counter and scene, and each injection's outcome there."""

    counter: int
    scene: str
    injections: list[Injected]


class Injector:
    """Writes an inject test's words in the loads it names, following the recorder's events.

    The target step's load is injected, and then every later load of its scene in the route unless the test is
    ``first_visit_only``. In each, the injections with an ``asset`` or ``address`` target are written at players done
    and those with a ``live`` or ``lookup`` target at the first drawn frame, where a landing writes. The injections of
    one timing are all resolved before the first is written. A target the load doesn't hold ends the run
    ``not injected`` with the reason as the cause, and nothing of that timing is written there; a fault of the harness
    ends it ``interrupted``.

    Args:
        target: The guest.
        profile: The platform's addresses and constants.
        recorder: The recorder whose events it follows, and which makes its writes.
        test: The inject test.
        scene: The target step's scene.
        step: The navigator's current step.

    Attributes:
        verdict: The outcome and cause the injector ended the run with, or ``None`` while it hasn't.
        loads: The loads injected so far, in order.
    """

    def __init__(
        self,
        target: Target,
        profile: PlatformProfile,
        recorder: Recorder,
        test: InjectTest,
        scene: str,
        step: Callable[[], int],
    ) -> None:
        self._target = target
        self._profile = profile
        self._recorder = recorder
        self._test = test
        self._scene = scene
        self._step = step
        self.verdict: tuple[str, str | None] | None = None
        self.loads: list[InjectedLoad] = []

    def on_event(self, event: str, fields: dict[str, object]) -> None:
        """Follows the recorder's events."""
        if self.verdict is not None:
            return
        try:
            match event:
                case "scene_init" if self._injects(fields["scene"]):
                    counter = fields["counter"]
                    assert isinstance(counter, int) and isinstance(fields["scene"], str)
                    timings = [Injected(injection, _timing(injection)) for injection in self._test.injections]
                    self.loads.append(InjectedLoad(counter, fields["scene"], timings))
                case "players_done" if self._current() is not None:
                    self._inject(AFTER_PLAYER_INIT)
                case "drawn" if self._current() is not None:
                    self._inject(AT_FIRST_DRAW)
        except Exception as error:
            self._end(INTERRUPTED, f"harness fault: {error}")

    def _injects(self, scene: object) -> bool:
        step = self._step()
        return scene == self._scene and (
            step == self._test.step or (step > self._test.step and not self._test.first_visit_only)
        )

    def _current(self) -> InjectedLoad | None:
        load = self.loads[-1] if self.loads else None
        return load if load is not None and load.counter == self._recorder.counter else None

    def _inject(self, timing: str) -> None:
        load = self._current()
        assert load is not None
        due = [injected for injected in load.injections if injected.timing == timing]
        anchors = [resolve(injected.injection.target, self._target.read, self._profile) for injected in due]
        for found in anchors:
            if not isinstance(found, Resolved):
                self._end(NOT_INJECTED, found.reason)
                return
        for injected, found in zip(due, anchors, strict=True):
            assert isinstance(found, Resolved)
            injected.anchor = found.anchor
            injected.seqs = self._write(injected.injection, found.anchor)

    def _write(self, injection: Injection, anchor: int) -> list[int]:
        words = [
            (offset, struct.pack("<f", value))
            for offset, value in self._profile.bowl_storage.footprint
            if injection.words is None or offset in injection.words
        ]
        placed = injection.values if injection.values is not None else words
        return [
            self._recorder.write(INJECT, _name(injection, offset), (anchor + offset) & 0xFFFFFFFF, data)
            for offset, data in placed
        ]

    def _end(self, outcome: str, cause: str | None) -> None:
        self.verdict = (outcome, cause)
        self._target.interrupt()


def _timing(injection: Injection) -> str:
    return AFTER_PLAYER_INIT if injection.target.kind in (ASSET, ADDRESS) else AT_FIRST_DRAW


def _name(injection: Injection, offset: int) -> str:
    target = injection.target
    if target.kind == ADDRESS:
        return f"address {(target.offset + offset) & 0xFFFFFFFF:#x}"
    assert target.id is not None
    return f"{target.kind} 0x{target.id:08X}{target.offset + offset:+#x}"
