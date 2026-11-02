"""Starts gdb with the harness loaded: ``python -m bowlharness <bowl command> [arguments]``."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_GDB = Path(r"C:\msys64\ucrt64\bin\gdb.exe")
SOURCE_ROOT = Path(__file__).resolve().parent.parent


def find_gdb() -> str:
    """Finds the gdb to host the harness: ``BOWL_GDB``, then MSYS2's, then the one on ``PATH``."""
    if configured := os.environ.get("BOWL_GDB"):
        return configured
    if DEFAULT_GDB.exists():
        return str(DEFAULT_GDB)
    if found := shutil.which("gdb"):
        return found
    raise SystemExit("gdb not found: install MSYS2's ucrt64 gdb or set BOWL_GDB")


def gdb_command(gdb: str, bowl_args: list[str]) -> list[str]:
    """The command line that starts ``gdb`` with the harness imported and ``bowl_args`` run as a ``bowl`` command."""
    path_setup = f"python import sys; sys.path.insert(0, {SOURCE_ROOT.as_posix()!r})"
    quoted = " ".join(f'"{arg}"' for arg in bowl_args)
    batch = ["-batch"] if bowl_args[:1] == ["smoke"] else []
    return [gdb, "-q", *batch, "-iex", path_setup, "-ex", "python import bowlharness.gdbhost", "-ex", f"bowl {quoted}"]


def main() -> int:
    if not sys.argv[1:]:
        raise SystemExit("usage: python -m bowlharness <bowl command> [arguments]")
    return subprocess.call(gdb_command(find_gdb(), sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
