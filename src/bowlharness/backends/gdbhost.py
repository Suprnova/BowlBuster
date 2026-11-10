"""The harness hosted inside gdb: a :class:`~bowlharness.target.Target` over gdb's Python API and the ``bowl`` commands.

This is the only module that imports ``gdb``. gdb imports it with ``python import bowlharness.backends.gdbhost``, which
registers the ``bowl`` command group; ``python -m bowlharness`` does that.
"""

import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import Any

import gdb

from bowlharness.backends.emulator import Emulator
from bowlharness.backends.xemu import (
    default_config,
    derived_config,
    describe,
    launch,
    load_config,
    preconditions,
    running_xemu,
    stop,
)
from bowlharness.driving.landing import check_recipe
from bowlharness.driving.placer import PlacementFault, ToolPlacer
from bowlharness.driving.request import LandingTest, Request, check_save, read_request
from bowlharness.profiles import XBOX_NTSC_U
from bowlharness.saves.library import Library
from bowlharness.saves.storage import prepare
from bowlharness.session.commands import (
    LaunchArguments,
    parse_drive_arguments,
    parse_queue_arguments,
    parse_record_arguments,
)
from bowlharness.session.driven import DrivenSession, pin_placer
from bowlharness.session.session import ENDED, PAUSED, Session
from bowlharness.store.queue import ProgressStream, Queue
from bowlharness.store.store import Claim, Store
from bowlharness.target import Capability, Handle, Handler, Registers, Stop, TargetError


def _register(name: str) -> int:
    """A register of the stopped guest, read without building gdb's frame, which costs code reads at every stop."""
    return int(gdb.parse_and_eval(f"${name}")) & 0xFFFFFFFF


class _Point(gdb.Breakpoint):
    def __init__(
        self, spec: str, kind: int, handler: Handler, target: GdbTarget, *, pc: int | None, watched: int | None
    ) -> None:
        super().__init__(spec, kind, gdb.WP_WRITE, internal=True)
        self._handler = handler
        self._target = target
        self._pc = pc
        self._watched = watched

    def stop(self) -> bool:
        self._target.stops += 1
        self._handler(Stop(_register("pc") if self._pc is None else self._pc, self._watched))
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
        self.stops = 0

    def set_breakpoint(self, address: int, handler: Handler) -> Handle:
        return self._add(_Point(f"*{address:#x}", gdb.BP_BREAKPOINT, handler, self, pc=address, watched=None))

    def set_watchpoint(self, address: int, length: int, handler: Handler) -> Handle:
        spec = f"*(unsigned char (*)[{length}]) {address:#x}"
        return self._add(_Point(spec, gdb.BP_WATCHPOINT, handler, self, pc=None, watched=address))

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
        return {name: _register(name) for name in self._register_names}

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
        timers: list[threading.Timer] = []
        if timeout is not None:
            self._watch_for_silence(timeout, expired, timers)
        try:
            gdb.execute("continue", to_string=True)
        except KeyboardInterrupt:
            self._stop_running_guest()
        except gdb.error as error:
            raise TargetError(str(error)) from error
        finally:
            for timer in timers:
                timer.cancel()
        return expired.is_set()

    @staticmethod
    def _stop_running_guest() -> None:
        """Makes sure the guest is stopped after a person's Ctrl-C was raised as an exception instead of a stop."""
        with suppress(gdb.error):
            gdb.execute("interrupt", to_string=True)

    def _watch_for_silence(self, timeout: float, expired: threading.Event, timers: list[threading.Timer]) -> None:
        """Interrupts the guest after ``timeout`` seconds with no stop reaching a handler.

        Interrupting a guest that keeps stopping at breakpoints would often land on a breakpoint's own address, and gdb
        resumes from there by stepping over it, which loses that stop.
        """
        seen = self.stops

        def check() -> None:
            if self.stops != seen:
                self._watch_for_silence(timeout, expired, timers)
                return
            expired.set()
            gdb.post_event(lambda: gdb.execute("interrupt", to_string=True))

        timer = threading.Timer(timeout, check)
        timers.append(timer)
        timer.start()

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


