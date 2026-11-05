"""Starts gdb with the harness loaded: ``python -m bowlharness [--gdb <gdb>] <bowl command> [arguments]``."""

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


def main() -> int:
    named, arguments = split_gdb(sys.argv[1:])
    if not arguments:
        raise SystemExit("usage: python -m bowlharness [--gdb <gdb>] <bowl command> [arguments]")
    return subprocess.call(gdb_command(find_gdb(named), arguments))


if __name__ == "__main__":
    raise SystemExit(main())
