"""Starting xemu, checking its setup, and describing it for a recording's manifest."""

import hashlib
import os
import platform
import subprocess
import tomllib
from pathlib import Path
from typing import Any


def default_config() -> Path:
    """Where xemu keeps its configuration unless told otherwise."""
    return Path(os.environ["APPDATA"]) / "xemu" / "xemu" / "xemu.toml"


def load_config(path: Path) -> dict[str, Any]:
    """Reads an xemu configuration file."""
    with path.open("rb") as handle:
        return tomllib.load(handle)


def running_xemu() -> list[str]:
    """The ids of the xemu processes that are running."""
    listing = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq xemu.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True, check=True
    ).stdout
    return [line.split(",")[1].strip('"') for line in listing.splitlines() if line.lower().startswith('"xemu.exe"')]


def preconditions(config: dict[str, Any], running: list[str]) -> list[str]:
    """What stops a recording from starting, as messages; empty when it can.

    Args:
        config: The xemu configuration the run will use.
        running: The xemu processes already running, which would hold the storage image.
    """
    failures = []
    if not config.get("input", {}).get("bindings", {}).get("port1"):
        failures.append("no controller is bound to port 1 in xemu")
    if running:
        image = Path(config.get("sys", {}).get("files", {}).get("hdd_path", "")).name or "the storage image"
        failures.append(f"xemu is already running (process {', '.join(running)}), and holds the storage image {image}")
    return failures


def file_sha256(path: Path) -> str:
    """A file's SHA-256, read in 8 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 23):
            digest.update(chunk)
    return digest.hexdigest()


def parse_banner(text: str) -> dict[str, str]:
    """The version, commit and date xemu prints when it starts."""
    found = {}
    for line in text.splitlines():
        key, _, value = line.partition(": ")
        if key in ("xemu_version", "xemu_commit", "xemu_date"):
            found[key.removeprefix("xemu_")] = value.strip()
    return found


def describe(exe: Path | None, config_path: Path, gdb_version: str) -> dict[str, Any]:
    """What a manifest records of the emulator, its configuration, the disc and the host.

    Without the emulator's executable, which a recording that attaches to a running one may not have, its version
    and hash are left out.
    """
    config = load_config(config_path)
    files = config.get("sys", {}).get("files", {})
    banner = subprocess.run([str(exe), "-version"], capture_output=True, text=True, timeout=30).stderr if exe else ""
    disc, storage = Path(files.get("dvd_path", "")), Path(files.get("hdd_path", ""))
    return {
        "emulator": {
            "name": "xemu",
            **parse_banner(banner),
            **({"executable_sha256": file_sha256(exe)} if exe else {}),
            "config_sha256": file_sha256(config_path),
            "controller": config.get("input", {}).get("bindings", {}).get("port1"),
        },
        "disc": {"image": disc.name, "image_sha256": file_sha256(disc)} if disc.is_file() else {},
        "storage": {"image": storage.name, "bytes": storage.stat().st_size} if storage.is_file() else {},
        "gdb": gdb_version,
        "host": platform.platform(),
    }


def launch_command(exe: Path, config_path: Path, port: int) -> str:
    """The command line that runs xemu held at reset with its debugger stub on ``port``, under ``cmd.exe``."""
    xemu = f'"{exe}" -config_path "{config_path}" -gdb tcp::{port} -S'
    return f'cmd.exe /s /c "{xemu}"'


def launch(exe: Path, config_path: Path, port: int, log: Path) -> subprocess.Popen[bytes]:
    """Starts xemu held at reset with its debugger stub on ``port``, in a console of its own.

    xemu attaches to its parent's console on startup, so the process that starts it must have a console that is not
    gdb's: ``cmd.exe`` gets a new one, with no window, and xemu takes it. Started from gdb directly, xemu would
    share gdb's console, and a Ctrl-C meant for gdb would close it. Its output goes to ``log``. Stop it with
    :func:`stop`.
    """
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    with log.open("wb") as output:
        return subprocess.Popen(
            launch_command(exe, config_path, port), stdout=output, stderr=subprocess.STDOUT, creationflags=flags
        )


def stop(process: subprocess.Popen[bytes]) -> None:
    """Closes the xemu that :func:`launch` started, and the ``cmd.exe`` around it."""
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, check=False)