_session: Session | None = None
_session_out: Path | None = None
_queue: Queue | None = None
_queue_end: Callable[[], None] | None = None


def _connect(port: int, process: subprocess.Popen[bytes] | None) -> None:
    """Connects to the emulator's stub, retrying while a started emulator opens it."""
    for _ in range(120):
        if process is not None and process.poll() is not None:
            raise gdb.GdbError(f"xemu exited with code {process.returncode}")
        try:
            gdb.execute(f"target remote :{port}", to_string=True)
            return
        except gdb.error:
            time.sleep(0.5)
    raise gdb.GdbError(f"could not connect to an emulator on port {port}")


def _tell(state: str) -> None:
    if state == PAUSED:
        print(
            "paused: bowl capture <label> | bowl read <address> <length> | bowl press <button> [<polls>] | "
            "bowl resume | bowl stop"
        )
    else:
        print(f"ended: {_session.recordings if _session else 0} recording(s) in {_session_out}")
        if isinstance(_session, DrivenSession) and _session.result:
            print(f"route {_session.result}")
        if isinstance(_session, DrivenSession) and (written := _session.written):
            print(f"result: {written.outcome}" + (f" ({written.cause})" if written.cause else ""))


DRIVE_INSTANCE = "drive"


class _Xemu:
    """The xemu a session or a queue runs on: started by the harness, or attached to when ``xemu`` is ``None``."""

    def __init__(self, xemu: Path | None, port: int, log: Path) -> None:
        self._xemu = xemu
        self._port = port
        self._log = log
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def restartable(self) -> bool:
        return self._xemu is not None

    def start(self, config: Path) -> None:
        if self._xemu is None:
            _connect(self._port, None)
            return
        self._log.parent.mkdir(parents=True, exist_ok=True)
        self._process = launch(self._xemu, config, self._port, self._log)
        _connect(self._port, self._process)
        self.reset()

    def stop(self) -> None:
        if self._process is None:
            return
        with suppress(gdb.error):
            gdb.execute("disconnect", to_string=True)
        stop(self._process)
        self._process.wait(timeout=60)
        self._process = None

    def reset(self) -> None:
        gdb.execute("monitor system_reset", to_string=True)

    def describe(self, config: Path) -> dict[str, Any]:
        return describe(self._xemu, config, gdb.VERSION)

    def running(self) -> list[str]:
        return running_xemu()


def _start_emulator(
    verb: str, xemu: Path | None, config: Path | None, port: int, attach: bool, log: Path
) -> tuple[dict[str, Any], _Xemu]:
    """Starts the emulator, or attaches to a running one, and connects to it; returns what a manifest records of it."""
    config = config or default_config()
    if not attach and (failures := preconditions(load_config(config), running_xemu())):
        raise gdb.GdbError(f"cannot {verb}: " + "; ".join(failures))
    emulator = _Xemu(None if attach else xemu, port, log)
    environment = emulator.describe(config)
    emulator.start(config)
    return environment, emulator


def _launch(
    verb: str, arguments: LaunchArguments, open_session: Callable[[dict[str, Any], Callable[[], None] | None], Session]
) -> None:
    """Starts or attaches to the emulator and runs the session ``open_session`` makes, until it pauses or ends."""
    global _session, _session_out
    if arguments.out.exists():
        raise gdb.GdbError(f"{arguments.out} already exists")
    log = arguments.out.parent / f"{arguments.name}-xemu.log"
    environment, emulator = _start_emulator(
        verb, arguments.xemu, arguments.config, arguments.port, arguments.attach, log
    )
    _session_out = arguments.out
    _session = open_session(environment, emulator.stop if emulator.restartable else None)
    _tell(_session.run())


def _require_no_session() -> None:
    if _session is not None and not _session.ended:
        raise gdb.GdbError("a session is recording, end it with bowl stop")


