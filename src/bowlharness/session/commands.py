"""The arguments of the ``bowl`` console commands, parsed without gdb."""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from bowlharness.recording.recorder import Options


@dataclass(frozen=True)
class RecordArguments:
    """What ``bowl record`` was asked to do.

    Attributes:
        out: The folder for the session's recordings; it must not exist.
        xemu: The emulator to start, or ``None`` when attaching to a running one.
        config: The emulator's configuration file, or ``None`` for its default.
        port: The port of the emulator's debugger stub.
        attach: Whether to attach to a running emulator instead of starting one.
        options: What to observe.
        liveness: How long play may stall before it is a hang, in seconds.
        name: What the run ids start with.
    """

    out: Path
    xemu: Path | None
    config: Path | None
    port: int
    attach: bool
    options: Options
    liveness: float
    name: str


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


def parse_record_arguments(arguments: list[str], run_name: str) -> RecordArguments:
    """Reads the arguments of ``bowl record``. Raises ``ValueError`` with a message for the person."""
    parser = _Parser(prog="bowl record", add_help=False)
    parser.add_argument("--out", type=Path, required=True, help="a folder that does not exist yet")
    parser.add_argument("--xemu", type=Path, help="the emulator to start")
    parser.add_argument("--config", type=Path, help="the emulator's configuration file")
    parser.add_argument("--port", type=int, default=1234)
    parser.add_argument("--attach", type=int, metavar="PORT", help="attach to a running emulator's stub")
    parser.add_argument("--heap", default="all", help="all, none, or scenes")
    parser.add_argument("--captures", default="none", help="cutoff:all, cutoff:none or cutoff:scenes")
    parser.add_argument("--budget", type=int)
    parser.add_argument("--liveness", type=float, default=5.0)
    parser.add_argument("--name", default=run_name)
    found = parser.parse_args(arguments)

    if not found.out.is_absolute():
        raise ValueError(f"--out must be an absolute path, got {found.out}")
    if found.attach is None and found.xemu is None:
        raise ValueError("give --xemu to start an emulator, or --attach PORT to attach to a running one")
    if found.attach is not None and found.xemu is not None:
        raise ValueError("--xemu and --attach are alternatives")
    return RecordArguments(
        out=found.out,
        xemu=found.xemu,
        config=found.config,
        port=found.attach if found.attach is not None else found.port,
        attach=found.attach is not None,
        options=Options(
            heap_events=scene_selection(found.heap),
            cutoff_captures=scene_selection(found.captures.removeprefix("cutoff:")),
            capture_budget=found.budget,
        ),
        liveness=found.liveness,
        name=found.name,
    )
