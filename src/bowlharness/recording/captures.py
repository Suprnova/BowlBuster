"""Takes captures: the game's static memory and heap 0 at one moment, with what is needed to read them."""

import json
from pathlib import Path
from typing import Any

from bowlharness.observe import bowl_statics, heap0_state, tag, u32
from bowlharness.profiles.profile import PlatformProfile
from bowlharness.target import Target

MARKER = "complete"


def take_capture(
    target: Target, profile: PlatformProfile, directory: Path, capture_id: str, trigger: str, label: str | None
) -> dict[str, Any]:
    """Writes a capture of the stopped guest and returns its manifest.

    The capture's directory holds the static range, heap 0 up to its cursor, the manifest, and last of all the
    completion marker, so a reader that finds no marker finds no capture.
    """
    heap = heap0_state(target.read, profile.heap)
    cursor = heap["states"][heap["depth"]]["cursor"]
    heap0 = (profile.heap.heap0_base, cursor - profile.heap.heap0_base)
    if not 0 <= heap0[1] <= profile.heap_block_size:
        raise ValueError(f"heap 0's cursor {cursor:#x} is outside the heap")

    manifest = {
        "id": capture_id,
        "trigger": trigger,
        "label": label,
        "platform": profile.name,
        "arch": profile.arch,
        "counter": u32(target.read, profile.globals.scene_counter),
        "scene": tag(u32(target.read, profile.globals.current_scene)),
        "registers": dict(target.registers()),
        "bowl": bowl_statics(target.read, profile.globals),
        "heap": heap,
        "ranges": {
            "static": {
                "address": profile.static_range[0],
                "length": profile.static_range[1] - profile.static_range[0],
                "file": "data.bin",
            },
            "heap0": {"address": heap0[0], "length": heap0[1], "file": "heap0.bin"},
        },
    }

    directory.mkdir(parents=True)
    for spec in manifest["ranges"].values():
        target.dump(spec["address"], spec["length"], directory / spec["file"])
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    (directory / MARKER).write_bytes(b"")
    return manifest