def _record(args: Sequence[str]) -> None:
    _require_no_session()
    try:
        arguments = parse_record_arguments(list(args), time.strftime("%Y%m%d-%H%M%S"))
    except ValueError as error:
        raise gdb.GdbError(str(error)) from error

    def open_session(environment: dict[str, Any], on_end: Callable[[], None] | None) -> Session:
        print(f"recording to {arguments.out}")
        return Session(
            GdbTarget(XBOX_NTSC_U.registers),
            XBOX_NTSC_U,
            arguments.out,
            arguments.options,
            run_stem=arguments.name,
            environment=environment,
            boot_path="attached" if arguments.attach else "boot",
            liveness=arguments.liveness,
            on_end=on_end,
        )

    _launch("record", arguments, open_session)


def _drive(args: Sequence[str]) -> None:
    _require_no_session()
    try:
        arguments = parse_drive_arguments(list(args), time.strftime("%Y%m%d-%H%M%S"))
        request, request_sha256 = read_request(arguments.request, XBOX_NTSC_U)
        library = Library(arguments.saves) if arguments.saves else None
        check_save(request, library)
        placer = pin_placer(request, arguments.place, arguments.recordings, XBOX_NTSC_U.name)
        save = None
        if request.save is not None and library is not None:
            if arguments.attach:
                raise ValueError("a run that starts from a save needs an emulator the harness starts, not --attach")
            storage = prepare(library, request.save, DRIVE_INSTANCE, running_xemu())
            arguments = replace(arguments, config=derived_config(arguments.config or default_config(), storage.path))
            save = storage.record()
    except (OSError, ValueError) as error:
        raise gdb.GdbError(str(error)) from error
    if placer is not None and placer.tool is not None:
        print(f"placing with {placer.tool.build} ({placer.tool.path})")

    def open_session(environment: dict[str, Any], on_end: Callable[[], None] | None) -> Session:
        print(f"driving {request.request_id} to {arguments.out}")
        return DrivenSession(
            GdbTarget(XBOX_NTSC_U.registers),
            XBOX_NTSC_U,
            arguments.out,
            request,
            request_sha256,
            run_stem=arguments.name,
            environment={**environment, **({"save": save} if save else {})},
            boot_path="attached" if arguments.attach else "boot",
            liveness=arguments.liveness,
            on_end=on_end,
            placer=placer,
            recordings=arguments.recordings,
        )

    _launch("drive", arguments, open_session)


def _live() -> Session:
    if _session is None or _session.ended:
        raise gdb.GdbError("no session is recording, start it with bowl record")
    return _session


def _capture(args: Sequence[str]) -> None:
    label = " ".join(args) or "manual"
    try:
        print(f"capture: {_live().capture(label) or 'refused by the budget'}")
    except RuntimeError as error:
        raise gdb.GdbError(str(error)) from error


def _read(args: Sequence[str]) -> None:
    if len(args) != 2:
        raise gdb.GdbError("usage: bowl read <address> <length>")
    address, length = int(args[0], 0), int(args[1], 0)
    try:
        data = _live().read(address, length)
    except RuntimeError as error:
        raise gdb.GdbError(str(error)) from error
    for offset in range(0, len(data), 16):
        print(f"{address + offset:08x}  {data[offset : offset + 16].hex(' ')}")


def _press(args: Sequence[str]) -> None:
    if not 1 <= len(args) <= 2:
        raise gdb.GdbError("usage: bowl press <button> [<polls>]")
    try:
        _live().press(args[0], int(args[1]) if len(args) == 2 else None)
    except (RuntimeError, ValueError) as error:
        raise gdb.GdbError(str(error)) from error
    print(f"queued: {args[0]}")


def _resume(_: Sequence[str]) -> None:
    session = _live()
    state = session.resume()
    _tell(state)
    if _queue is not None and state == ENDED:
        _finish_queued(session)
        _run_queue()


def _stop(_: Sequence[str]) -> None:
    session = _live()
    session.stop()
    _tell(ENDED)
    if _queue is not None:
        _queue.stop()
        _finish_queued(session)
        _run_queue()


