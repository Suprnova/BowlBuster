"""Runs a store's requests one after another on one instance, and reports its progress as it goes."""

import json
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bowlharness.backends.emulator import EmulatorFault
from bowlharness.driving.request import Request, read_request
from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.result import Ending, build_result, harness_version, moment, write_result
from bowlharness.session.driven import DrivenSession
from bowlharness.store.store import Claim, Store, StoredRequest

STALL_SECONDS = 600
LOST = "lost"
STOPPED = "stopped"
EMULATOR_LOST = "emulator exited"

type OpenSession = Callable[[Request, str, Claim, Path, Callable[[str, dict[str, object]], None]], DrivenSession]


class ProgressStream:
    """The store's progress stream: one JSON line per thing that happened, for BowlBuster to read and never write.

    Args:
        path: The stream's file, appended to.
        instance: The instance writing it.
        stall_seconds: How long without progress makes a ``stall`` line.
        clock: The wall clock, in seconds.
    """

    def __init__(
        self,
        path: Path,
        instance: str,
        stall_seconds: float = STALL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._path = path
        self._instance = instance
        self._stall_seconds = stall_seconds
        self._clock = clock
        self._last = clock()
        self._stalled = False
        self._lock = threading.Lock()

    def write(self, event: str, **fields: Any) -> None:
        """Appends a line: the time, the instance, the event and its fields."""
        line = {"time": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "instance": self._instance, "event": event}
        with self._lock, self._path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(line | fields, separators=(",", ":")) + "\n")

    def touch(self) -> None:
        """Notes that the instance made progress."""
        self._last = self._clock()
        self._stalled = False

    def check_stall(self, run: str | None) -> None:
        """Writes a ``stall`` line once the instance has made no progress for the stall time, once per stall."""
        idle = self._clock() - self._last
        if idle >= self._stall_seconds and not self._stalled:
            self._stalled = True
            self.write("stall", run=run, seconds=round(idle))


class Queue:
    """Runs a store's pending requests on one instance, oldest first, a new attempt for each claim.

    For each it claims the request, reboots the guest, runs the request as ``bowl drive`` would into the claim's run
    folder, and releases the claim once the result is written. It goes on until nothing is pending, a person stops it,
    or a session is cut short by a lost emulator. A request it can't run is refused with a progress line and left; a
    duplicate of a request with a result is skipped, and the line names the one it matched.

    Args:
        store: The store.
        progress: Its progress stream.
        profile: The platform's addresses and constants.
        open_session: Opens the session that runs a request: given the request, its file's hash, the claim, the run's
            folder and a listener for the run's events.
        reboot: Boots the guest afresh for a run, on the storage its request needs. A ``ValueError`` refuses the
            request with nothing stopped; an :class:`EmulatorFault` means the emulator is down, and the queue stops.
    """

    def __init__(
        self,
        store: Store,
        progress: ProgressStream,
        profile: PlatformProfile,
        open_session: OpenSession,
        reboot: Callable[[Request], None],
    ) -> None:
        self._store = store
        self._progress = progress
        self._profile = profile
        self._open_session = open_session
        self._reboot = reboot
        self._reported: set[str] = set()
        self._claims: dict[int, Claim] = {}
        self._current: str | None = None
        self.done = 0
        self.stopped = False

    @property
    def current(self) -> str | None:
        """The run in progress, or ``None``."""
        return self._current

    def recover(self) -> list[str]:
        """Releases the claims this instance's dead sessions left, each run's result written ``interrupted``, ``lost``.

        Returns:
            The runs recovered.
        """
        recovered = []
        for claim in self._store.dead_claims():
            folder = self._store.run_folder(claim)
            manifests = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted(folder.glob("*/manifest.json"), key=lambda path: path.parent.name)
            ]
            written = (folder / "result.json").exists()
            if manifests and not written:
                request, _ = read_request(self._store.requests / f"{claim.request_id}.json", self._profile)
                result = build_result(
                    request.to_json(),
                    manifests,
                    Ending(interrupted=LOST),
                    started=moment(None),
                    ended=moment(None),
                    harness=harness_version(),
                    instance=claim.instance,
                    attempt=claim.attempt,
                )
                write_result(folder / "result.json", result)
            self._store.release(claim)
            self._progress.write("recovered", run=claim.run, result=manifests != [] or written)
            recovered.append(claim.run)
        return recovered

    def start_next(self) -> DrivenSession | None:
        """Claims the next pending request, reboots the guest and opens its session; ``None`` when nothing is left."""
        if self.stopped:
            return None
        while True:
            pending, skipped, refused = self._store.pending()
            for name, reason in refused:
                self._report("refused", name, request=name, reason=reason)
            for request, match in skipped:
                self._report("skipped", request.request_id, request=request.request_id, matched=match)
            pending = [request for request in pending if request.request_id not in self._reported]
            if not pending:
                return None
            if (session := self._start(pending[0], len(pending) - 1)) is not None or self.stopped:
                return session

    def finish(self, session: DrivenSession) -> bool:
        """Records a finished session's run and releases its claim. Returns whether the queue goes on."""
        claim = self._claims.pop(id(session))
        written = session.written
        self.done += 1
        self._current = None
        self._progress.touch()
        if written is not None:
            self._progress.write(
                "finished",
                run=claim.run,
                outcome=written.outcome,
                flags=written.integrity.flags,
                token_gain=None,
                done=self.done,
                left=len(self._store.pending()[0]),
            )
        self._store.release(claim)
        cause = written.cause if written is not None else None
        if written is None or cause == STOPPED or (cause or "").startswith(EMULATOR_LOST):
            self.stopped = True
        return not self.stopped

    def stop(self) -> None:
        """Runs no further request once the current one ends."""
        self.stopped = True

    def _start(self, request: StoredRequest, left: int) -> DrivenSession | None:
        try:
            parsed, digest = read_request(request.path, self._profile)
        except (OSError, ValueError) as error:
            self._report("refused", request.request_id, request=request.request_id, reason=str(error))
            return None
        claim = self._store.claim(request)
        if claim is None:
            return None
        try:
            self._reboot(parsed)
        except ValueError as error:
            self._store.release(claim)
            self._report("refused", request.request_id, request=request.request_id, reason=str(error))
            return None
        except EmulatorFault as error:
            self._store.release(claim)
            self._progress.write(LOST, request=request.request_id, reason=str(error))
            self.stopped = True
            return None
        self._current = claim.run
        self._progress.touch()
        self._progress.write("started", run=claim.run, attempt=claim.attempt, done=self.done, left=left)

        def on_event(event: str, fields: dict[str, object]) -> None:
            self._progress.touch()
            if event == "stage":
                self._progress.write("stage", run=claim.run, stage=fields["stage"], status=fields["status"])

        try:
            session = self._open_session(parsed, digest, claim, self._store.run_folder(claim), on_event)
        except ValueError as error:
            self._store.release(claim)
            self._report("refused", request.request_id, request=request.request_id, reason=str(error))
            return None
        self._claims[id(session)] = claim
        return session

    def _report(self, event: str, key: str, **fields: Any) -> None:
        if key not in self._reported:
            self._reported.add(key)
            self._progress.write(event, **fields)
