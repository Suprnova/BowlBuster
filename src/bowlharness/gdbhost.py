"""The harness hosted inside gdb: a :class:`~bowlharness.target.Target` over gdb's Python API and the ``bowl`` commands.

This is the only module that imports ``gdb``. gdb imports it with ``python import bowlharness.gdbhost``, which
registers the ``bowl`` command group; ``python -m bowlharness`` does that.
"""

import threading
from collections.abc import Callable, Sequence
from pathlib import Path

import gdb

from bowlharness.target import Capability, Handle, Handler, Registers, Stop, TargetError


class _Point(gdb.Breakpoint):
    def __init__(self, spec: str, kind: int, handler: Handler, target: GdbTarget, address: int | None) -> None:
        super().__init__(spec, kind, gdb.WP_WRITE, internal=True)
        self._handler = handler
        self._target = target
        self._address = address

    def stop(self) -> bool:
        self._handler(Stop(int(gdb.selected_frame().pc()), self._address))
        return self._target.take_interrupt()


class GdbTarget:
    """Drives the guest through gdb's remote connection to xemu's stub.

    A watchpoint's :attr:`Stop.address <bowlharness.target.Stop.address>` is the start of the watched range, since gdb
    does not say which byte was written.

    Args:
        register_names: The registers :meth:`registers` reads.
    """

    capabilities = frozenset(Capability) - {Capability.SAVED_STATES}

    def __init__(self, register_names: Sequence[str] = ()) -> None:
        self._register_names = register_names
        self._points: dict[Handle, _Point] = {}
        self._next_handle = 0
        self._interrupted = False

    def set_breakpoint(self, address: int, handler: Handler) -> Handle:
        return self._add(_Point(f"*{address:#x}", gdb.BP_BREAKPOINT, handler, self, None))

    def set_watchpoint(self, address: int, length: int, handler: Handler) -> Handle:
        spec = f"*(unsigned char (*)[{length}]) {address:#x}"
        return self._add(_Point(spec, gdb.BP_WATCHPOINT, handler, self, address))

    def clear(self, handle: Handle) -> None:
        point = self._points.pop(handle)
        point.enabled = False
        gdb.post_event(point.delete)

    def read(self, address: int, length: int) -> bytes:
        try:
            return bytes(gdb.selected_inferior().read_memory(address, length))
        except gdb.MemoryError as error:
            raise TargetError(str(error)) from error

    def registers(self) -> Registers:
        frame = gdb.selected_frame()
        return {name: int(frame.read_register(name)) & 0xFFFFFFFF for name in self._register_names}

    def write(self, address: int, data: bytes) -> None:
        try:
            gdb.selected_inferior().write_memory(address, data)
        except gdb.MemoryError as error:
            raise TargetError(str(error)) from error

    def dump(self, address: int, length: int, path: Path) -> None:
        try:
            gdb.execute(f"monitor memsave {address:#x} {length:#x} {path.as_posix()}")
        except gdb.error as error:
            raise TargetError(str(error)) from error

    def interrupt(self) -> None:
        self._interrupted = True

    def run(self, timeout: float | None = None) -> bool:
        self._interrupted = False
        expired = threading.Event()
        timer = threading.Timer(timeout, lambda: self._expire(expired)) if timeout is not None else None
        if timer:
            timer.start()
        try:
            gdb.execute("continue")
        finally:
            if timer:
                timer.cancel()
        return expired.is_set()

    @staticmethod
    def _expire(expired: threading.Event) -> None:
        expired.set()
        gdb.post_event(lambda: gdb.execute("interrupt"))

    def reset(self) -> None:
        gdb.execute("monitor system_reset")

    def take_interrupt(self) -> bool:
        """Whether a handler asked to stop the guest; the request is consumed."""
        interrupted, self._interrupted = self._interrupted, False
        return interrupted

    def _add(self, point: _Point) -> Handle:
        handle = self._next_handle
        self._next_handle += 1
        self._points[handle] = point
        return handle


def _smoke(args: Sequence[str]) -> None:
    port, header, breakpoint_, start, length, out = args
    target = GdbTarget()
    gdb.execute(f"target remote :{port}")
    stops: list[Stop] = []

    def hit(stop: Stop) -> None:
        stops.append(stop)
        target.interrupt()

    target.set_breakpoint(int(breakpoint_, 0), hit)
    target.run()
    print(f"stopped: {stops}")
    print(f"magic: {target.read(int(header, 0), 4)!r}")
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    target.dump(int(start, 0), int(length, 0), path)
    print(f"dumped: {path.stat().st_size} bytes")


def _unavailable(name: str) -> Callable[[Sequence[str]], None]:
    def command(_: Sequence[str]) -> None:
        raise gdb.GdbError(f"bowl {name} is not available yet")

    return command


_COMMANDS: dict[str, Callable[[Sequence[str]], None]] = {
    "smoke": _smoke,
    **{name: _unavailable(name) for name in ("record", "capture", "read", "resume", "stop")},
}


class _Bowl(gdb.Command):
    """The harness's commands: bowl smoke|record|capture|read|resume|stop."""

    def __init__(self) -> None:
        super().__init__("bowl", gdb.COMMAND_USER)

    def invoke(self, argument: str, from_tty: bool) -> None:
        name, *args = gdb.string_to_argv(argument) or [""]
        if (command := _COMMANDS.get(name)) is None:
            raise gdb.GdbError(f"usage: bowl {'|'.join(_COMMANDS)}")
        command(args)


_Bowl()
