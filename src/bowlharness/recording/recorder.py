"""Records a passive run's events and manifest by observing a target. Nothing here writes to guest memory."""

import logging
import shutil
import struct
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bowlharness.profiles.profile import PlatformProfile, Point
from bowlharness.recording import EventWriter, RunManifest
from bowlharness.recording.captures import take_capture
from bowlharness.recording.detection import bugcheck_addresses, crash_record, stack_words
from bowlharness.recording.observe import bowl_statics, heap0_state, loading_layer, tag, u32, worn_archives
from bowlharness.target import Handle, Registers, Stop, Target, TargetError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Options:
    """What a recording observes.

    Attributes:
        heap_events: Whether heap events are logged for every scene, for none, or for the listed scenes. A scene's
            init always logs its heap state.
        cutoff_captures: Whether a capture is taken at the cutoff of every scene, of none, or of the listed scenes.
        capture_budget: The most captures to take, or ``None`` for no limit.
    """

    heap_events: bool | frozenset[str] = True
    cutoff_captures: bool | frozenset[str] = False
    capture_budget: int | None = None

    def logs_heap(self, scene: str) -> bool:
        """Whether heap events are logged while ``scene`` runs."""
        return _includes(self.heap_events, scene)

    def captures_cutoff(self, scene: str) -> bool:
        """Whether a capture is taken at the cutoff of ``scene``."""
        return _includes(self.cutoff_captures, scene)

    def to_json(self) -> dict[str, object]:
        """The options as a manifest records them."""
        return {
            "heap_events": _listed(self.heap_events),
            "cutoff_captures": _listed(self.cutoff_captures),
            "capture_budget": self.capture_budget,
        }


def _includes(scenes: bool | frozenset[str], scene: str) -> bool:
    return scenes if isinstance(scenes, bool) else scene in scenes


def _listed(scenes: bool | frozenset[str]) -> bool | list[str]:
    return scenes if isinstance(scenes, bool) else sorted(scenes)


@dataclass(frozen=True)
class Hit:
    """A stop as a handler sees it.

    Attributes:
        pc: Where the guest stopped.
        address: The address a watchpoint caught a write to, or ``None``.
        registers: The registers.
        words: The stack words from the stack pointer: the return address, then the arguments.
    """

    pc: int
    address: int | None
    registers: Registers
    words: tuple[int, ...]

    @property
    def caller(self) -> int:
        """The return address of the observed function."""
        return self.words[0]

    @property
    def result(self) -> int:
        """The accumulator, which holds a function's result at its return."""
        return self.registers["eax"]

    def arg(self, index: int) -> int:
        """An argument word."""
        return self.words[1 + index]


class DuplicateFilter:
    """Discards a stop identical to the one before it, except at the exempt addresses.

    The exempt addresses are the ones whose genuine consecutive hits look identical.
    """

    def __init__(self, exempt: frozenset[int]) -> None:
        self._exempt = exempt
        self._last: tuple[int, tuple[tuple[str, int], ...], tuple[int, ...]] | None = None

    def discards(self, hit: Hit) -> bool:
        """Whether this stop repeats the previous one; either way it becomes the previous one."""
        key = (hit.pc, tuple(hit.registers.items()), hit.words)
        repeated = key == self._last and hit.pc not in self._exempt
        self._last = key
        return repeated


