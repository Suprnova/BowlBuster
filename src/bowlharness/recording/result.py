"""Builds a run's result from its recordings, and writes it once."""

import json
import os
import subprocess
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bowlharness.contract.documents import read_document, write_document
from bowlharness.contract.generated import common_schema
from bowlharness.contract.generated import result_schema as schema

SCHEMA_VERSION = 1
NOT_OBSERVED = "the observed-fields list is not confirmed"
ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Ending:
    """How a session ended, as the session saw it.

    Attributes:
        interrupted: Why the session was cut short, such as the emulator exiting; ``None`` when it wasn't.
        ended: Why a session that wasn't cut short ended: the route's ``done`` or ``failed``, ``stopped`` by a person,
            or ``reboot``. A crash or a hang says so in its recording.
    """

    interrupted: str | None = None
    ended: str | None = None


def moment(frame: int | None) -> schema.Moment:
    """Now, at the guest's ``frame``."""
    return schema.Moment(wall=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), frame=frame)


def harness_version(root: Path = ROOT) -> str:
    """The harness's version, with the commit it runs from and ``.dirty`` when its tree has changes."""
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    try:
        commit = _git(root, "rev-parse", "--short", "HEAD")
        dirty = _git(root, "status", "--porcelain", "--untracked-files=no")
    except OSError, subprocess.CalledProcessError:
        return version
    return f"{version}+{commit}{'.dirty' if dirty else ''}"


def _git(root: Path, *arguments: str) -> str:
    found = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, check=True)
    return found.stdout.strip()


def outcome(manifests: list[dict[str, Any]], ending: Ending) -> tuple[schema.Outcome, str | None]:
    """A record run's outcome and its cause, from its recordings' manifests and how its session ended.

    A crash or a hang wins; then a session cut short is ``interrupted`` with its reason; then the route's own end:
    ``survived`` when every step was reached, or the failed step's reason. A session a person stopped, or that a
    reboot ended, is ``interrupted`` with ``stopped`` or ``reboot``.
    """
    last = manifests[-1]
    if last["ended"] in ("crash", "hang"):
        return last["ended"], None
    if ending.interrupted is not None:
        return "interrupted", ending.interrupted
    if ending.ended == "done":
        return "survived", None
    failed = next((step for step in last.get("steps", []) if step["status"] == "failed"), None)
    if ending.ended == "failed" and failed is not None:
        return failed["reason"], None
    return "interrupted", ending.ended or "stopped"


