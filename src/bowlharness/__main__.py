"""Starts gdb with the harness loaded: ``python -m bowlharness [--gdb <gdb>] <bowl command> [arguments]``.

``python -m bowlharness saves ...`` manages the save library instead, with no gdb (:mod:`bowlharness.saves.commands`).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent


def find_gdb(named: str | None = None) -> str:
    """Finds the gdb to host the harness: the one ``--gdb`` names, else ``BOWL_GDB``, else the one on ``PATH``."""
    if named:
        return named
    if configured := os.environ.get("BOWL_GDB"):
        return configured
    if found := shutil.which("gdb"):
        return found
    raise SystemExit("gdb not found: give --gdb <gdb>, set BOWL_GDB to it, or put a gdb with Python scripting on PATH")


def split_gdb(arguments: list[str]) -> tuple[str | None, list[str]]:
    """Takes ``--gdb <gdb>`` out of the arguments, wherever it is: the gdb it names, and the bowl command's."""
    if "--gdb" not in arguments:
        return None, arguments
    index = arguments.index("--gdb")
    if index + 1 == len(arguments):
        raise SystemExit("--gdb needs the path of a gdb")
    return arguments[index + 1], arguments[:index] + arguments[index + 2 :]


def gdb_command(gdb: str, bowl_args: list[str]) -> list[str]:
    """The command line that starts ``gdb`` with the harness imported and ``bowl_args`` run as a ``bowl`` command."""
    path_setup = f"python import sys; sys.path.insert(0, {SOURCE_ROOT.as_posix()!r})"
    quoted = " ".join(f'"{arg.replace(chr(92), "/")}"' for arg in bowl_args)
    batch = ["-batch"] if bowl_args[:1] == ["smoke"] else []
    quiet = ["-iex", "set pagination off", "-iex", "set confirm off"]
    return [
        gdb,
        "-q",
        *batch,
        *quiet,
        "-iex",
        path_setup,
        "-ex",
        "python import bowlharness.backends.gdbhost",
        "-ex",
        f"bowl {quoted}",
    ]


def run_gdb(command: list[str]) -> int:
    """Runs gdb to its end and returns its exit code.

    A person's Ctrl-C reaches this process as well as gdb, and it is gdb's: it pauses the run, so it ends no wait.
    """
    process = subprocess.Popen(command)
    while True:
        try:
            return process.wait()
        except KeyboardInterrupt:
            continue


def main() -> int:
    named, arguments = split_gdb(sys.argv[1:])
    if not arguments:
        raise SystemExit("usage: python -m bowlharness [--gdb <gdb>] <bowl command> [arguments]")
    if arguments[0] == "saves":
        from bowlharness.saves.commands import main as saves

        return saves(arguments[1:])
    return run_gdb(gdb_command(find_gdb(named), arguments))


if __name__ == "__main__":
    raise SystemExit(main())
