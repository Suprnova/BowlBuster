"""The store a queue runs from: requests, claims on them, the runs they made, and the progress stream.

```
<store>/requests/<request_id>.json     a request; never changed
<store>/claims/<request_id>.json       an instance's claim on it, removed with the run's result
<store>/runs/<run>/result.json         a run's result, written once
<store>/runs/<run>/<recording>/        the run's recordings
<store>/progress.jsonl                 the progress stream
```
"""

import hashlib
import json
import os
import platform
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class StoredRequest:
    """A request file of the store.

    Attributes:
        request_id: The request's id, which is its file's name.
        path: The file.
        content: The SHA-256 of its canonical JSON without ``request_id`` and ``client``, which deduplicates it.
    """

    request_id: str
    path: Path
    content: str


@dataclass(frozen=True)
class Claim:
    """An instance's claim on a request: the run it is making.

    Attributes:
        request_id: The request.
        run: The run's id, ``<request_id>-a<attempt>``.
        attempt: Which attempt it is, from 1.
        instance: The instance that claimed it.
        host: The machine it runs on.
        pid: The process that claimed it.
    """

    request_id: str
    run: str
    attempt: int
    instance: str
    host: str
    pid: int


def content_hash(document: Any) -> str:
    """The SHA-256 of a request's canonical JSON (sorted keys, no whitespace) without ``request_id`` and ``client``."""
    content = {key: value for key, value in document.items() if key not in ("request_id", "client")}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def process_alive(pid: int) -> bool:
    """Whether a process with ``pid`` is running on this machine.

    On Windows this asks the system for the process's exit code, since ``os.kill`` there would send it Ctrl-C.
    """
    if sys.platform == "win32":
        import ctypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Store:
    """A store's folders, read and claimed from by one instance.

    Args:
        root: The store's folder.
        instance: The name of the instance using it.
        host: The machine it runs on.
        pid: Its process.
    """

    def __init__(self, root: Path, instance: str, host: str | None = None, pid: int | None = None) -> None:
        self.root = root
        self.instance = instance
        self.host = host or platform.node()
        self.pid = pid or os.getpid()
        for folder in (self.requests, self.claims, self.runs):
            folder.mkdir(parents=True, exist_ok=True)

    @property
    def requests(self) -> Path:
        """The folder of request files."""
        return self.root / "requests"

    @property
    def claims(self) -> Path:
        """The folder of claim files."""
        return self.root / "claims"

    @property
    def runs(self) -> Path:
        """The folder of runs, one per attempt."""
        return self.root / "runs"

    @property
    def progress(self) -> Path:
        """The progress stream."""
        return self.root / "progress.jsonl"

    def stored(self) -> tuple[list[StoredRequest], list[tuple[str, str]]]:
        """Every request file, oldest first, and those that can't be read: each file's name and why."""
        found, refused = [], []
        for path in sorted(self.requests.glob("*.json"), key=lambda path: (path.stat().st_mtime_ns, path.name)):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except ValueError as error:
                refused.append((path.name, f"{path.name} is not valid JSON: {error}"))
                continue
            if not isinstance(document, dict) or document.get("request_id") != path.stem:
                refused.append((path.name, f"{path.name} must hold the request whose request_id is {path.stem!r}"))
                continue
            found.append(StoredRequest(path.stem, path, content_hash(document)))
        return found, refused

    def results(self, request_id: str) -> list[dict[str, Any]]:
        """The results of every attempt at a request, in attempt order."""
        return [
            json.loads((run / "result.json").read_text(encoding="utf-8"))
            for run in self._run_folders(request_id)
            if (run / "result.json").exists()
        ]

    def finished(self, request_id: str) -> bool:
        """Whether a request has a result that isn't ``interrupted``."""
        return any(result["outcome"] != INTERRUPTED for result in self.results(request_id))

    def claimed(self, request_id: str) -> Claim | None:
        """The claim on a request, or ``None``."""
        path = self.claims / f"{request_id}.json"
        try:
            return Claim(**json.loads(path.read_text(encoding="utf-8"))["claim"])
        except FileNotFoundError:
            return None

    def duplicate_of(self, request: StoredRequest, among: list[StoredRequest]) -> str | None:
        """The id of an earlier request with the same content and a result that isn't interrupted, if there is one."""
        return next(
            (
                other.request_id
                for other in among
                if other.request_id != request.request_id
                and other.content == request.content
                and self.finished(other.request_id)
            ),
            None,
        )

    def pending(self) -> tuple[list[StoredRequest], list[tuple[StoredRequest, str]], list[tuple[str, str]]]:
        """The requests to run, oldest first; those skipped as duplicates, each with the request it matched; and the
        files that can't be read, each with why.

        A request is pending when it has no claim and no result that isn't ``interrupted``.
        """
        stored, refused = self.stored()
        pending, skipped = [], []
        for request in stored:
            if self.finished(request.request_id) or self.claimed(request.request_id) is not None:
                continue
            if (match := self.duplicate_of(request, stored)) is not None:
                skipped.append((request, match))
            else:
                pending.append(request)
        return pending, skipped, refused

    def claim(self, request: StoredRequest) -> Claim | None:
        """Claims a request for a new attempt, or ``None`` when another claim got there first.

        The claim file is created exclusively, so of two instances claiming one request, one wins.
        """
        attempt = self._next_attempt(request.request_id)
        claim = Claim(
            request.request_id, f"{request.request_id}-a{attempt}", attempt, self.instance, self.host, self.pid
        )
        document = {"claim": claim.__dict__, "claimed": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
        try:
            descriptor = os.open(self.claims / f"{request.request_id}.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return None
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            json.dump(document, file)
        return claim

    def release(self, claim: Claim) -> None:
        """Removes a claim, once its run's result is written."""
        (self.claims / f"{claim.request_id}.json").unlink(missing_ok=True)

    def dead_claims(self) -> list[Claim]:
        """This instance's claims whose process is gone, which a lost session left. Others' are never touched."""
        dead = []
        for path in sorted(self.claims.glob("*.json")):
            claim = self.claimed(path.stem)
            if claim is None or claim.instance != self.instance or claim.host != self.host:
                continue
            if claim.pid != self.pid and not process_alive(claim.pid):
                dead.append(claim)
        return dead

    def run_folder(self, claim: Claim) -> Path:
        """Where a claim's run writes its recordings and its result."""
        return self.runs / claim.run

    def _run_folders(self, request_id: str) -> list[Path]:
        pattern = re.compile(rf"{re.escape(request_id)}-a(\d+)")
        found = [
            (int(match[1]), path)
            for path in self.runs.glob(f"{request_id}-a*")
            if (match := pattern.fullmatch(path.name))
        ]
        return [path for _, path in sorted(found)]

    def _next_attempt(self, request_id: str) -> int:
        folders = self._run_folders(request_id)
        return int(folders[-1].name.rsplit("-a", 1)[1]) + 1 if folders else 1
