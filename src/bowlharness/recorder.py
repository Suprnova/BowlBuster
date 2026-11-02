"""Records a passive run's events and manifest by observing a target. Nothing here writes to guest memory."""

import logging
import shutil
import struct
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bowlharness.observe import heap0_state, loading_layer, tag, u32, worn_archives
from bowlharness.profiles.profile import PlatformProfile, Point
from bowlharness.recording import EventWriter, RunManifest
from bowlharness.recording.captures import take_capture
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
    """A stop as a handler sees it: the registers, and the return address then the arguments from the stack."""

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

    def discards(self, pc: int, hit: Hit) -> bool:
        """Whether this stop repeats the previous one; either way it becomes the previous one."""
        key = (pc, tuple(hit.registers.items()), hit.words)
        repeated = key == self._last and pc not in self._exempt
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
    """

    def __init__(self, target: Target, profile: PlatformProfile, directory: Path, run: str, options: Options) -> None:
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
        )
        self._duplicates = DuplicateFilter(frozenset(profile.points.frame.entry))
        self._heap_handles: list[Handle] = []
        self._drawn_handle: Handle | None = None
        self._pops: list[int] = []
        self._counter: int | None = None
        self._scene: str | None = None
        self._capture_ids: Counter[str] = Counter()

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
        self._manifest.write(self._manifest_path)

    def finish(self, interrupted: str | None = None) -> None:
        """Ends the recording: complete, or interrupted for the given reason."""
        self._manifest.complete = interrupted is None
        self._manifest.interrupted = interrupted
        self._manifest.write(self._manifest_path)
        self._events.close()

    def capture(self, trigger: str, label: str | None = None) -> str | None:
        """Captures the stopped guest, unless the budget is spent or the capture fails.

        A capture a person asks for (``manual``) marks the run attended. Every capture is logged as an event and
        listed in the manifest; one the budget refuses is listed there as dropped.

        Returns:
            The capture's id, or ``None`` when it was not taken.
        """
        if trigger == "manual":
            self._manifest.attended = True
        budget = self._options.capture_budget
        if budget is not None and len(self._manifest.captures) >= budget:
            self._manifest.captures_dropped.append({"trigger": trigger, "label": label, "scene": self._scene})
            return None
        counter = u32(self._target.read, self._profile.globals.scene_counter)
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
        guarded = self._guard(point, handler)
        addresses = point.returns if at_return or not point.entry else point.entry
        return [self._target.set_breakpoint(address, guarded) for address in addresses]

    def _guard(self, point: Point, handler: Callable[[Hit], None]) -> Callable[[Stop], None]:
        def stop(stop: Stop) -> None:
            try:
                registers = self._target.registers()
                data = self._target.read(registers["esp"], 4 * (1 + point.args))
                hit = Hit(registers, struct.unpack(f"<{1 + point.args}I", data))
                if self._duplicates.discards(stop.pc, hit):
                    self._manifest.duplicates_discarded += 1
                else:
                    handler(hit)
            except (TargetError, ValueError) as error:
                self._manifest.events_dropped += 1
                log.warning("dropped the event at %#x: %s", stop.pc, error)

        return stop

    def _emit(self, event: str, **fields: object) -> int:
        frame = u32(self._target.read, self._profile.globals.frame)
        return self._events.emit(event, frame, **fields)

    def _scene_init(self, hit: Hit) -> None:
        scene = tag(hit.arg(0))
        counter = u32(self._target.read, self._profile.globals.scene_counter)
        heap = heap0_state(self._target.read, self._profile.heap)
        costumes = worn_archives(self._target.read, self._profile.costumes)
        if self._counter is not None and counter != self._counter + 1 and hit.caller != self._profile.boot_return:
            self._emit("counter_gap", counter=counter, expected=self._counter + 1)
        self._counter = counter
        self._scene = scene
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
        self._arm_drawn()

    def _scene_exit(self, hit: Hit) -> None:
        scene = tag(u32(self._target.read, self._profile.globals.current_scene))
        self._emit("scene_exit", scene=scene, counter=u32(self._target.read, self._profile.globals.scene_counter))

    def _arm_drawn(self) -> None:
        if self._drawn_handle is None:
            self._drawn_handle = self._arm(self._profile.points.drawn, self._drawn)[0]

    def _drawn(self, hit: Hit) -> None:
        if self._drawn_handle is not None:
            self._target.clear(self._drawn_handle)
            self._drawn_handle = None
        self._emit("drawn")
        if self._scene is not None and self._options.captures_cutoff(self._scene):
            self.capture("cutoff")

    def _arm_heap_events(self, wanted: bool) -> None:
        if wanted == bool(self._heap_handles):
            return
        if not wanted:
            for handle in self._heap_handles:
                self._target.clear(handle)
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
