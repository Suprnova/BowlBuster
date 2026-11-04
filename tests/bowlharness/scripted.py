"""Builds scripted guests for the mock target: the stops a game would give, with the memory behind them."""

import struct
from dataclasses import replace

from bowlharness.backends.mock import MockTarget, Step, Wait
from bowlharness.profiles import XBOX_NTSC_U, PlatformProfile

STACK = 0x1000
BLOCK_HEADER = 0x2000
INSTANCE = 0x3000
ARCHIVE = 0x4000
ARRAY = 0x4400
LAYER_OBJECTS = 0x4800
SCENE_OBJECT = 0x5000
PAD_RECORD = 0x6000
PAD_BUFFER = 0x6200
SEQUENCES = 0x7000
PAUSE_MENU = 0xB94EE0
OPTIONS_MENU = 0xB94E40
BUGCHECK_RVAS = (0x94B0, 0x9442)


def _tag(text: str) -> bytes:
    """A four-character tag as the game holds it in memory: a dword with the first character most significant."""
    return text.encode("ascii")[::-1]


COMPACT = replace(XBOX_NTSC_U, static_range=(0x8000, 0x8040))

ARCHIVES = [(_tag("PLSB"), 0, 0), (_tag("PLSD"), 0, 0), (_tag("PLPB"), 1, 0), (_tag("PLP1"), 1, 0)]
CHEAT_ARCHIVES = [
    (_tag("PLSA"), 0, 0x2000000),
    (_tag("PLSC"), 0, 0x4000000),
    (_tag("PLPA"), 1, 0x10000000),
    (_tag("PLPC"), 1, 0x8000000),
]

CHEATS = [
    ("X Y X Y X Y X Y", 0x800000, False),
    ("X X X X Y Y Y Y", 0x2000000, True),
    ("Y Y Y Y X X X X", 0x4000000, True),
    ("X Y Y X X Y Y X", 0x8000000, True),
    ("Y X X Y Y X X Y", 0x10000000, True),
    ("X X Y Y X X Y Y", 0x20000, False),
    ("Y Y X X Y Y X X", 0x400000, False),
    ("X Y Y Y Y Y Y X", 0x100, False),
    ("Y X X X X X X Y", 0x40000, True),
]


