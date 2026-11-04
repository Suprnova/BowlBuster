"""Writes a recording's event stream and run manifest."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

SCHEMA_VERSION = 1


class EventWriter:
    """Appends events as JSON lines, numbering them and flushing each one."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._next_seq = 0
        self.segment = 0

    def emit(self, event: str, frame: int, **fields: Any) -> int:
        """Writes one event and returns its sequence number."""
        seq = self._next_seq
        self._next_seq += 1
        line = {"seq": seq, "segment": self.segment, "frame": frame, "event": event, **fields}
        self._stream.write(json.dumps(line, separators=(",", ":")) + "\n")
        self._stream.flush()
        return seq

    @property
    def count(self) -> int:
        """How many events have been written."""
        return self._next_seq

    def close(self) -> None:
        self._stream.close()


@dataclass
class RunManifest:
    """The run manifest of a recording, rewritten whole as the recording grows.

    A driven recording is not ``passive`` and also holds the request it followed, the hash of the request's file and
    the state of each of its steps.

    The manifest says the recording is incomplete until it ends, so a reader can tell one still being written.
    """

    run: str
    platform: str
    profile: str
    boot_scene: str
    boot_counter: int
    observation: dict[str, Any]
    segments: list[dict[str, Any]] = field(default_factory=list)
    captures: list[dict[str, Any]] = field(default_factory=list)
    captures_dropped: list[dict[str, Any]] = field(default_factory=list)
    attended: bool = False
    ended: str | None = None
    environment: dict[str, Any] = field(default_factory=dict)
    crash: dict[str, Any] | None = None
    hang: dict[str, Any] | None = None
    loads: list[dict[str, Any]] = field(default_factory=list)
    input_ledger: list[dict[str, Any]] = field(default_factory=list)
    write_ledger: list[dict[str, Any]] = field(default_factory=list)
    passive: bool = True
    request: dict[str, Any] | None = None
    request_sha256: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    events_dropped: int = 0
    duplicates_discarded: int = 0
    complete: bool = False
    interrupted: str | None = None

    def to_json(self) -> dict[str, Any]:
        """The manifest as the document `manifest.json` holds."""
        return {
            "schema_version": SCHEMA_VERSION,
            "run": self.run,
            **{key: value for key, value in self.environment.items() if key != "disc"},
            "disc": {"platform": self.platform, **self.environment.get("disc", {})},
            "profile": self.profile,
            "counter_basis": {"boot_scene": self.boot_scene, "boot_counter": self.boot_counter},
            "passive": self.passive,
            **(
                {"request": self.request, "request_sha256": self.request_sha256, "steps": self.steps}
                if not self.passive
                else {}
            ),
            "attended": self.attended,
            "observation": self.observation,
            "events_dropped": self.events_dropped,
            "duplicates_discarded": self.duplicates_discarded,
            "segments": self.segments,
            "loads": self.loads,
            "captures": self.captures,
            "captures_dropped": self.captures_dropped,
            "write_ledger": self.write_ledger,
            "input_ledger": self.input_ledger,
            "crash": self.crash,
            "hang": self.hang,
            "complete": self.complete,
            "ended": self.ended,
            "interrupted": self.interrupted,
        }

    def write(self, path: Path) -> None:
        """Replaces the manifest file with the current state, never leaving it half-written."""
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.to_json(), indent=2) + "\n", encoding="utf-8", newline="\n")
        os.replace(temporary, path)