def _queue_command(args: Sequence[str]) -> None:
    global _queue, _queue_end
    _require_no_session()
    try:
        arguments = parse_queue_arguments(list(args))
        store = Store(arguments.store, arguments.instance)
        placer = ToolPlacer.pin(arguments.place) if arguments.place else None
        library = Library(arguments.saves) if arguments.saves else None
    except (OSError, ValueError, PlacementFault) as error:
        raise gdb.GdbError(str(error)) from error
    if placer is not None and placer.tool is not None:
        print(f"placing with {placer.tool.build} ({placer.tool.path})")
    log = store.root / f"{arguments.instance}-xemu.log"
    environment, control = _start_emulator(
        "queue", arguments.xemu, arguments.config, arguments.port, arguments.attach, log
    )
    progress = ProgressStream(store.progress, arguments.instance, arguments.stall)
    emulator = Emulator(
        control,
        arguments.config or default_config(),
        arguments.instance,
        library,
        environment,
        lambda reason: progress.write("emulator", restart=reason),
    )

    def open_session(
        request: Request, digest: str, claim: Claim, folder: Path, on_event: Callable[[str, dict[str, object]], None]
    ) -> DrivenSession:
        if isinstance(request.test, LandingTest):
            if placer is None or arguments.recordings is None:
                raise ValueError("a landing request needs --place and --recordings")
            check_recipe(request.test, arguments.recordings, XBOX_NTSC_U.name)
        return DrivenSession(
            GdbTarget(XBOX_NTSC_U.registers),
            XBOX_NTSC_U,
            folder,
            request,
            digest,
            run_stem=claim.run,
            environment=emulator.environment,
            liveness=arguments.liveness,
            placer=placer,
            recordings=arguments.recordings,
            attempt=claim.attempt,
            instance=claim.instance,
            on_event=on_event,
        )

    _queue = Queue(store, progress, XBOX_NTSC_U, open_session, emulator.boot)
    _queue_end = control.stop if control.restartable else None
    for run in _queue.recover():
        print(f"recovered {run}: its session was lost")
    queue = _queue

    def watch_for_stalls() -> None:
        while _queue is queue:
            time.sleep(60)
            progress.check_stall(queue.current)

    threading.Thread(target=watch_for_stalls, daemon=True).start()
    print(f"queue {arguments.instance} on {store.root}")
    _run_queue()


def _run_queue() -> None:
    """Runs the queue's sessions one after another until it pauses for a person or ends."""
    global _session, _session_out
    while _queue is not None and (session := _queue.start_next()) is not None:
        _session, _session_out = session, session.out
        print(f"running {_queue.current}")
        state = session.run()
        _tell(state)
        if state == PAUSED:
            return
        _finish_queued(session)
    _end_queue()


def _finish_queued(session: Session) -> None:
    assert _queue is not None and isinstance(session, DrivenSession)
    _queue.finish(session)


def _end_queue() -> None:
    global _queue, _queue_end
    if _queue is None:
        return
    print(f"queue ended: {_queue.done} run(s)")
    if _queue_end is not None:
        _queue_end()
    _queue, _queue_end = None, None


_COMMANDS: dict[str, Callable[[Sequence[str]], None]] = {
    "smoke": _smoke,
    "record": _record,
    "drive": _drive,
    "queue": _queue_command,
    "capture": _capture,
    "read": _read,
    "press": _press,
    "resume": _resume,
    "stop": _stop,
}


class _Bowl(gdb.Command):
    """The harness's commands: bowl smoke|record|drive|queue|capture|read|press|resume|stop."""

    def __init__(self) -> None:
        super().__init__("bowl", gdb.COMMAND_USER)

    def invoke(self, argument: str, from_tty: bool) -> None:
        name, *args = gdb.string_to_argv(argument) or [""]
        if (command := _COMMANDS.get(name)) is None:
            raise gdb.GdbError(f"usage: bowl {'|'.join(_COMMANDS)}")
        command(args)


_Bowl()
