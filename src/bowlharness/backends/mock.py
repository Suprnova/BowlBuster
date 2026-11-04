"""A target with no emulator behind it, for testing the harness's logic."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from bowlharness.target import Capability, Handle, Handler, Registers, Stop, TargetError


@dataclass(frozen=True)
class Wait:
    """A step that repeats until the harness has given the guest a button.

    The step repeats as a poll, arriving again each time, until the dword at ``address`` holds all of ``mask`` or the
    guest has polled ``polls`` times, and only then applies ``then``.

    Attributes:
        address: The dword the harness presses into.
        mask: The buttons it must hold.
        polls: How many times the step may repeat before the guest goes on without the press.
        then: The memory that takes effect once the press arrives.
    """

    address: int
    mask: int
    polls: int
    then: Mapping[int, bytes] = field(default_factory=dict)


@dataclass(frozen=True)
class Step:
    """One point of a scripted guest's execution.

    Attributes:
        pc: The instruction the guest is at.
        registers: The registers the guest presents there.
        memory: Bytes that take effect in guest memory on arriving, by address.
        written: The address the instruction writes, if any.
        seconds: How long the guest runs before arriving.
        wait: What the step waits for before the guest goes on, if anything.
    """

    pc: int
    registers: Registers = field(default_factory=dict)
    memory: Mapping[int, bytes] = field(default_factory=dict)
    written: int | None = None
    seconds: float = 0.0
    wait: Wait | None = None


@dataclass
class _Point:
    address: int
    length: int | None
    handler: Handler


class MockTarget:
    """Plays a scripted guest, stopping only at the addresses a test armed.

    Every write the harness makes is kept in :attr:`writes`, and the address of the stop it was made at in
    :attr:`write_stops`, at the same index.
    """

    capabilities = frozenset(Capability) - {Capability.SAVED_STATES}

    def __init__(self, script: Sequence[Step], memory: Mapping[int, bytes] | None = None) -> None:
        self._script = script
        self._position = 0
        self._memory: dict[int, int] = {}
        for address, data in (memory or {}).items():
            self._store(address, data)
        self._registers: Registers = {}
        self._points: dict[Handle, _Point] = {}
        self._next_handle = 0
        self._interrupted = False
        self.writes: list[tuple[int, bytes]] = []
        self.write_stops: list[int] = []
        self._pc = 0
        self.resets = 0

    def set_breakpoint(self, address: int, handler: Handler) -> Handle:
        return self._add(_Point(address, None, handler))

    def set_watchpoint(self, address: int, length: int, handler: Handler) -> Handle:
        return self._add(_Point(address, length, handler))

    def clear(self, handle: Handle) -> None:
        del self._points[handle]

    def read(self, address: int, length: int) -> bytes:
        try:
            return bytes(self._memory[a] for a in range(address, address + length))
        except KeyError as error:
            raise TargetError(f"cannot read {length} bytes at {address:#x}") from error

    def registers(self) -> Registers:
        return self._registers

    def write(self, address: int, data: bytes) -> None:
        self.writes.append((address, data))
        self.write_stops.append(self._pc)
        self._store(address, data)

    def dump(self, address: int, length: int, path: Path) -> None:
        path.write_bytes(self.read(address, length))

    def interrupt(self) -> None:
        self._interrupted = True

    def run(self, timeout: float | None = None) -> bool:
        self._interrupted = False
        elapsed = 0.0
        while not self._interrupted and self._position < len(self._script):
            step = self._script[self._position]
            self._position += 1
            elapsed += step.seconds
            fired = self._arrive(step)
            if step.wait:
                fired |= self._wait(step, step.wait)
            if timeout is not None and elapsed >= timeout and not self._interrupted:
                return True
            if fired:
                elapsed = 0.0
        return False

    def reset(self) -> None:
        self.resets += 1
        self._position = 0
        self._memory.clear()

    def _add(self, point: _Point) -> Handle:
        handle = self._next_handle
        self._next_handle += 1
        self._points[handle] = point
        return handle

    def _store(self, address: int, data: bytes) -> None:
        self._memory.update(enumerate(data, address))

    def _wait(self, step: Step, wait: Wait) -> bool:
        """Repeats a step until its press arrives or its polls run out; returns whether any handler ran."""
        fired = False
        for repeat in range(wait.polls + 1):
            if int.from_bytes(self.read(wait.address, 4), "little") & wait.mask == wait.mask:
                self._store_all(wait.then)
                break
            if repeat == wait.polls or self._interrupted:
                break
            fired |= self._arrive(step)
        return fired

    def _store_all(self, memory: Mapping[int, bytes]) -> None:
        for address, data in memory.items():
            self._store(address, data)

    def _arrive(self, step: Step) -> bool:
        """Applies a step and calls the handlers it reaches; returns whether any ran."""
        self._pc = step.pc
        self._registers = step.registers
        for address, data in step.memory.items():
            self._store(address, data)
        fired = False
        for point in list(self._points.values()):
            if point.length is None:
                if point.address == step.pc:
                    point.handler(Stop(step.pc))
                    fired = True
            elif step.written is not None and point.address <= step.written < point.address + point.length:
                point.handler(Stop(step.pc, step.written))
                fired = True
        return fired
