"""A recording session: one or more recordings of a game a person plays, and the person's control over the guest."""

from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from bowlharness.driving.input import MANUAL, InputDriver
from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.detection import Watchdog
from bowlharness.recording.recorder import Options, Recorder
from bowlharness.target import Target, TargetError

PAUSED = "paused"
ENDED = "ended"


class Session:
    """Runs a guest under a recorder, watching it, and hands control to a person when they pause it.

    A session opens a recording at its start and another at each reboot of the guest, each in its own folder of
    ``out``. :meth:`run` and :meth:`resume` return when the person pauses the guest or the session ends; while it is
    paused the person can :meth:`capture`, :meth:`read`, :meth:`press` and :meth:`resume`, and each of those marks the
    run attended.

    Args:
        target: The guest to record.
        profile: The platform's addresses and constants.
        out: The folder for the session's recordings. It must not exist.
        options: What to observe.
        run_stem: The start of each recording's run id, which a counter completes.
        environment: What the manifest records of the emulator and the host.
        boot_path: How the first recording began: ``boot`` or ``attached``.
        liveness: How long play may stall before it is a hang, in seconds.
        load_limit: How long a load may stall, in seconds.
        on_end: Called once when the session ends, for example to close the emulator.
    """

    def __init__(
        self,
        target: Target,
        profile: PlatformProfile,
        out: Path,
        options: Options,
        *,
        run_stem: str,
        environment: dict[str, Any],
        boot_path: str = "boot",
        liveness: float = 5.0,
        load_limit: float = 120.0,
        on_end: Callable[[], None] | None = None,
    ) -> None:
        self._target = target
        self._profile = profile
        self._out = out
        self._options = options
        self._run_stem = run_stem
        self._environment = environment
        self._liveness = liveness
        self._load_limit = load_limit
        self._on_end = on_end
        self._recordings = 0
        self._state = "new"
        self._driver: InputDriver | None = None
        out.mkdir(parents=True)
        self._recorder, self._watchdog = self._open("attach" if boot_path == "attached" else "boot", boot_path)

    @property
    def out(self) -> Path:
        """The folder of the session's recordings."""
        return self._out

    @property
    def recordings(self) -> int:
        """How many recordings the session has opened."""
        return self._recordings

    @property
    def ended(self) -> bool:
        """Whether the session is over."""
        return self._state == ENDED

    def run(self) -> str:
        """Runs the guest until a person pauses it or the session ends; returns which."""
        if self.ended:
            return ENDED
        self._state = "running"
        if (reason := self._concluded()) is not None:
            return self._end(ended=reason)
        while True:
            try:
                expired = self._target.run(timeout=self._watchdog.liveness)
            except TargetError as error:
                return self._end(f"emulator exited: {error}")
            if expired:
                self._recorder.replay_current_stop()
            if expired and not self._recorder.ended:
                self._watchdog.check()
            if self._recorder.ended:
                return self._end()
            if self._recorder.rebooted:
                self._reopen()
                if self.ended:
                    return ENDED
            elif not expired:
                if (reason := self._concluded()) is not None:
                    return self._end(ended=reason)
                return self._pause()

    def resume(self) -> str:
        """Lets the guest run again after a pause."""
        self._require_paused()
        self._recorder.note("resume")
        self._recorder.replay_current_stop()
        self._watchdog.release()
        return self.run()

    def capture(self, label: str) -> str | None:
        """Takes a capture of the paused guest, and returns its id unless the budget refused it."""
        self._require_paused()
        return self._recorder.capture("manual", label)

    def read(self, address: int, length: int) -> bytes:
        """Reads the paused guest's memory. The read is logged, with its range and never its bytes."""
        self._require_paused()
        data = self._target.read(address, length)
        self._recorder.note("read", address=address, length=length)
        return data

    def press(self, button: str, polls: int | None = None) -> None:
        """Queues a press for the paused guest, given when it resumes. The run is attended.

        Raises:
            ValueError: ``button`` names no button, or ``polls`` is below 1.
        """
        self._require_paused()
        if self._driver is None:
            self._driver = InputDriver(self._target, self._profile, self._recorder)
            self._driver.arm()
        self._driver.press(button, source=MANUAL, hold=polls)
        self._recorder.attend()

    def stop(self) -> str:
        """Ends the session, completing the recording."""
        return self._end(ended="stopped")

    def _open(self, reason: str, boot_path: str) -> tuple[Recorder, Watchdog]:
        self._recordings += 1
        run = f"{self._run_stem}-{self._recordings}"
        recorder = Recorder(
            self._target,
            self._profile,
            self._out / run,
            run,
            self._options,
            {**self._environment, "boot_path": boot_path},
        )
        recorder.start(reason)
        return recorder, Watchdog(recorder, self._liveness, self._load_limit)

    def _reopen(self) -> None:
        """The guest rebooted, which broke the heap's continuity: ends the recording and opens another."""
        self._recorder.finish(ended="reboot")
        self._recorder.detach()
        self._driver = None
        self._recorder, self._watchdog = self._open("reboot", "reboot")
        self._recorder.replay_scene_init()

    def _concluded(self) -> str | None:
        """Why the session is over without anyone stopping it, or ``None`` while it goes on."""
        return None

    def _pause(self) -> str:
        self._state = PAUSED
        self._watchdog.hold()
        self._recorder.note("pause")
        return PAUSED

    def _require_paused(self) -> None:
        if self._state != PAUSED:
            raise RuntimeError("the guest is not paused" if self._state != ENDED else "the session has ended")

    def _end(self, interrupted: str | None = None, ended: str | None = None) -> str:
        if self._state != ENDED:
            self._state = ENDED
            self._recorder.finish(interrupted, ended)
            with suppress(TargetError):
                self._recorder.detach()
            if self._on_end:
                self._on_end()
        return ENDED
