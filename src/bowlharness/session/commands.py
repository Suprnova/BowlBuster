"""The arguments of the ``bowl`` console commands, parsed without gdb."""

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from bowlharness.recording.recorder import Options


@dataclass(frozen=True)
class LaunchArguments:
    """What every command that starts a session is told about the emulator and where to record.

    Attributes:
        out: The folder for the session's recordings; it must not exist.
        xemu: The emulator to start (``--xemu``, or else ``BOWL_XEMU``), or ``None`` when attaching to a running one.
        config: The emulator's configuration file, or ``None`` for its default.
        port: The port of the emulator's debugger stub.
        attach: Whether to attach to a running emulator instead of starting one.
        liveness: How long play may stall before it is a hang, in seconds.
        name: What the run ids start with.
    """

    out: Path
    xemu: Path | None
    config: Path | None
    port: int
    attach: bool
    liveness: float
    name: str


@dataclass(frozen=True)
class RecordArguments(LaunchArguments):
    """What ``bowl record`` was asked to do.

    Attributes:
        options: What to observe.
    """

    options: Options


@dataclass(frozen=True)
class DriveArguments(LaunchArguments):
    """What ``bowl drive`` was asked to do.

    Attributes:
        request: The file holding the request to follow.
        place: The published copy of ``bowlbuster`` that places landings, which a landing needs.
        recordings: The folder a landing's recipes are under, which a landing needs.
    """

    request: Path
    place: Path | None = None
    recordings: Path | None = None


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        raise ValueError(message or self.format_usage())


def scene_selection(text: str) -> bool | frozenset[str]:
    """``all``, ``none``, or a comma-separated list of scenes."""
    match text.strip().lower():
        case "all":
            return True
        case "none" | "":
            return False
    scenes = frozenset(scene.strip().upper() for scene in text.split(","))
    if bad := [scene for scene in scenes if len(scene) != 4]:
        raise ValueError(f"a scene is four characters, got {', '.join(sorted(bad))}")
    return scenes


def _launch_parser(prog: str, run_name: str) -> _Parser:
    parser = _Parser(prog=prog, add_help=False)
    parser.add_argument("--out", type=Path, required=True, help="a folder that does not exist yet")
    parser.add_argument("--xemu", type=Path, help="the emulator to start")
    parser.add_argument("--config", type=Path, help="the emulator's configuration file")
    parser.add_argument("--port", type=int, default=1234)
    parser.add_argument("--attach", type=int, metavar="PORT", help="attach to a running emulator's stub")
    parser.add_argument("--liveness", type=float, default=5.0)
    parser.add_argument("--name", default=run_name)
    return parser


def _emulator(found: argparse.Namespace) -> tuple[Path | None, int, bool]:
    """The emulator to start (``--xemu``, else ``BOWL_XEMU``) or the stub to attach to, the port, and which."""
    if found.attach is not None:
        if found.xemu is not None:
            raise ValueError("--xemu and --attach are alternatives")
        return None, found.attach, True
    xemu = found.xemu or (Path(named) if (named := os.environ.get("BOWL_XEMU")) else None)
    if xemu is None:
        raise ValueError(
            "give --xemu, or set BOWL_XEMU, to start an emulator, or --attach PORT to attach to a running one"
        )
    return xemu, found.port, False


def _launch(found: argparse.Namespace) -> LaunchArguments:
    if not found.out.is_absolute():
        raise ValueError(f"--out must be an absolute path, got {found.out}")
    xemu, port, attach = _emulator(found)
    return LaunchArguments(
        out=found.out,
        xemu=xemu,
        config=found.config,
        port=port,
        attach=attach,
        liveness=found.liveness,
        name=found.name,
    )


def parse_record_arguments(arguments: list[str], run_name: str) -> RecordArguments:
    """Reads the arguments of ``bowl record``. Raises ``ValueError`` with a message for the person."""
    parser = _launch_parser("bowl record", run_name)
    parser.add_argument("--heap", default="all", help="all, none, or scenes")
    parser.add_argument("--captures", default="none", help="cutoff:all, cutoff:none or cutoff:scenes")
    parser.add_argument("--budget", type=int)
    found = parser.parse_args(arguments)
    return RecordArguments(
        **vars(_launch(found)),
        options=Options(
            heap_events=scene_selection(found.heap),
            cutoff_captures=scene_selection(found.captures.removeprefix("cutoff:")),
            capture_budget=found.budget,
        ),
    )


def parse_drive_arguments(arguments: list[str], run_name: str) -> DriveArguments:
    """Reads the arguments of ``bowl drive``. Raises ``ValueError`` with a message for the person."""
    parser = _launch_parser("bowl drive", run_name)
    parser.add_argument("--request", type=Path, required=True, help="the request to follow")
    parser.add_argument("--place", type=Path, help="the published bowlbuster that places landings")
    parser.add_argument("--recordings", type=Path, help="the folder a landing's recipes are under")
    found = parser.parse_args(arguments)
    return DriveArguments(**vars(_launch(found)), request=found.request, place=found.place, recordings=found.recordings)


@dataclass(frozen=True)
class QueueArguments:
    """What ``bowl queue`` was asked to do.

    Attributes:
        store: The store's folder.
        instance: The instance's name, which its claims carry.
        xemu: The emulator to start (``--xemu``, or else ``BOWL_XEMU``), or ``None`` when attaching to a running one.
        config: The emulator's configuration file, or ``None`` for its default.
        port: The port of the emulator's debugger stub.
        attach: Whether to attach to a running emulator instead of starting one.
        liveness: How long play may stall before it is a hang, in seconds.
        place: The published copy of ``bowlbuster`` that places landings, which a landing needs.
        recordings: The folder a landing's recipes are under, which a landing needs.
        stall: How long without progress makes a ``stall`` line in the progress stream, in seconds.
    """

    store: Path
    instance: str
    xemu: Path | None
    config: Path | None
    port: int
    attach: bool
    liveness: float
    place: Path | None
    recordings: Path | None
    stall: float


def parse_queue_arguments(arguments: list[str]) -> QueueArguments:
    """Reads the arguments of ``bowl queue``. Raises ``ValueError`` with a message for the person."""
    parser = _Parser(prog="bowl queue", add_help=False)
    parser.add_argument("--store", type=Path, required=True, help="the store's folder")
    parser.add_argument("--instance", required=True, help="the instance's name")
    parser.add_argument("--xemu", type=Path, help="the emulator to start")
    parser.add_argument("--config", type=Path, help="the emulator's configuration file")
    parser.add_argument("--port", type=int, default=1234)
    parser.add_argument("--attach", type=int, metavar="PORT", help="attach to a running emulator's stub")
    parser.add_argument("--liveness", type=float, default=5.0)
    parser.add_argument("--place", type=Path, help="the published bowlbuster that places landings")
    parser.add_argument("--recordings", type=Path, help="the folder a landing's recipes are under")
    parser.add_argument("--stall", type=float, default=600.0, help="seconds without progress before a stall line")
    found = parser.parse_args(arguments)
    if not found.store.is_absolute():
        raise ValueError(f"--store must be an absolute path, got {found.store}")
    xemu, port, attach = _emulator(found)
    return QueueArguments(
        store=found.store,
        instance=found.instance,
        xemu=xemu,
        config=found.config,
        port=port,
        attach=attach,
        liveness=found.liveness,
        place=found.place,
        recordings=found.recordings,
        stall=found.stall,
    )
