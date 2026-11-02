"""Builds scripted guests for the mock target: the stops a game would give, with the memory behind them."""

import struct

from bowlharness.mock import MockTarget, Step
from bowlharness.profiles import XBOX_NTSC_U, PlatformProfile

STACK = 0x1000
BLOCK_HEADER = 0x2000
INSTANCE = 0x3000
ARCHIVE = 0x4000
ARRAY = 0x4400
LAYER_OBJECTS = 0x4800

ARCHIVES = [(b"PLSB", 0, 0), (b"PLSD", 0, 0), (b"PLPB", 1, 0), (b"PLP1", 1, 0)]
CHEAT_ARCHIVES = [(b"PLSA", 0, 0x2000000), (b"PLSC", 0, 0x4000000), (b"PLPA", 1, 0x10000000), (b"PLPC", 1, 0x8000000)]


class ScriptedGame:
    """Collects the steps of a guest's run, one call per stop the game would give."""

    def __init__(self, profile: PlatformProfile = XBOX_NTSC_U) -> None:
        self._profile = profile
        self._steps: list[Step] = []
        self.frame = 0

    def build(self) -> MockTarget:
        """The mock target that plays the steps collected so far."""
        return MockTarget(list(self._steps))

    def scene_init(
        self,
        scene: str,
        counter: int,
        *,
        caller: int = 0x528B6,
        depth: int = 0,
        last_block: tuple[int, int] | None = None,
        extras: dict[int, int] | None = None,
        cheats: int = 0,
    ) -> None:
        """A scene initialising, with heap 0 at the given depth and the costumes the extras and cheats enable."""
        memory = {
            self._profile.globals.scene_counter: struct.pack("<I", counter),
            **self._heap0(depth, last_block),
            **self._costumes(extras or {}, cheats),
        }
        self._step(self._profile.points.scene_init.entry[0], (caller, scene.encode("ascii")), memory=memory)

    def scene_exit(self, scene: str, counter: int) -> None:
        memory = {
            self._profile.globals.current_scene: scene.encode("ascii"),
            self._profile.globals.scene_counter: struct.pack("<I", counter),
        }
        self._step(self._profile.points.scene_exit.entry[0], (0x6EAF0,), memory=memory)

    def alloc(self, heap: int, size: int, alignment: int, address: int, caller: int = 0x1000) -> None:
        self._step(self._profile.points.alloc.returns[-1], (caller, heap, size, alignment, 0, 0, 0), eax=address)

    def layer_alloc(
        self, size: int, address: int, archive: str, layers: int, index: int, *, directory: bool = False
    ) -> None:
        """A block allocated for the layer at ``index`` of ``archive``, or for the archive's asset directory."""
        profile = self._profile.layers
        record = bytearray(profile.count_offset + 4)
        name = f"{archive}{profile.extension}".encode("ascii")
        record[profile.name_offset : profile.name_offset + len(name)] = name
        struct.pack_into("<I", record, profile.layers_offset, ARRAY)
        struct.pack_into("<I", record, profile.count_offset, layers)
        pointers = [LAYER_OBJECTS + 0x80 * layer for layer in range(layers)]
        memory = {
            ARCHIVE: bytes(record),
            ARRAY: struct.pack(f"<{layers}I", *pointers),
            profile.archive: struct.pack("<I", ARCHIVE),
            profile.layer: struct.pack("<I", pointers[index]),
        }
        asked_by = 0x197916 if directory else profile.layer_return
        words = (profile.site, 0, size, 0x40, 0, 0, asked_by)
        self._step(self._profile.points.alloc.returns[-1], words, eax=address, memory=memory)

    def grow(self, heap: int, size: int) -> None:
        self._step(self._profile.points.grow.entry[0], (0x1100, heap, size))

    def push(self, heap: int, depth: int) -> None:
        self._step(self._profile.points.push.returns[0], (0x1200, heap), eax=depth)

    def pop(self, heap: int, depth: int, requested: int = 0) -> None:
        """A pop entering with its arguments and returning with the depth reached."""
        self._step(self._profile.points.pop.entry[0], (0x1300, heap, requested))
        self._step(self._profile.points.pop.returns[0], (0x1300, 0, requested), eax=depth)

    def model(self, instance: int, nodes: int, flags: int, *, bypass: bool = False) -> None:
        """A model allocation returning ``instance``, or failing when it is 0."""
        model = self._profile.model
        memory = {model.bypass: struct.pack("<I", bypass)}
        if instance:
            memory[instance + model.nodes_offset] = bytes([nodes])
        self._step(self._profile.points.model.returns[-1], (0x1400, 0, 0, 0, flags), eax=instance, memory=memory)

    def pool_free(self, instance: int) -> None:
        self._step(self._profile.points.pool_free.entry[0], (0x1500, instance))

    def drawn(self) -> None:
        self._step(self._profile.points.drawn.entry[0], (0x9000,))

    def stop(self, pc: int, words: tuple[int | bytes, ...], *, esp: int = STACK, eax: int = 0) -> None:
        """A stop at ``pc`` with the given stack words, at a stack pointer that may be unreadable."""
        self._step(pc, words, esp=esp, eax=eax)

    def _step(
        self,
        pc: int,
        words: tuple[int | bytes, ...],
        *,
        esp: int = STACK,
        eax: int = 0,
        memory: dict[int, bytes] | None = None,
    ) -> None:
        stack = b"".join(word if isinstance(word, bytes) else struct.pack("<I", word) for word in words)
        self.frame += 1
        frame = {self._profile.globals.frame: struct.pack("<I", self.frame)}
        self._steps.append(Step(pc, {"esp": esp, "eax": eax}, {STACK: stack, **frame, **(memory or {})}))

    def _heap0(self, depth: int, last_block: tuple[int, int] | None) -> dict[int, bytes]:
        heap = self._profile.heap
        descriptor = bytearray(heap.stride)
        struct.pack_into("<H", descriptor, heap.depth_offset, depth)
        for index in range(depth + 1):
            offset = heap.states_offset + index * heap.state_stride
            struct.pack_into("<I", descriptor, offset + heap.cursor_offset, heap.heap0_base + 0x100 * (index + 1))
            struct.pack_into("<H", descriptor, offset + heap.blocks_offset, index + 1)
            struct.pack_into("<II", descriptor, offset + heap.used_offset, 0x100 * (index + 1), 8 * index)
        memory = {heap.descriptors: bytes(descriptor)}
        if last_block:
            struct.pack_into("<I", descriptor, heap.last_block_offset, BLOCK_HEADER)
            memory = {heap.descriptors: bytes(descriptor), BLOCK_HEADER: struct.pack("<II", *last_block)}
        return memory

    def _costumes(self, extras: dict[int, int], cheats: int) -> dict[int, bytes]:
        costumes = self._profile.costumes
        entries = [*ARCHIVES, *CHEAT_ARCHIVES]
        table = b"".join(struct.pack("<4sII", *entry) for entry in entries)
        rows = b"".join(bytes([costumes.extra_kind, extra_id, 0, state]) for extra_id, state in extras.items())
        return {
            costumes.count: struct.pack("<I", len(entries)),
            costumes.table: table,
            costumes.extras_count: struct.pack("<I", len(extras)),
            costumes.extras: rows,
            costumes.cheat_mask: struct.pack("<I", cheats),
        }
