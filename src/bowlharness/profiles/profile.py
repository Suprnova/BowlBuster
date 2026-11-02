"""The platform profile: every address and constant that belongs to one platform's build of the game."""

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Point:
    """A place in the game's code the recorder observes.

    The arguments are the stack words after the return address, which sits at the stack pointer. They are read at the
    entry when the point has one, since a function may overwrite its argument slots before it returns, and otherwise
    at the return.

    Attributes:
        entry: Addresses of the function's first instruction, or of the instruction observed.
        returns: Addresses of every return instruction of the function. The result is in the accumulator there.
        args: How many argument words to read.
    """

    entry: tuple[int, ...] = ()
    returns: tuple[int, ...] = ()
    args: int = 0


@dataclass(frozen=True)
class Points:
    """The points the recorder observes, by event."""

    scene_init: Point
    scene_exit: Point
    alloc: Point
    grow: Point
    push: Point
    pop: Point
    model: Point
    pool_free: Point
    drawn: Point
    frame: Point
    title_entry: Point
    entity: Point
    players_done: Point
    scene_id: Point
    first_stale_write: Point
    reset: Point


@dataclass(frozen=True)
class Heap:
    """How a heap descriptor is laid out in guest memory.

    A descriptor holds the heap's flags, its depth states and its current depth. A depth state holds a cursor, a block
    count, the bytes used and the bytes wasted. The last block is a pointer to the header of the block last
    allocated, which holds the block's address and size.
    """

    descriptors: int
    stride: int
    flags_offset: int
    states_offset: int
    state_stride: int
    state_count: int
    cursor_offset: int
    blocks_offset: int
    used_offset: int
    wasted_offset: int
    depth_offset: int
    last_block_offset: int
    block_address_offset: int
    block_size_offset: int
    heap0_base: int
    active_heap: int


@dataclass(frozen=True)
class Model:
    """Where the model allocator's fields are read.

    The instance is the result. The flags are an argument. The bypass flag is a global, and the node count a byte of
    the instance.
    """

    bypass: int
    nodes_offset: int
    flags_arg: int


@dataclass(frozen=True)
class Costumes:
    """How the worn player archive of each character is resolved.

    The costume table has an entry per archive: its tag, its character and the cheat-mask bits that enable it. The
    first entries are enabled instead by a row of the extras table, of the given kind, whose id is the entry's index
    plus one. The first enabled entry of a character is the one worn.

    Attributes:
        characters: What a recording calls each character, by the index the table's character field holds.
    """

    characters: tuple[str, ...]
    table: int
    count: int
    stride: int
    character_offset: int
    mask_offset: int
    extras_count: int
    extras: int
    extra_stride: int
    extra_state_offset: int
    extra_kind: int
    extra_entries: int
    cheat_mask: int


@dataclass(frozen=True)
class Crash:
    """How a bugcheck is read.

    A bugcheck for an unhandled exception has the given code; its first parameter is the exception's code, and the
    others, by index among the parameters, are the faulting instruction, the kind of access (1 for a write) and the
    address accessed.

    Attributes:
        stack_words: How many stack words a crash record keeps.
        scan_words: How many stack words are searched for return addresses.
        exception_bugcheck: The bugcheck code for an unhandled exception.
        access_violation: The exception code of an access violation.
        instruction_param: The index of the faulting instruction's address among the parameters.
        access_param: The index of the access kind.
        address_param: The index of the address accessed.
    """

    stack_words: int
    scan_words: int
    exception_bugcheck: int
    access_violation: int
    instruction_param: int
    access_param: int
    address_param: int


@dataclass(frozen=True)
class Layers:
    """How the archive layer being loaded is found when a layer's block is allocated.

    The allocation of a layer's block returns to ``site``, as does an archive's asset directory. The layer's block is
    told apart by the function that asked for it: the word ``caller_arg`` of the allocation's stack, which holds that
    function's return address, is ``layer_return`` for a layer. The loader keeps the archive and the layer it is
    loading in two globals. An archive record names its file and holds the array of its layers.

    Attributes:
        site: The return address of the allocation shared by layers and asset directories.
        caller_arg: The argument word of the allocation's stack that holds its caller's return address.
        layer_return: That return address when a layer asked for the block.
        archive: The global that points at the archive record being loaded.
        layer: The global that points at the layer being loaded.
        name_offset: Where an archive record holds its file name, a null-terminated string.
        name_size: The most bytes a file name takes.
        extension: The extension of an archive's file name.
        layers_offset: Where an archive record holds the pointer to its array of layer pointers.
        count_offset: Where an archive record holds the number of layers.
    """

    site: int
    caller_arg: int
    layer_return: int
    archive: int
    layer: int
    name_offset: int
    name_size: int
    extension: str
    layers_offset: int
    count_offset: int


@dataclass(frozen=True)
class Globals:
    """The guest globals the recorder reads.

    Attributes:
        scene_counter: The load counter, already advanced when a scene initialises.
        current_scene: The four characters of the scene being run, valid from its init until its exit.
        frame: A dword that grows by one each frame.
        bowl_statics: First and last dword of the bowl's statics.
        watched: The dwords whose writes are watched.
        watch_stack_words: How many stack words a watch event records.
        sphere: The dword holding the pointer the bowl writes through.
        scene_pointer: The dword holding the pointer to the scene, whose first dword is the scene's id.
    """

    scene_counter: int
    current_scene: int
    frame: int
    bowl_statics: tuple[int, int]
    watched: tuple[int, ...]
    watch_stack_words: int
    sphere: int
    scene_pointer: int
    token_count: int
    manliness_count: int
    play_state: int
    game_mode: int
    active_port: int


@dataclass(frozen=True)
class PlatformProfile:
    """Everything the harness knows about one platform's build of the game.

    Attributes:
        name: The platform, as a recording names it.
        arch: The processor architecture.
        registers: The registers a capture and a crash record read, by name.
        code: First and one past the last address of the game's code.
        static_range: First and one past the last address of the data and zero-initialised sections.
        heap_block_size: The size of the block the game takes for its heaps.
        boot_scene: The scene the game boots into.
        boot_counter: The load counter at the boot scene.
        boot_return: The return address of the call that initialises the boot scene.
        kernel_base: Where the kernel image is mapped.
        bugcheck_ordinals: The kernel export ordinals of ``KeBugCheck`` and ``KeBugCheckEx``.
    """

    name: str
    arch: str
    registers: tuple[str, ...]
    code: tuple[int, int]
    static_range: tuple[int, int]
    heap_block_size: int
    boot_scene: str
    boot_counter: int
    boot_return: int
    kernel_base: int
    bugcheck_ordinals: tuple[int, int]
    points: Points
    heap: Heap
    model: Model
    costumes: Costumes
    layers: Layers
    crash: Crash
    globals: Globals

    @property
    def digest(self) -> str:
        """A hash of the whole profile, for a run's manifest."""
        canonical = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
