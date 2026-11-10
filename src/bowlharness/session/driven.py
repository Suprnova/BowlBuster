"""A session that drives the game along a request's route and records it."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from bowlharness.contract.generated import result_schema as schema
from bowlharness.driving.injector import Injector
from bowlharness.driving.input import InputDriver
from bowlharness.driving.landing import Landing, check_recipe
from bowlharness.driving.navigation import Navigator
from bowlharness.driving.placer import PlacementFault, Placer, ToolPlacer
from bowlharness.driving.request import InjectTest, LandingTest, Request
from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.detection import Watchdog
from bowlharness.recording.recorder import Recorder
from bowlharness.recording.result import Ending, build_result, harness_version, moment, write_result
from bowlharness.recording.stages import StageTracker
from bowlharness.session.session import ENDED, Session
from bowlharness.target import Target, TargetError

LANDED = "landed"


class DrivenSession(Session):
    """A :class:`Session` that follows a request instead of waiting for a person to play.

    It runs until the route is done, a step fails, a landing or inject test ends the run, the guest crashes or hangs,
    the game reboots, or a person stops it. A person can still pause it, as in any session; a pause, a capture, a read
    or a press marks the run attended, and so does a button on the controller. A reboot ends the route, since the route
    can't go on after one. The test step of a landing, a control or an inject test is held until its windows close, then
    left for the exit step. When the session ends it writes the run's result, ``result.json``, in ``out`` beside the
    recordings.

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
        attempt: Which attempt at the request the run is.
        instance: The emulator instance running it, when a queue claimed it.
        on_event: Called with each event of the run's recordings, as it is logged.

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
        attempt: int = 1,
        instance: str | None = None,
        on_event: Callable[[str, dict[str, object]], None] | None = None,
    ) -> None:
        self._attempt = attempt
        self._instance = instance
        self._on_event = on_event
        if isinstance(request.test, LandingTest) and (placer is None or recordings is None):
            raise ValueError("a landing request needs the placement tool and the recordings folder")
        self._request = request
        self._harness = harness or harness_version()
        self._request_sha256 = request_sha256
        self._placer = placer
        self._recipes = recordings
        self._navigator: Navigator | None = None
        self._landing: Landing | None = None
        self._injector: Injector | None = None
        self._tracker: StageTracker | None = None
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
        if self._on_event is not None:
            recorder.listen(self._on_event)
        test, windows = self._request.test, self._request.windows
        if test is not None and windows is not None:
            self._tracker = StageTracker(
                self._target,
                self._profile,
                recorder,
                self._request.kind,
                test.step,
                windows,
                self._current_step,
                exits=test.step < len(self._request.steps) - 1,
            )
        tracker = self._tracker
        self._navigator = Navigator(
            self._target,
            self._profile,
            recorder,
            self._request,
            held_step=test.step if test else None,
            release=tracker.release if tracker else lambda: True,
            save_slot=(self._environment.get("save") or {}).get("slot"),
        )
        navigator = self._navigator

        def on_poll() -> None:
            if tracker is not None:
                tracker.on_poll()
            navigator.on_poll()

        self._driver = InputDriver(
            self._target,
            self._profile,
            recorder,
            watch_person=True,
            hold=self._request.hold,
            release=self._request.release,
            on_poll=on_poll,
        )
        navigator.use(self._driver)
        self._driver.arm()
        recorder.listen(navigator.on_event)
        if tracker is not None:
            recorder.listen(tracker.on_event)
        if isinstance(test, LandingTest):
            assert self._placer is not None and self._recipes is not None
            self._landing = Landing(
                self._target, self._profile, recorder, test, self._placer, self._recipes, self._current_step
            )
            recorder.listen(self._landing.on_event)
        if isinstance(test, InjectTest):
            scene = self._request.steps[test.step].scene
            self._injector = Injector(self._target, self._profile, recorder, test, scene, self._current_step)
            recorder.listen(self._injector.on_event)
        navigator.start()
        return recorder, watchdog

    def _current_step(self) -> int:
        assert self._navigator is not None
        return self._navigator.step

    def _reopen(self) -> None:
        self._end(ended="reboot")

    def _verdict(self) -> tuple[str, str | None] | None:
        for source in (self._landing, self._injector, self._tracker):
            if source is not None and source.verdict is not None:
                return source.verdict
        return None

    def _concluded(self) -> str | None:
        return LANDED if self._verdict() is not None else self.outcome

    def _frame(self) -> int | None:
        try:
            return self._recorder.frame()
        except TargetError:
            return None

    def _end(self, interrupted: str | None = None, ended: str | None = None) -> str:
        if self.ended:
            return ENDED
        frame = self._frame()
        landing, injector, tracker, navigator = self._landing, self._injector, self._tracker, self._navigator
        if tracker is not None:
            if ended == "failed" and navigator is not None and navigator.reason is not None:
                tracker.fail_exit(navigator.reason)
                ended = "done" if tracker.exit_failed else ended
            tracker.finish()
        super()._end(interrupted, ended)
        runs = [f"{self._run_stem}-{number}" for number in range(1, self.recordings + 1)]
        manifests = [json.loads((self._out / run / "manifest.json").read_text(encoding="utf-8")) for run in runs]
        placement = landing.placement() if landing else None
        tool = self._placer.tool if self._placer else None
        flags = []
        if tracker is not None:
            flags = tracker.flags(
                match=placement.match if placement else None,
                events_dropped=sum(manifest["events_dropped"] for manifest in manifests),
                warp_retries=navigator.warp_retries if navigator else 0,
                test_ended=injector is not None and injector.verdict is not None,
            )
        self.written = build_result(
            self._request.to_json(),
            manifests,
            Ending(interrupted, ended, self._verdict()),
            started=self._started,
            ended=moment(frame),
            harness=self._harness,
            instance=self._instance,
            attempt=self._attempt,
            placement=placement,
            injection=injector.record() if injector else None,
            live_window=landing.live_window if landing else None,
            placement_tool=schema.PlacementTool(path=str(tool.path), build=tool.build, sha256=tool.sha256)
            if tool
            else None,
            windows=tracker.windows() if tracker else None,
            stages=tracker.stages() if tracker else [],
            resets=tracker.resets if tracker else [],
            crash_stage=tracker.crash_stage if tracker else None,
            flags=flags,
        )
        write_result(self._out / "result.json", self.written)
        return ENDED


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
