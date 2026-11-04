"""A session that drives the game along a request's route and records it."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from bowlharness.contract.generated import common_schema
from bowlharness.contract.generated import result_schema as schema
from bowlharness.driving.input import InputDriver
from bowlharness.driving.landing import FixedHold, Landing, check_recipe
from bowlharness.driving.navigation import Navigator
from bowlharness.driving.placer import PlacementFault, Placer, ToolPlacer
from bowlharness.driving.request import GUEST_FRAMES, LandingTest, Request, Window
from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.detection import Watchdog
from bowlharness.recording.recorder import Recorder
from bowlharness.recording.result import Ending, build_result, harness_version, moment, write_result
from bowlharness.session.session import ENDED, Session
from bowlharness.target import Target, TargetError

LANDED = "landed"


class DrivenSession(Session):
    """A :class:`Session` that follows a request instead of waiting for a person to play.

    It runs until the route is done, a step fails, a landing test ends the run, the guest crashes or hangs, the game
    reboots, or a person stops it. A person can still pause it, as in any session; a pause, a capture, a read or a
    press marks the run attended, and so does a button on the controller. A reboot ends the route, since the route
    can't go on after one. A landing's or a control's test step is held until its windows close, then left for the exit
    step. When the session ends it writes the run's result, ``result.json``, in ``out`` beside the recordings.

    Args:
        target: The guest to drive.
        profile: The platform's addresses and constants.
        out: The folder for the session's recording. It must not exist.
        request: The request.
        request_sha256: The hash of the request's file, which the manifest records.
        run_stem: The start of the recording's run id.
        environment: What the manifest records of the emulator and the host.
        boot_path: How the recording began: ``boot`` or ``attached``.
        liveness: How long play may stall before it is a hang, in seconds.
        on_end: Called once when the session ends, for example to close the emulator.
        harness: The harness's version for the result, or ``None`` to read it from the source tree.
        placer: Where a landing's stale pointer comes from; a landing needs one.
        recordings: The folder a landing's recipe is under; a landing needs one.

    Attributes:
        written: The run's result, once the session has ended and written it.

    Raises:
        ValueError: A landing request without a placer or a recordings folder.
    """

    def __init__(
        self,
        target: Target,
        profile: PlatformProfile,
        out: Path,
        request: Request,
        request_sha256: str,
        *,
        run_stem: str,
        environment: dict[str, Any],
        boot_path: str = "boot",
        liveness: float = 5.0,
        on_end: Callable[[], None] | None = None,
        harness: str | None = None,
        placer: Placer | None = None,
        recordings: Path | None = None,
    ) -> None:
        if isinstance(request.test, LandingTest) and (placer is None or recordings is None):
            raise ValueError("a landing request needs the placement tool and the recordings folder")
        self._request = request
        self._harness = harness or harness_version()
        self._request_sha256 = request_sha256
        self._placer = placer
        self._recipes = recordings
        self._navigator: Navigator | None = None
        self._landing: Landing | None = None
        self.written: schema.Result | None = None
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
        self._started = moment(self._frame())

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
        test, windows = self._request.test, self._request.windows
        hold = None
        if test is not None and windows is not None:
            hold = FixedHold(recorder, test.step, self._frames(windows.render), lambda: self._current_step())
        self._navigator = Navigator(
            self._target,
            self._profile,
            recorder,
            self._request,
            held_step=test.step if test else None,
            release=hold.release if hold else lambda: True,
        )
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
        if hold is not None:
            recorder.listen(hold.on_event)
        if isinstance(test, LandingTest):
            assert self._placer is not None and self._recipes is not None
            self._landing = Landing(
                self._target, self._profile, recorder, test, self._placer, self._recipes, self._current_step
            )
            recorder.listen(self._landing.on_event)
        self._navigator.start()
        return recorder, watchdog

    def _current_step(self) -> int:
        assert self._navigator is not None
        return self._navigator.step

    def _frames(self, window: Window) -> int:
        return int(window.value if window.unit == GUEST_FRAMES else window.value * self._profile.frame_rate)

    def _reopen(self) -> None:
        self._end(ended="reboot")

    def _concluded(self) -> str | None:
        if self._landing is not None and self._landing.verdict is not None:
            return LANDED
        return self.outcome

    def _frame(self) -> int | None:
        try:
            return self._recorder.frame()
        except TargetError:
            return None

    def _end(self, interrupted: str | None = None, ended: str | None = None) -> str:
        if self.ended:
            return ENDED
        frame = self._frame()
        super()._end(interrupted, ended)
        runs = [f"{self._run_stem}-{number}" for number in range(1, self.recordings + 1)]
        manifests = [json.loads((self._out / run / "manifest.json").read_text(encoding="utf-8")) for run in runs]
        landing = self._landing
        tool = self._placer.tool if self._placer else None
        self.written = build_result(
            self._request.to_json(),
            manifests,
            Ending(interrupted, ended, landing.verdict if landing else None),
            started=self._started,
            ended=moment(frame),
            harness=self._harness,
            placement=landing.placement() if landing else None,
            live_window=landing.live_window if landing else None,
            placement_tool=schema.PlacementTool(path=str(tool.path), build=tool.build, sha256=tool.sha256)
            if tool
            else None,
            windows=self._windows_record(),
        )
        write_result(self._out / "result.json", self.written)
        return ENDED

    def _windows_record(self) -> schema.Windows | None:
        windows = self._request.windows
        if windows is None:
            return None

        def record(window: Window) -> schema.WindowRecord:
            configured = common_schema.Window(unit=window.unit, value=window.value)
            return schema.WindowRecord(configured=configured, frames=None, seconds=None)

        return schema.Windows(
            render=record(windows.render), reset=record(windows.reset), write_timeout=record(windows.write_timeout)
        )


def pin_placer(request: Request, place: Path | None, recordings: Path | None, platform: str) -> Placer | None:
    """The placer a session runs ``request`` with: the pinned tool for a landing, none for anything else.

    Raises:
        ValueError: A landing without ``place`` or ``recordings``, a tool that can't be pinned, or a recipe that isn't a
            recording made on ``platform``.
    """
    if not isinstance(request.test, LandingTest):
        return None
    if place is None or recordings is None:
        raise ValueError("a landing request needs --place and --recordings")
    check_recipe(request.test, recordings, platform)
    try:
        return ToolPlacer.pin(place)
    except PlacementFault as error:
        raise ValueError(str(error)) from error