def build_record_result(
    request: dict[str, Any],
    manifests: list[dict[str, Any]],
    ending: Ending,
    *,
    started: schema.Moment,
    ended: schema.Moment,
    harness: str,
    instance: str | None = None,
    attempt: int = 1,
) -> schema.Result:
    """The result of a driven record run.

    Args:
        request: The request as the run's manifests record it, defaults included.
        manifests: The manifest of each of the run's recordings, in order.
        ending: How the session ended.
        started: When the run started.
        ended: When it ended.
        harness: The harness's version.
        instance: The emulator instance that ran it, when a queue claimed it.
        attempt: Which attempt at the request this is.
    """
    first = manifests[0]
    storage = first.get("storage", {})
    kind, cause = outcome(manifests, ending)
    crash = next((manifest["crash"] for manifest in manifests if manifest["crash"]), None)
    hang = next((manifest["hang"] for manifest in manifests if manifest["hang"]), None)
    return schema.Result(
        schema_version=SCHEMA_VERSION,
        run=f"{request['request_id']}-a{attempt}",
        request=request["request_id"],
        attempt=attempt,
        kind=request["kind"],
        instance=instance,
        started=started,
        ended=ended,
        outcome=kind,
        cause=cause,
        manifest=schema.Manifest(
            harness=harness,
            platform=first["disc"]["platform"],
            profile=first["profile"],
            counter_basis=schema.CounterBasis(**first["counter_basis"]),
            emulator=_emulator(first.get("emulator", {})),
            disc=schema.Disc(image=first["disc"].get("image"), image_sha256=first["disc"].get("image_sha256")),
            storage=schema.Storage(image=storage.get("image"), bytes=storage.get("bytes")),
            gdb=first["gdb"],
            host=first["host"],
            boot_path=first["boot_path"],
            request_sha256=first["request_sha256"],
            setup=request["start"]["from"],
            observation=read_document(common_schema.Observe, request["observe"], "observe"),
            input=read_document(common_schema.InputPolicy, request["input"], "input"),
            windows=None,
            placement_tool=None,
            recordings=[manifest["run"] for manifest in manifests],
            steps=[_step(step) for step in manifests[-1]["steps"]],
            loads=[_load(manifest["run"], load) for manifest in manifests for load in manifest["loads"]],
            events_dropped=sum(manifest["events_dropped"] for manifest in manifests),
        ),
        placement=None,
        stages=[],
        crash=_crash(crash) if crash else None,
        hang=_hang(hang) if hang else None,
        resets=[],
        integrity=schema.Integrity(flags=[]),
        effects=schema.Effects(observed=False, reason=NOT_OBSERVED),
        write_ledger=[
            schema.Write(
                recording=manifest["run"],
                seq=row["seq"],
                class_=row["class"],
                target=row["target"],
                address=row["address"],
                new=row["new"],
            )
            for manifest in manifests
            for row in manifest["write_ledger"]
        ],
        input_ledger=[
            read_document(schema.Press, {"recording": manifest["run"], **row}, "press")
            for manifest in manifests
            for row in manifest["input_ledger"]
        ],
        attended=any(manifest["attended"] for manifest in manifests),
        captures=[
            schema.Capture(recording=manifest["run"], **capture)
            for manifest in manifests
            for capture in manifest["captures"]
        ],
        captures_dropped=[
            schema.DroppedCapture(recording=manifest["run"], **capture)
            for manifest in manifests
            for capture in manifest["captures_dropped"]
        ],
        client=request.get("client"),
        memory=schema.Memory(
            live_window=None,
            old_bytes=[
                schema.OldBytes(recording=manifest["run"], seq=row["seq"], bytes=row["old"])
                for manifest in manifests
                for row in manifest["write_ledger"]
            ],
            crash=schema.CrashMemory(registers=crash["registers"], stack=crash["stack"]) if crash else None,
        ),
    )


def write_result(path: Path, result: schema.Result) -> None:
    """Writes ``result`` to ``path``, which must not exist yet, so a reader never sees half of one."""
    if path.exists():
        raise FileExistsError(f"{path} already holds a result")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(write_document(result), indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _emulator(emulator: dict[str, Any]) -> schema.Emulator:
    return schema.Emulator(
        name=emulator["name"],
        version=emulator.get("version"),
        commit=emulator.get("commit"),
        date=emulator.get("date"),
        executable_sha256=emulator.get("executable_sha256"),
        config_sha256=emulator["config_sha256"],
        controller=emulator.get("controller"),
    )


def _step(step: dict[str, Any]) -> schema.StepRecord:
    return schema.StepRecord(
        index=step["index"],
        scene=step["scene"],
        status=step["status"],
        reason=step.get("reason"),
        signal=step.get("signal"),
        frame=step.get("frame"),
        presses=step.get("presses", 0),
    )


def _load(recording: str, load: dict[str, Any]) -> schema.Load:
    return schema.Load(
        recording=recording,
        segment=load["segment"],
        counter=load["counter"],
        scene=load["scene"],
        costumes=load["costumes"],
    )


def _crash(crash: dict[str, Any]) -> schema.Crash:
    return schema.Crash(
        kind=crash["kind"],
        code=crash["code"],
        params=crash["params"],
        arch=crash["arch"],
        return_addresses=crash["return_addresses"],
        instruction=crash.get("instruction"),
        access=crash.get("access"),
        accessed=crash.get("accessed"),
        scene=crash["scene"],
        counter=crash["counter"],
        capture=crash["capture"],
        stage=None,
    )


def _hang(hang: dict[str, Any]) -> schema.Hang:
    last = hang["last_event"]
    return schema.Hang(
        stalled=hang["stalled"],
        last_frame=hang["last_frame"],
        last_event=schema.EventReference(seq=last["seq"], event=last["event"]) if last else None,
        scene=hang["scene"],
        counter=hang["counter"],
        capture=hang["capture"],
    )
