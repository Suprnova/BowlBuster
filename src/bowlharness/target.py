"""The interface between the harness and an emulator, and the types that cross it."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

type Registers = Mapping[str, int]
type Handle = int
type Handler = Callable[[Stop], None]


class Capability(StrEnum):
    """An operation a backend may or may not support."""

    BREAKPOINTS = "breakpoints"
    WATCHPOINTS = "watchpoints"
    MEMORY_WRITE = "memory_write"
    BULK_DUMP = "bulk_dump"
    RESET = "reset"
    SAVED_STATES = "saved_states"


class TargetError(Exception):
    """A target operation failed, such as a read the emulator refused."""


@dataclass(frozen=True)
class Stop:
    """Why the guest stopped.

    Attributes:
        pc: The guest address of the instruction the guest stopped at.
        address: The guest address that was written, for a watchpoint stop; ``None`` for a breakpoint. A backend that
            cannot say which byte was written reports the start of the watched range.
    """

    pc: int
    address: int | None = None


class Target(Protocol):
    """An emulator the harness drives. Addresses are guest virtual addresses.

    A handler runs while the guest is stopped, and the guest continues when it returns, unless it called
    :meth:`interrupt`.
    """

    @property
    def capabilities(self) -> frozenset[Capability]:
        """The operations this backend supports."""
        ...

    def set_breakpoint(self, address: int, handler: Handler) -> Handle:
        """Calls ``handler`` each time the guest is about to execute the instruction at ``address``."""
        ...

    def set_watchpoint(self, address: int, length: int, handler: Handler) -> Handle:
        """Calls ``handler`` each time the guest writes any of the ``length`` bytes at ``address``."""
        ...

    def clear(self, handle: Handle) -> None:
        """Removes a breakpoint or watchpoint."""
        ...

    def read(self, address: int, length: int) -> bytes:
        """Reads guest memory. Raises :class:`TargetError` when the emulator refuses the read."""
        ...

    def registers(self) -> Registers:
        """Reads the guest's registers by name."""
        ...

    def write(self, address: int, data: bytes) -> None:
        """Writes guest memory."""
        ...

    def dump(self, address: int, length: int, path: Path) -> None:
        """Saves a range of guest memory to a file, much faster than :meth:`read` for large ranges."""
        ...

    def interrupt(self) -> None:
        """Stops the guest, making :meth:`run` return."""
        ...

    def run(self, timeout: float | None = None) -> bool:
        """Continues the guest until it is interrupted or ends.

        Args:
            timeout: Seconds the guest may run without a stop reaching a handler. After that long a stretch, the guest
                is stopped. A guest that keeps stopping at points is making progress and is never stopped by it.

        Returns:
            Whether the guest was stopped because the timeout elapsed.
        """
        ...

    def reset(self) -> None:
        """Resets the machine."""
        ...
