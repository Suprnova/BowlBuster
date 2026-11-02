"""Detecting a crashed or hung guest."""

import struct
from typing import TYPE_CHECKING, Any

from bowlharness.observe import Read, u32
from bowlharness.profiles.profile import PlatformProfile
from bowlharness.target import TargetError

if TYPE_CHECKING:
    from bowlharness.recorder import Recorder

BUGCHECK_KINDS = ("KeBugCheck", "KeBugCheckEx")


def kernel_export(read: Read, base: int, ordinal: int) -> int:
    """The address of a kernel export, found by ordinal in the export table of the PE image at ``base``."""
    header = base + u32(read, base + 0x3C)
    directory = base + u32(read, header + 0x78)
    first_ordinal = u32(read, directory + 0x10)
    count = u32(read, directory + 0x14)
    functions = u32(read, directory + 0x1C)
    index = ordinal - first_ordinal
    if not 0 <= index < count:
        raise ValueError(f"the kernel exports no ordinal {ordinal}")
    return base + u32(read, base + functions + 4 * index)


def bugcheck_addresses(read: Read, profile: PlatformProfile) -> dict[str, int]:
    """Where each bugcheck function is, by name."""
    return {
        kind: kernel_export(read, profile.kernel_base, ordinal)
        for kind, ordinal in zip(BUGCHECK_KINDS, profile.bugcheck_ordinals, strict=True)
    }


def _follows_a_call(before: bytes) -> bool:
    """Whether the six bytes before an address end with a call instruction."""
    return (
        before[1] == 0xE8
        or before[:2] == bytes([0xFF, 0x15])
        or before[0] == 0xFF
        and 0x90 <= before[1] <= 0x97
        or before[3] == 0xFF
        and 0x50 <= before[4] <= 0x57
        or before[4] == 0xFF
        and (0x10 <= before[5] <= 0x17 or 0xD0 <= before[5] <= 0xD7)
    )


def return_addresses(read: Read, words: tuple[int, ...], code: tuple[int, int]) -> list[int]:
    """The stack words that are return addresses: inside the game's code, and right after a call instruction."""
    found = []
    for word in words:
        if not code[0] + 6 <= word < code[1]:
            continue
        try:
            if _follows_a_call(read(word - 6, 6)):
                found.append(word)
        except TargetError:
            continue
    return found


def crash_record(
    kind: str,
    words: tuple[int, ...],
    registers: dict[str, int],
    stack: tuple[int, ...],
    read: Read,
    profile: PlatformProfile,
) -> dict[str, Any]:
    """The record of a bugcheck: ``words`` are the return address, the code and the parameters it was called with.

    A bugcheck for an unhandled exception also carries the faulting instruction and, for an access violation, the
    address accessed and whether it was read or written.
    """
    code, params = words[1], list(words[2:])
    crash = profile.crash
    record: dict[str, Any] = {
        "kind": kind,
        "code": code,
        "params": params,
        "arch": profile.arch,
        "registers": registers,
        "stack": list(stack[: profile.crash.stack_words]),
        "return_addresses": return_addresses(read, stack, profile.code),
    }
    if code == crash.exception_bugcheck and len(params) == 4:
        record["instruction"] = params[crash.instruction_param]
        if params[0] == crash.access_violation:
            record["access"] = "write" if params[crash.access_param] == 1 else "read"
            record["accessed"] = params[crash.address_param]
    return record


def stack_words(read: Read, esp: int, count: int) -> tuple[int, ...]:
    """Up to ``count`` words on the stack from the stack pointer, fewer if the stack ends sooner."""
    while count:
        try:
            return struct.unpack(f"<{count}I", read(esp, 4 * count))
        except TargetError:
            count //= 2
    return ()


class Watchdog:
    """Declares a hang when the guest shows no progress for longer than its liveness window.

    Progress is the frame counter advancing or the recorder logging any event, since a load runs no frames. The
    session calls :meth:`check` each time the guest has run for ``liveness`` seconds and been stopped; a stall
    during a load is given ``load_limit`` seconds, and nothing counts while the guest is held for a person.

    Args:
        recorder: The recorder to report a hang to.
        liveness: How often the guest is checked, and how long play may stall, in seconds.
        load_limit: How long a load may stall, in seconds.
    """

    def __init__(self, recorder: Recorder, liveness: float = 5.0, load_limit: float = 120.0) -> None:
        self._recorder = recorder
        self.liveness = liveness
        self._load_limit = load_limit
        self._held = False
        self._seen: tuple[int, int] | None = None
        self._stalled = 0.0

    def hold(self) -> None:
        """Stops counting, for a guest held for a person."""
        self._held = True

    def release(self) -> None:
        """Starts counting again from the next check."""
        self._held = False
        self._seen = None
        self._stalled = 0.0

    def check(self) -> bool:
        """Looks for progress since the last check, and reports a hang if there has been none for too long."""
        if self._held or self._recorder.ended:
            return False
        seen = (self._recorder.frame(), self._recorder.event_count)
        self._stalled = self._stalled + self.liveness if seen == self._seen else 0.0
        self._seen = seen
        limit = self._load_limit if self._recorder.loading else self.liveness
        if self._stalled < limit:
            return False
        self._recorder.hang(self._stalled, seen[0])
        return True
