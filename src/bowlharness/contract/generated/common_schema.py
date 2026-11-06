# Generated from schema/ by scripts/generate_contract.py. Do not edit; change the schema and run it again.

from dataclasses import dataclass
from typing import Any, Literal

type Common = Any
"""
Definitions that requests and results share.
"""


type Scene = str
"""
A scene's four-character tag, as the game names it.
"""


type Hex = str
"""
Bytes as lower-case hexadecimal, two digits per byte.
"""


type Sha256 = str
"""
A SHA-256 digest as lower-case hexadecimal.
"""


type SceneSelection = Literal["all", "none"] | list[Scene]
"""
Which scenes something applies to: all, none, or the listed scenes.
"""


@dataclass(frozen=True, kw_only=True)
class Observe:
    """
    What a recording logs.
    """

    heap_events: SceneSelection | None = None
    """
    The scenes whose heap events are logged. Every scene init logs its heap state.
    """
    cutoff_captures: SceneSelection | None = None
    """
    The scenes captured at their cutoff.
    """
    capture_budget: int | None = None
    """
    The most captures a run takes, or null for no limit. A crash or a hang is always captured.
    """


@dataclass(frozen=True, kw_only=True)
class InputPolicy:
    """
    How long the harness holds and releases each press, in polls of the controller.
    """

    hold: int | None = None
    """
    Polls a press is held for.
    """
    release: int | None = None
    """
    Polls a press is released for before the next.
    """


@dataclass(frozen=True, kw_only=True)
class Window:
    """
    A length of time, in guest frames or in wall-clock seconds.
    """

    unit: Literal["guest-frames", "wall-seconds"]
    """
    What the value counts.
    """
    value: float
    """
    How many of the unit.
    """


@dataclass(frozen=True, kw_only=True)
class DepthState:
    """
    One depth state of a heap descriptor.
    """

    cursor: int
    """
    The next free address.
    """
    blocks: int
    """
    How many blocks it holds.
    """
    used: int
    """
    The bytes used.
    """
    wasted: int
    """
    The bytes wasted.
    """


@dataclass(frozen=True, kw_only=True)
class Block:
    """
    A heap block: its address and size.
    """

    address: int
    """
    Where the block starts.
    """
    size: int
    """
    The block's size in bytes.
    """


@dataclass(frozen=True, kw_only=True)
class HeapState:
    """
    Heap 0 as a scene init found it, spelled as the scene_init event spells it.
    """

    depth: int
    """
    The current depth.
    """
    states: list[DepthState]
    """
    The depth states up to the current depth.
    """
    last_block: Block | None
    """
    The block last allocated, or null when there is none.
    """


@dataclass(frozen=True, kw_only=True)
class Top:
    """
    Heap 0's cursor and depth.
    """

    cursor: int
    """
    The cursor.
    """
    depth: int
    """
    The depth.
    """


type ObjectId = str
"""
An object's id as the game names it: 0x and up to eight hexadecimal digits.
"""


@dataclass(frozen=True, kw_only=True)
class ObjectOffset:
    id: ObjectId
    offset: int
    """
    Where S falls from the object, in signed bytes.
    """


@dataclass(frozen=True, kw_only=True)
class AssetTarget:
    """
    The asset of the live base with the id, plus the offset.
    """

    asset: ObjectOffset


@dataclass(frozen=True, kw_only=True)
class LiveTarget:
    """
    The live base with the id, plus the offset.
    """

    live: ObjectOffset


@dataclass(frozen=True, kw_only=True)
class LookupTarget:
    """
    The lookup table's entry for the id, plus the offset.
    """

    lookup: ObjectOffset


@dataclass(frozen=True, kw_only=True)
class AddressTarget:
    """
    An address in guest memory.
    """

    address: int


@dataclass(frozen=True, kw_only=True)
class Value:
    """
    Bytes written at an offset from the anchor.
    """

    offset: int
    """
    Where the bytes start, in signed bytes from the anchor.
    """
    hex: str
    """
    Bytes as lower-case hexadecimal, two digits per byte.
    """


@dataclass(frozen=True, kw_only=True)
class Injection:
    """
    Words written at a target in the load. Without words or values, the footprint is written.
    """

    target: AssetTarget | LiveTarget | LookupTarget | AddressTarget
    """
    Where S would be: the anchor the writes are laid against.
    """
    words: list[int] | None = None
    """
    The footprint's words to write, by their offsets from the anchor. Not with values.
    """
    values: list[Value] | None = None
    """
    Explicit bytes in place of the footprint. Not with words.
    """
