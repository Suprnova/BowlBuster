"""Where a landing goes: asked of ``bowlbuster place``, the one source of the stale pointer ``S``."""

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

PLACED, NO_BLOCK, UNPLACEABLE = 0, 65, 66
TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class Placed:
    """A placement: the pointer to write, and the cursor and depth the replay has at the recipe's cutoff.

    Attributes:
        s: The stale pointer to write.
        top: The cursor and depth at the recipe's cutoff, or ``None`` when it has no cutoff.
    """

    s: int
    top: tuple[int, int] | None


@dataclass(frozen=True)
class NotPlaced:
    """No placement, for the reason ``bowlbuster place`` gave."""

    reason: str


class PlacementFault(Exception):
    """The placement tool failed: a usage error, an internal error, or a tool that couldn't be run."""


@dataclass(frozen=True)
class PlacementTool:
    """The published copy of ``bowlbuster`` a session pins.

    Attributes:
        path: Where it is.
        build: What its ``--version`` printed.
        sha256: The hash of the executable.
    """

    path: Path
    build: str
    sha256: str


class Placer(Protocol):
    """Places a landing test's stale pointer.

    Attributes:
        tool: The placement tool behind it, which a result records; ``None`` for one that runs none.
    """

    tool: PlacementTool | None

    def place(
        self, recipe: Path, segment: int, load: int, heap: dict[str, Any], op: int, delta: int, folder: Path
    ) -> Placed | NotPlaced:
        """Places block ``op`` of the recipe's load, replayed from ``heap``, plus ``delta``.

        Args:
            recipe: The recipe recording's folder.
            segment: The segment that holds the load.
            load: The load's counter.
            heap: The live heap, spelled as a ``scene_init`` event's ``heap``.
            op: The block's position in the load's request list.
            delta: The signed byte offset of the pointer in the block.
            folder: Where the call may leave its files, such as the run's recording.

        Raises:
            PlacementFault: The placer itself failed, which is never a landing that can't be placed.
        """
        ...


class ToolPlacer:
    """A :class:`Placer` that runs a pinned copy of ``bowlbuster place``.

    The heap is written to ``place-heap-<op>.json`` in the call's folder. Exit 0 is a placement, 65 and 66 are no
    placement, and anything else is a :class:`PlacementFault`.

    Args:
        tool: The copy to run.
    """

    def __init__(self, tool: PlacementTool) -> None:
        self.tool = tool

    @classmethod
    def pin(cls, executable: Path) -> ToolPlacer:
        """Pins ``executable`` for a session: runs its ``--version`` once and hashes the file.

        Raises:
            PlacementFault: It can't be run, or its ``--version`` fails.
        """
        try:
            found = subprocess.run(
                [str(executable), "--version"], capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PlacementFault(f"cannot run the placement tool {executable}: {error}") from error
        if found.returncode != 0:
            raise PlacementFault(f"{executable} --version exited {found.returncode}: {found.stderr.strip()}")
        digest = hashlib.sha256(executable.read_bytes()).hexdigest()
        return cls(PlacementTool(executable, found.stdout.strip(), digest))

    def place(
        self, recipe: Path, segment: int, load: int, heap: dict[str, Any], op: int, delta: int, folder: Path
    ) -> Placed | NotPlaced:
        heap_file = folder / f"place-heap-{op}.json"
        heap_file.write_text(json.dumps(heap), encoding="utf-8", newline="\n")
        command = [
            *(str(self.tool.path), "place", "--recording", str(recipe), "--segment", str(segment)),
            *("--load", str(load), "--heap", str(heap_file), "--op", str(op), "--delta", str(delta), "--top"),
        ]
        try:
            found = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PlacementFault(f"cannot run the placement tool: {error}") from error
        if found.returncode in (NO_BLOCK, UNPLACEABLE):
            return NotPlaced(found.stderr.strip())
        if found.returncode != PLACED:
            raise PlacementFault(f"place exited {found.returncode}: {found.stderr.strip()}")
        return parse_placed(found.stdout)


def parse_placed(stdout: str) -> Placed:
    """Reads what ``bowlbuster place --top`` printed: ``0x<S>``, then ``0x<cursor> <depth>`` when there is a cutoff.

    Raises:
        PlacementFault: The output isn't in that form.
    """
    lines = stdout.split()
    try:
        s = int(lines[0], 16)
        top = (int(lines[1], 16), int(lines[2])) if len(lines) == 3 else None
    except (IndexError, ValueError) as error:
        raise PlacementFault(f"place printed what it never prints: {stdout!r}") from error
    if len(lines) not in (1, 3):
        raise PlacementFault(f"place printed what it never prints: {stdout!r}")
    return Placed(s, top)