class Recorder:
    """Observes a target and writes the recording of what it sees.

    Args:
        target: The target to observe.
        profile: The platform's addresses and constants.
        directory: Where the recording's files go.
        run: The run's id.
        options: What to observe.
        environment: What the session knows of the emulator and the host, for the manifest.
    """

    def __init__(
        self,
        target: Target,
        profile: PlatformProfile,
        directory: Path,
        run: str,
        options: Options,
        environment: dict[str, object] | None = None,
    ) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self._target = target
        self._profile = profile
        self._options = options
        self._directory = directory
        self._manifest_path = directory / "manifest.json"
        self._events = EventWriter((directory / "events.jsonl").open("w", encoding="utf-8", newline="\n"))
        self._manifest = RunManifest(
            run=run,
            platform=profile.name,
            profile=profile.digest,
            boot_scene=profile.boot_scene,
            boot_counter=profile.boot_counter,
            observation=options.to_json(),
            environment=environment or {},
        )
        self._duplicates = DuplicateFilter(frozenset((*profile.points.frame.entry, *profile.points.pad_read.entry)))
        self._heap_handles: list[Handle] = []
        self._handles: set[Handle] = set()
        self._armed: dict[Handle, tuple[int, Callable[[Stop], None]]] = {}
        self._loads_seen = 0
        self.rebooted = False
        self._once: dict[str, Handle] = {}
        self._watched: dict[int, int] | None = None
        self._pops: list[int] = []
        self._counter: int | None = None
        self._scene: str | None = None
        self._capture_ids: Counter[str] = Counter()
        self._last_event: dict[str, object] | None = None
        self._ending: str | None = None
        self._listeners: list[Callable[[str], None]] = []
        self.polls = 0
        self.loading = False

    def start(self, reason: str) -> None:
        """Opens the first segment and arms the points that follow the game's loads."""
        self._manifest.segments.append({"segment": self._events.segment, "reason": reason})
        try:
            frame = u32(self._target.read, self._profile.globals.frame)
        except TargetError:
            frame = 0
        self._events.emit("segment", frame, reason=reason)
        points = self._profile.points
        self._arm(points.scene_init, self._scene_init)
        self._arm(points.scene_exit, self._scene_exit)
        self._arm_crash_detection()
        self._arm(points.entity, self._entity)
        self._arm(points.players_done, self._players_done)
        self._arm(points.scene_id, self._scene_id, at_return=True)
        self._arm(points.reset, self._reset)
        self._manifest.write(self._manifest_path)

    def finish(self, interrupted: str | None = None, ended: str | None = None) -> None:
        """Ends the recording: complete, or interrupted for the given reason.

        Args:
            interrupted: Why the recording was cut short, if it was.
            ended: Why a complete recording ended (``stopped``, ``reboot``); a crash or a hang says so itself.
        """
        self._manifest.complete = interrupted is None
        self._manifest.interrupted = interrupted
        self._manifest.ended = self._ending or ended
        self._manifest.write(self._manifest_path)
        self._events.close()

    def capture(self, trigger: str, label: str | None = None) -> str | None:
        """Captures the stopped guest, unless the budget is spent or the capture fails.

        The budget doesn't apply to the capture of a crash or a hang.

        A capture a person asks for (``manual``) marks the run attended. Every capture is logged as an event and
        listed in the manifest; one the budget refuses is listed there as dropped.

        Returns:
            The capture's id, or ``None`` when it was not taken.
        """
        if trigger == "manual":
            self._manifest.attended = True
        budget = self._options.capture_budget
        if budget is not None and len(self._manifest.captures) >= budget and trigger not in ("crash", "hang"):
            self._manifest.captures_dropped.append({"trigger": trigger, "label": label, "scene": self._scene})
            return None
        try:
            counter = u32(self._target.read, self._profile.globals.scene_counter)
        except TargetError as error:
            self._manifest.events_dropped += 1
            log.warning("dropped a %s capture: %s", trigger, error)
            return None
        base = f"{self._events.segment}-{counter}-{trigger}"
        self._capture_ids[base] += 1
        capture_id = base if self._capture_ids[base] == 1 else f"{base}-{self._capture_ids[base]}"
        directory = self._directory / "captures" / capture_id
        try:
            take_capture(self._target, self._profile, directory, capture_id, trigger, label)
        except (TargetError, ValueError, OSError) as error:
            shutil.rmtree(directory, ignore_errors=True)
            self._manifest.events_dropped += 1
            log.warning("dropped the capture %s: %s", capture_id, error)
            return None
        self._manifest.captures.append(
            {"id": capture_id, "trigger": trigger, "label": label, "counter": counter, "scene": self._scene}
        )
        self._emit("capture", id=capture_id, trigger=trigger, label=label)
        self._manifest.write(self._manifest_path)
        return capture_id

    def _arm(self, point: Point, handler: Callable[[Hit], None], *, at_return: bool = False) -> list[Handle]:
        guarded = self._guard(point, handler, dedupe=True)
        addresses = point.returns if at_return or not point.entry else point.entry
        handles = [self._target.set_breakpoint(address, guarded) for address in addresses]
        self._handles.update(handles)
        self._armed.update({handle: (address, guarded) for handle, address in zip(handles, addresses, strict=True)})
        return handles

    def _clear(self, handle: Handle) -> None:
        if handle in self._handles:
            self._handles.discard(handle)
            self._armed.pop(handle, None)
            self._target.clear(handle)

    def replay_current_stop(self) -> None:
        """Observes the points at the address the guest is stopped at, which it stopped at before reaching them.

        A guest interrupted at a breakpoint's address resumes by stepping over the breakpoint, so the stop the
        breakpoint would have given never happens. The recorder gives it itself.
        """
        pc = self._target.registers().get("eip")
        for address, guarded in [armed for armed in self._armed.values() if armed[0] == pc]:
            guarded(Stop(address))

    def detach(self) -> None:
        """Stops observing: removes every breakpoint and watchpoint this recorder set."""
        for handle in list(self._handles):
            self._clear(handle)

    def _guard(self, point: Point, handler: Callable[[Hit], None], *, dedupe: bool) -> Callable[[Stop], None]:
        def stop(stop: Stop) -> None:
            try:
                registers = self._target.registers()
                data = self._target.read(registers["esp"], 4 * (1 + point.args))
                hit = Hit(stop.pc, stop.address, registers, struct.unpack(f"<{1 + point.args}I", data))
                if dedupe and self._duplicates.discards(hit):
                    self._manifest.duplicates_discarded += 1
                else:
                    handler(hit)
            except (TargetError, ValueError) as error:
                self._manifest.events_dropped += 1
                log.warning("dropped the event at %#x: %s", stop.pc, error)

        return stop

    @property
    def ended(self) -> bool:
        """Whether a crash or a hang has ended the recording."""
        return self._ending is not None

    @property
    def event_count(self) -> int:
        """How many events have been logged."""
        return self._events.count

    def frame(self) -> int:
        """The guest's frame."""
        return u32(self._target.read, self._profile.globals.frame)

    def _emit(self, event: str, **fields: object) -> int:
        seq = self._events.emit(event, self.frame(), **fields)
        self._last_event = {"seq": seq, "event": event}
        for listener in self._listeners:
            listener(event)
        return seq

    def listen(self, listener: Callable[[str], None]) -> None:
        """Calls ``listener`` with the name of each event as it is logged."""
        self._listeners.append(listener)

    def arm_pad_read(self, handler: Callable[[Hit], None]) -> None:
        """Observes the game's pad read: ``handler`` gets each stop there, in the order the guest reaches them.

        Stops at the pad read are never discarded as duplicates, and one the guest was interrupted at is replayed.
        """
        self._arm(self._profile.points.pad_read, handler)

    def count_poll(self) -> None:
        """Counts a poll of the controller, which is progress for the watchdog."""
        self.polls += 1

    def attend(self) -> None:
        """Marks the run attended: a person took part."""
        self._manifest.attended = True

    def log_press(self, row: dict[str, Any]) -> None:
        """Logs a press the harness gave or a person made: in the input ledger and as a ``press`` event.

        A press that is not the harness's own marks the run attended.
        """
        if row["source"] != "harness":
            self.attend()
        self._manifest.input_ledger.append(row)
        self._emit("press", button=row["button"], mask=row["mask"], source=row["source"], polls=row["polls"])
        self._manifest.write(self._manifest_path)

    def _arm_crash_detection(self) -> None:
        """Breaks on the bugcheck functions, as soon as the kernel is loaded: at once, or when the title starts."""
        try:
            addresses = bugcheck_addresses(self._target.read, self._profile)
        except TargetError, ValueError:
            self._arm(self._profile.points.title_entry, self._title_started)
            return
        for kind, address in addresses.items():
            point = Point(entry=(address,), args=1 if kind == "KeBugCheck" else 5)
            self._arm(point, lambda hit, kind=kind: self._bugcheck(kind, hit))

    def _title_started(self, hit: Hit) -> None:
        self._arm_crash_detection()

    def _bugcheck(self, kind: str, hit: Hit) -> None:
        if self.ended:
            return
        self._ending = "crash"
        words = hit.words
        stack = stack_words(self._target.read, hit.registers["esp"], self._profile.crash.scan_words)
        record = crash_record(kind, words, dict(hit.registers), stack, self._target.read, self._profile)
        record |= {"scene": self._scene, "counter": self._counter, "capture": self.capture("crash")}
        self._manifest.crash = record
        try:
            self._emit("crash", **record)
        finally:
            self._target.interrupt()

    def hang(self, stalled: float, frame: int) -> None:
        """Ends the recording as hung: the guest made no progress for ``stalled`` seconds."""
        if self.ended:
            return
        self._ending = "hang"
        record = {
            "stalled": stalled,
            "last_frame": frame,
            "last_event": self._last_event,
            "scene": self._scene,
            "counter": self._counter,
            "capture": self.capture("hang"),
        }
        self._manifest.hang = record
        self._emit("hang", **record)

    def note(self, event: str, **fields: object) -> None:
        """Logs something a person did, which marks the run attended."""
        self._manifest.attended = True
        self._emit(event, **fields)

    def replay_scene_init(self) -> None:
        """Observes the scene init the guest is stopped at, for a recording that opens at a reboot."""
        point = self._profile.points.scene_init
        self._guard(point, self._scene_init, dedupe=False)(Stop(point.entry[0]))

    def _scene_init(self, hit: Hit) -> None:
        if hit.caller == self._profile.boot_return and self._loads_seen > 0:
            self.rebooted = True
            self._target.interrupt()
            return
        self._loads_seen += 1
        scene = tag(hit.arg(0))
        counter = u32(self._target.read, self._profile.globals.scene_counter)
        heap = heap0_state(self._target.read, self._profile.heap)
        costumes = worn_archives(self._target.read, self._profile.costumes)
        if self._counter is not None and counter != self._counter + 1 and hit.caller != self._profile.boot_return:
            self._emit("counter_gap", counter=counter, expected=self._counter + 1)
        self._counter = counter
        self._scene = scene
        self.loading = True
        seq = self._emit("scene_init", scene=scene, caller=hit.caller, counter=counter, heap=heap)
        self._manifest.loads.append(
            {
                "segment": self._events.segment,
                "counter": counter,
                "scene": scene,
                "first_seq": seq,
                "costumes": costumes,
            }
        )
        self._arm_heap_events(self._options.logs_heap(scene))
        points = self._profile.points
        self._arm_once("drawn", points.drawn, self._drawn)
        self._arm_once("first_stale_write", points.first_stale_write, self._first_stale_write)
        self._arm_watches()

    def _scene_exit(self, hit: Hit) -> None:
        scene = tag(u32(self._target.read, self._profile.globals.current_scene))
        self._emit("scene_exit", scene=scene, counter=u32(self._target.read, self._profile.globals.scene_counter))

    def _arm_once(self, name: str, point: Point, handler: Callable[[Hit], None]) -> None:
        """Arms a point that fires once per load: it disarms at its first hit and is armed again at the next init."""
        if name in self._once:
            return

        def fire(hit: Hit) -> None:
            self._clear(self._once.pop(name))
            handler(hit)

        self._once[name] = self._arm(point, fire)[0]

    def _drawn(self, hit: Hit) -> None:
        self.loading = False
        self._emit("drawn")
        if self._scene is not None and self._options.captures_cutoff(self._scene):
            self.capture("cutoff")

    def _first_stale_write(self, hit: Hit) -> None:
        self._emit(
            "first_stale_write",
            scene=self._scene,
            counter=self._counter,
            s=hit.registers["eax"],
            bowl=bowl_statics(self._target.read, self._profile.globals),
        )

    def _arm_watches(self) -> None:
        """Watches the bowl's variables from the first load on, keeping each value to report what a write replaced."""
        if self._watched is not None:
            return
        self._watched = {address: u32(self._target.read, address) for address in self._profile.globals.watched}
        for address in self._watched:
            guarded = self._guard(Point(args=self._profile.globals.watch_stack_words), self._watch, dedupe=False)
            self._handles.add(self._target.set_watchpoint(address, 4, guarded))

    def _watch(self, hit: Hit) -> None:
        if self._watched is None or hit.address is None:
            raise ValueError("a watch stop with no watched address")
        new = u32(self._target.read, hit.address)
        old, self._watched[hit.address] = self._watched[hit.address], new
        self._emit("watch", address=hit.address, old=old, new=new, pc=hit.pc, stack=list(hit.words))

    def _entity(self, hit: Hit) -> None:
        self._emit("entity", address=hit.registers["eax"])

    def _players_done(self, hit: Hit) -> None:
        self._emit(
            "players_done",
            scene=self._scene,
            counter=self._counter,
            bowl=bowl_statics(self._target.read, self._profile.globals),
        )

    def _scene_id(self, hit: Hit) -> None:
        scene_object = u32(self._target.read, self._profile.globals.scene_pointer)
        self._emit("scene_id", scene=self._scene, counter=self._counter, id=u32(self._target.read, scene_object))

    def _reset(self, hit: Hit) -> None:
        self._emit("reset", counter=self._counter)

    def _arm_heap_events(self, wanted: bool) -> None:
        if wanted == bool(self._heap_handles):
            return
        if not wanted:
            for handle in self._heap_handles:
                self._clear(handle)
            self._heap_handles.clear()
            self._pops.clear()
            return
        points = self._profile.points
        for point, handler in (
            (points.alloc, self._alloc),
            (points.grow, self._grow),
            (points.push, self._push),
            (points.pop, self._pop),
            (points.model, self._model),
            (points.pool_free, self._pool_free),
        ):
            self._heap_handles += self._arm(point, handler)
        self._heap_handles += self._arm(points.pop, self._pop_return, at_return=True)

    def _alloc(self, hit: Hit) -> None:
        layers = self._profile.layers
        fields: dict[str, object] = {}
        if hit.caller == layers.site and hit.arg(layers.caller_arg) == layers.layer_return:
            try:
                fields["layer"] = loading_layer(self._target.read, layers)
            except (TargetError, ValueError) as error:
                log.warning("an archive layer's block has no known layer: %s", error)
        self._emit(
            "alloc",
            heap=hit.arg(0),
            size=hit.arg(1),
            alignment=hit.arg(2),
            address=hit.result,
            caller=hit.caller,
            **fields,
        )

    def _grow(self, hit: Hit) -> None:
        self._emit("grow", heap=hit.arg(0), size=hit.arg(1))

    def _push(self, hit: Hit) -> None:
        self._emit("push", heap=hit.arg(0))

    def _pop(self, hit: Hit) -> None:
        self._pops.append(hit.arg(0))

    def _pop_return(self, hit: Hit) -> None:
        if not self._pops:
            raise ValueError("a pop returned that was not seen entering")
        self._emit("pop", heap=self._pops.pop(), depth=hit.result)

    def _model(self, hit: Hit) -> None:
        model = self._profile.model
        instance = hit.result
        nodes = self._target.read(instance + model.nodes_offset, 1)[0] if instance else 0
        self._emit(
            "model",
            bypass=u32(self._target.read, model.bypass) != 0,
            instance=instance,
            nodes=nodes,
            flags=hit.arg(model.flags_arg),
            caller=hit.caller,
        )

    def _pool_free(self, hit: Hit) -> None:
        self._emit("pool_free", instance=hit.arg(0))