class ScriptedGame:
    """Collects the steps of a guest's run, one call per stop the game would give."""

    def __init__(self, profile: PlatformProfile = COMPACT) -> None:
        self.profile = profile
        self._profile = profile
        self._steps: list[Step] = []
        self.frame = 0
        self.cursor = (0, 0)
        self.menu_lag = 0
        self.held = 0
        self.options_open = False
        self.main_menu_ready = False
        self._menu: dict[int, bytes] = {}

    @property
    def script(self) -> list[Step]:
        """The steps collected so far."""
        return list(self._steps)

    def build(self, *, kernel_loaded: bool = False) -> MockTarget:
        """The mock target that plays the steps collected so far, with the kernel already in memory if asked."""
        return MockTarget(self.script, self.kernel_image() if kernel_loaded else None)

    def kernel_image(self) -> dict[int, bytes]:
        """A kernel image whose export table places the bugcheck functions."""
        base = self._profile.kernel_base
        header, directory, functions = 0x80, 0x200, 0x300
        memory = {
            base + 0x3C: struct.pack("<I", header),
            base + header + 0x78: struct.pack("<I", directory),
            base + directory + 0x10: struct.pack("<III", 1, 400, 0),
            base + directory + 0x1C: struct.pack("<I", functions),
        }
        for ordinal, rva in zip(self._profile.bugcheck_ordinals, BUGCHECK_RVAS, strict=True):
            memory[base + functions + 4 * (ordinal - 1)] = struct.pack("<I", rva)
        return memory

    def bugcheck_address(self, kind: str) -> int:
        """Where the kernel image puts a bugcheck function."""
        return self._profile.kernel_base + BUGCHECK_RVAS[("KeBugCheck", "KeBugCheckEx").index(kind)]

    def kernel_loaded(self) -> None:
        """The kernel appearing in memory, as it does before the title starts."""
        self._step(0, (0,), memory=self.kernel_image())

    def title_started(self) -> None:
        self._step(self._profile.points.title_entry.entry[0], (0,))

    def bugcheck(self, kind: str, code: int, *params: int, calls: tuple[int, ...] = (), esp: int = STACK) -> None:
        """A bugcheck, with the stack words after its arguments: ``calls`` are return addresses, each after a call."""
        memory = {address - 6: bytes([0x90, 0xE8, 0, 0, 0, 0]) for address in calls}
        padding = (0,) * self._profile.crash.scan_words
        self._step(self.bugcheck_address(kind), (0x8001CA36, code, *params, *calls, *padding), memory=memory, esp=esp)

    def idle(self, seconds: float, frame: int) -> None:
        """The guest running for ``seconds`` with no stop, the frame counter then at ``frame``."""
        memory = {self._profile.globals.frame: struct.pack("<I", frame)}
        self._step(0, (0,), memory=memory, seconds=seconds)

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
            self._profile.globals.current_scene: _tag(scene),
            **{address: bytes(4) for address in self._profile.globals.watched},
            **self._capturable(depth),
            **self._heap0(depth, last_block),
            **self._costumes(extras or {}, cheats),
        }
        self._step(self._profile.points.scene_init.entry[0], (caller, _tag(scene)), memory=memory)

    def scene_exit(self, scene: str, counter: int) -> None:
        memory = {
            self._profile.globals.current_scene: _tag(scene),
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

    def entity(self, address: int) -> None:
        self._step(self._profile.points.entity.entry[0], (0x7267E,), eax=address)

    def players_done(self) -> None:
        self._step(self._profile.points.players_done.entry[0], (0x4E8D2,))

    def scene_id(self, scene_id: int) -> None:
        """A scene init returning, with the scene object holding its id."""
        globals_ = self._profile.globals
        memory = {globals_.scene_pointer: struct.pack("<I", SCENE_OBJECT), SCENE_OBJECT: struct.pack("<I", scene_id)}
        self._step(self._profile.points.scene_id.returns[0], (0x528B6,), memory=memory)

    def stale_write(self, sphere: int | None = None) -> None:
        """The render writing through ``sphere``, or through the pointer the sphere dword holds then."""
        point = self._profile.points.first_stale_write.entry[0]
        if sphere is None:
            self._step(point, (0x9500,), eax_from=self._profile.globals.sphere)
        else:
            self._step(point, (0x9500,), eax=sphere)

    def reset(self) -> None:
        self._step(self._profile.points.reset.entry[0], (0x703DE,))

    def watch(self, address: int, value: int, pc: int = 0x9600) -> None:
        """A write of ``value`` to a watched ``address``, with a stack of two words."""
        stack = tuple(range(1, self._profile.globals.watch_stack_words + 2))
        self._step(pc, stack, memory={address: struct.pack("<I", value)}, written=address)

    def drawn(self) -> None:
        self._step(self._profile.points.drawn.entry[0], (0x9000,))

    def pad_poll(
        self,
        physical: int = 0,
        *,
        port: int = 0,
        result: int = 1,
        pressed: int = 0,
        mode: int | None = None,
        state: int = 1,
        control_off: int = 0,
        gate: int = 1,
        movie: int = 2,
        wait: Wait | None = None,
    ) -> None:
        """A poll of the pad: the button dword holds ``physical`` and the pad record shows ``pressed`` as the edge.

        The game is in play unless ``mode`` says otherwise, and the record shows the buttons the game has seen held
        (:attr:`held`). A ``wait`` makes the poll repeat until a press arrives.
        """
        profile = self._profile
        pad, navigation = profile.input, profile.navigation
        mode = navigation.modes.play if mode is None else mode
        active = (mode == navigation.modes.pause_menu and self.menu_lag == 0) or (
            mode == navigation.modes.menu and self.main_menu_ready
        )
        if mode == navigation.modes.pause_menu and self.menu_lag:
            self.menu_lag -= 1
        record = bytearray(pad.record_stride)
        struct.pack_into("<I", record, pad.pressed_offset, pressed)
        struct.pack_into("<I", record, pad.held_offset, self.held)
        memory = {
            pad.active_record: struct.pack("<I", PAD_RECORD),
            PAD_RECORD: bytes(record),
            PAD_BUFFER: struct.pack("<I", physical),
            profile.globals.active_port: bytes(1),
            profile.globals.game_mode: struct.pack("<I", mode),
            navigation.menu_active: struct.pack(
                "<I", (OPTIONS_MENU if self.options_open else PAUSE_MENU) if active else 0
            ),
            profile.globals.play_state: struct.pack("<I", state),
            navigation.control_off: struct.pack("<I", control_off),
            navigation.render_gate: bytes([gate]),
            navigation.movie_flag: struct.pack("<I", movie),
            navigation.menu_world: struct.pack("<I", self.cursor[0]),
            navigation.menu_slot: struct.pack("<I", self.cursor[1]),
            **self._menu,
        }
        words = (PAD_RECORD, PAD_BUFFER, 0, 0, 0, port)
        self._step(profile.points.pad_read.entry[0], words, eax=result, memory=memory, wait=wait)

    def menu_scenes(self, rows: dict[tuple[int, int], str]) -> None:
        """The scenes the pause menu holds, by world and slot (both from 0), as the game fills its table at boot."""
        navigation = self._profile.navigation
        self._menu = {
            navigation.menu_scenes
            + world * navigation.menu_row_stride
            + slot * navigation.menu_slot_stride: scene.encode()
            for (world, slot), scene in rows.items()
        }

    def await_press(
        self,
        button: str,
        *,
        cursor: tuple[int, int] | None = None,
        mode: int | None = None,
        after: int | None = None,
        polls: int = 30,
        memory: dict[int, int] | None = None,
    ) -> None:
        """A poll that repeats until the harness presses ``button``, then the polls that finish the press.

        The game is in ``mode`` until the press arrives and in ``after`` (by default the same) from then on, and the
        pause menu's cursor moves to ``cursor``.
        The polls after the press are the rest of its hold and its release, so the next wait sees only its own press.
        ``memory`` gives dwords that take their values once the press arrives.
        """
        pad = self._profile.input
        navigation = self._profile.navigation
        then = {address: struct.pack("<I", value) for address, value in (memory or {}).items()}
        if cursor is not None:
            then |= {
                navigation.menu_world: struct.pack("<I", cursor[0]),
                navigation.menu_slot: struct.pack("<I", cursor[1]),
            }
        self.pad_poll(mode=mode, wait=Wait(PAD_BUFFER, getattr(pad.buttons, button), polls, then))
        if cursor is not None:
            self.cursor = cursor
        for _ in range(pad.hold_polls - 1 + pad.release_polls):
            self.pad_poll(mode=mode if after is None else after)

    def await_chord(self, *buttons: str, polls: int = 30) -> None:
        """A poll that repeats until the harness holds ``buttons``; the pad record shows them held after it."""
        pad = self._profile.input
        mask = sum(getattr(pad.buttons, button) for button in buttons)
        self.pad_poll(mode=self._profile.navigation.modes.pause_menu, wait=Wait(PAD_BUFFER, mask, polls))
        self.held = mask

    def enter_code(
        self, code: str, *, mask_before: int = 0, polls: int = 30, count_stops_at: int | None = None
    ) -> None:
        """The presses of a cheat code: each raises the history's count, and the last sets or toggles its row's bit.

        A code that stops at ``count_stops_at`` presses leaves the count there and takes no more.
        """
        navigation = self._profile.navigation
        mask_address = self._profile.costumes.cheat_mask
        bit, toggles = next((bit, toggles) for text, bit, toggles in CHEATS if text == code)
        buttons = code.lower().split()
        for number, button in enumerate(buttons, 1):
            if count_stops_at is not None and number > count_stops_at:
                break
            last = number == len(buttons)
            after = mask_before ^ bit if toggles else mask_before | bit
            memory = {navigation.cheats.count: 0, mask_address: after} if last else {navigation.cheats.count: number}
            self.await_press(button, mode=navigation.modes.pause_menu, polls=polls, memory=memory)

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
        written: int | None = None,
        seconds: float = 0.0,
        wait: Wait | None = None,
        eax_from: int | None = None,
    ) -> None:
        stack = b"".join(word if isinstance(word, bytes) else struct.pack("<I", word) for word in words)
        self.frame += 1
        frame = {self._profile.globals.frame: struct.pack("<I", self.frame)}
        self._steps.append(
            Step(
                pc,
                {"esp": esp, "eax": eax, "eip": pc},
                {STACK: stack, **frame, **(memory or {})},
                written,
                seconds,
                wait,
                eax_from,
            )
        )

    def _capturable(self, depth: int) -> dict[int, bytes]:
        """The bytes a capture reads: the static range, heap 0 up to its cursor, and the bowl's statics."""
        first, last = self._profile.globals.bowl_statics
        static_first, static_last = self._profile.static_range
        heap0 = 0x100 * (depth + 1)
        return {
            static_first: bytes(index % 251 for index in range(static_last - static_first)),
            self._profile.heap.heap0_base: bytes(index % 241 for index in range(heap0)),
            first: struct.pack(f"<{(last - first) // 4 + 1}I", *range(1, (last - first) // 4 + 2)),
        }

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
            **self._cheat_table(),
            costumes.count: struct.pack("<I", len(entries)),
            costumes.table: table,
            costumes.extras_count: struct.pack("<I", len(extras)),
            costumes.extras: rows,
            costumes.cheat_mask: struct.pack("<I", cheats),
        }

    def _cheat_table(self) -> dict[int, bytes]:
        cheats = self._profile.navigation.cheats
        buttons = self._profile.input.buttons
        navigation = self._profile.navigation
        memory = {
            cheats.count: bytes(4),
            navigation.menu_screens: struct.pack("<I", 5),
            navigation.title_start: struct.pack("<I", 1),
        }
        for index, (code, bit, toggles) in enumerate(CHEATS):
            sequence = SEQUENCES + 4 * cheats.history_length * index
            presses = [buttons.x if press == "X" else buttons.y for press in code.split()]
            memory[sequence] = struct.pack(f"<{cheats.history_length}I", *[0] * len(presses), *presses)
            row = bytearray(cheats.row_stride)
            struct.pack_into("<I", row, cheats.sequence_offset, sequence)
            struct.pack_into("<I", row, cheats.mask_offset, bit)
            struct.pack_into("<I", row, cheats.flags_offset, cheats.toggle_flag if toggles else 0)
            memory[cheats.table + index * cheats.row_stride] = bytes(row)
        return memory
