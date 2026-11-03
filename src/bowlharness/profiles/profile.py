"""The platform profile: every address and constant that belongs to one platform's build of the game."""

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum


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
    pad_read: Point


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
        tag_prefixes: How the tags of each character's archives start, in the order of ``characters``.
    """

    characters: tuple[str, ...]
    tag_prefixes: tuple[str, ...]
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
class Buttons:
    """The masks of the buttons in the game's button dword, by name."""

    a: int
    b: int
    x: int
    y: int
    start: int
    back: int
    l: int  # noqa: E741
    r: int
    up: int
    down: int
    left: int
    right: int


@dataclass(frozen=True)
class Input:
    """How the harness presses buttons at the game's pad read.

    At the pad read point the stack holds the pad record, then a pointer to the button dword the read has just filled,
    and further on the port (``Globals.active_port`` names the one the controller is on); the accumulator is zero when
    no pad was read. A pad record holds the held mask, the
    pressed edge and the released edge, and a time per button.

    Attributes:
        record_word: The stack word, counted from the stack pointer, that holds the pad record's address.
        buffer_word: The stack word that holds the address of the button dword.
        port_word: The stack word that holds the port being polled.
        active_record: The dword that holds the active pad record's address.
        record_base: Where port 0's pad record starts.
        record_stride: The size of a pad record.
        held_offset: Where a pad record holds the held mask.
        pressed_offset: Where it holds the pressed edge.
        released_offset: Where it holds the released edge.
        times_offset: Where it holds the time of the first button.
        buttons: The button masks.
        hold_polls: How many polls a press is held for.
        release_polls: How many polls it is released for before the next.
        resend_limit: How many times a press the game didn't take is sent again.
    """

    record_word: int
    buffer_word: int
    port_word: int
    active_record: int
    record_base: int
    record_stride: int
    held_offset: int
    pressed_offset: int
    released_offset: int
    times_offset: int
    buttons: Buttons
    hold_polls: int
    release_polls: int
    resend_limit: int


@dataclass(frozen=True)
class GameModes:
    """The values of the game mode (``Globals.game_mode``).

    Attributes:
        boot_movies: The boot logos.
        menu: The title, the main menu and the autosave prompt.
        pause_menu: The pause menu and the options menu.
        play: A level in play.
        paused: Every mode in which the game is paused.
    """

    boot_movies: int
    menu: int
    pause_menu: int
    play: int
    paused: tuple[int, ...]


@dataclass(frozen=True)
class Cheats:
    """How the cheat entry and its table are read.

    The cheat entry takes the pressed X and Y buttons into a history, counted and timed out by its own dwords. A row of
    the cheat table names the history it matches, the callback it calls, the bit it sets in the cheat mask, and flags,
    one of which makes it toggle the bit.

    Attributes:
        held: The held mask the entry needs and no more: both triggers.
        count: The dword holding the number of presses in the history.
        timeout: The dword holding the float that counts down to clearing the history.
        history: The first of the history's dwords.
        history_length: How many dwords the history has.
        table: The first row of the cheat table.
        row_stride: The size of a row.
        sequence_offset: Where a row holds the address of its sequence.
        mask_offset: Where it holds its mask bit.
        flags_offset: Where it holds its flags.
        toggle_flag: The flag that makes the row toggle its bit.
    """

    held: int
    count: int
    timeout: int
    history: int
    history_length: int
    table: int
    row_stride: int
    sequence_offset: int
    mask_offset: int
    flags_offset: int
    toggle_flag: int


@dataclass(frozen=True)
class Navigation:
    """What the harness reads and waits for while it moves through the game.

    Attributes:
        modes: The game mode values.
        playing: The play state (``Globals.play_state``) of a level in play.
        control_off: The dword holding the mask of what owns the player's control; zero when the player has it.
        render_gate: The byte that is non-zero once the player is drawn.
        movie_flag: The dword that is ``movie_playing`` while a Bink movie plays.
        movie_playing: The movie flag's value while a movie plays.
        menu_world: The dword holding the pause menu's world, zero-based.
        menu_slot: The dword holding its task slot, zero-based.
        menu_start_world: The world the pause menu opens on when the game opens it.
        menu_scenes: The pause menu's table of scenes, a row per world, filled when the game boots.
        menu_row_stride: The size of a row.
        menu_slot_stride: The size of a slot in a row, which starts with the scene's four characters.
        cheats: The cheat entry.
        warp_delay_frames: How long a level must have been in play before the harness warps out of it.
        action_polls: How many polls a press has to show its effect before it is sent again.
        warp_polls: How many polls the confirmed warp has to begin loading.
    """

    modes: GameModes
    playing: int
    control_off: int
    render_gate: int
    movie_flag: int
    movie_playing: int
    menu_world: int
    menu_slot: int
    menu_start_world: int
    menu_scenes: int
    menu_row_stride: int
    menu_slot_stride: int
    cheats: Cheats
    warp_delay_frames: int
    action_polls: int
    warp_polls: int


class Ready(StrEnum):
    """The signal that says a scene's player is ready for the next step."""

    FIRST_FRAME = "first_frame"
    CONTROL = "control"
    DRAWN_AND_CONTROL = "drawn_and_control"


@dataclass(frozen=True)
class SceneClass:
    """A class of scenes that become ready the same way.

    Attributes:
        name: What a recording calls the class.
        scenes: The scenes in it.
        ready: The signal that ends the wait.
        settle_frames: How many frames the signal must hold.
    """

    name: str
    scenes: tuple[str, ...]
    ready: Ready
    settle_frames: int


@dataclass(frozen=True)
class SceneClasses:
    """The scene classes, and the class of every scene in none of them.

    Attributes:
        classes: The classes with scenes.
        other: The class of every other scene.
        stall_frames: How many frames without the draw (``undrawn``) or without control (``control_off``) end a wait.
    """

    classes: tuple[SceneClass, ...]
    other: SceneClass
    stall_frames: int

    def of(self, scene: str) -> SceneClass:
        """The class of ``scene``."""
        return next((found for found in self.classes if scene in found.scenes), self.other)


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
    input: Input
    navigation: Navigation
    scene_classes: SceneClasses

    @property
    def digest(self) -> str:
        """A hash of the whole profile, for a run's manifest."""
        canonical = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
