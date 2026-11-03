"""A session that drives the game along a request's route and records it."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from bowlharness.driving.input import InputDriver
from bowlharness.driving.navigation import Navigator
from bowlharness.driving.request import RecordRequest
from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.detection import Watchdog
from bowlharness.recording.recorder import Recorder
from bowlharness.session.session import Session
from bowlharness.target import Target


class DrivenSession(Session):
    """A :class:`Session` that follows a request instead of waiting for a person to play.

    It runs until the route is done, a step fails, the guest crashes or hangs, the game reboots, or a person stops it.
    A person can still pause it, as in any session; a pause, a capture, a read or a press marks the run attended, and
    so does a button on the controller. A reboot ends the route, since the route can't go on after one.

    Args:
        target: The guest to drive.
        profile: The platform's addresses and constants.
        out: The folder for the session's recording. It must not exist.
        request: The route.
        request_sha256: The hash of the request's file, which the manifest records.
        run_stem: The start of the recording's run id.
        environment: What the manifest records of the emulator and the host.
        boot_path: How the recording began: ``boot`` or ``attached``.
        liveness: How long play may stall before it is a hang, in seconds.
        on_end: Called once when the session ends, for example to close the emulator.
    """

    def __init__(
        self,
        target: Target,
        profile: PlatformProfile,
        out: Path,
        request: RecordRequest,
        request_sha256: str,
        *,
        run_stem: str,
        environment: dict[str, Any],
        boot_path: str = "boot",
        liveness: float = 5.0,
        on_end: Callable[[], None] | None = None,
    ) -> None:
        self._request = request
        self._request_sha256 = request_sha256
        self._navigator: Navigator | None = None
        super().__init__(
            target,
            profile,
            out,
            request.options,
            run_stem=run_stem,
            environment=environment,
            boot_path=boot_path,
            liveness=liveness,
            on_end=on_end,
        )

    @property
    def outcome(self) -> str | None:
        """``done`` or ``failed`` once the route has ended, else ``None``."""
        return self._navigator.outcome if self._navigator else None

    @property
    def result(self) -> str | None:
        """How the route ended, for a person to read: ``done``, or ``failed`` with the step and why."""
        return self._navigator.result if self._navigator else None

    def _open(self, reason: str, boot_path: str) -> tuple[Recorder, Watchdog]:
        recorder, watchdog = super()._open(reason, boot_path)
        recorder.drive(self._request.to_json(), self._request_sha256)
        self._navigator = Navigator(self._target, self._profile, recorder, self._request)
        self._driver = InputDriver(
            self._target,
            self._profile,
            recorder,
            watch_person=True,
            hold=self._request.hold,
            release=self._request.release,
            on_poll=self._navigator.on_poll,
        )
        self._navigator.use(self._driver)
        self._driver.arm()
        recorder.listen(self._navigator.on_event)
        self._navigator.start()
        return recorder, watchdog

    def _reopen(self) -> None:
        self._end(ended="reboot")

    def _concluded(self) -> str | None:
        return self.outcome
