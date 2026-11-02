"""Reads the game's state from guest memory: heap 0 and the worn costumes."""

import struct
from collections.abc import Callable
from typing import Any

from bowlharness.profiles.profile import Costumes, Heap, Layers

type Read = Callable[[int, int], bytes]


def u32(read: Read, address: int) -> int:
    """Reads a dword."""
    return struct.unpack("<I", read(address, 4))[0]


def tag(word: int) -> str:
    """The four characters a dword holds, in memory order."""
    return struct.pack("<I", word).decode("ascii")


def heap0_state(read: Read, heap: Heap) -> dict[str, Any]:
    """Heap 0's depth, the depth states up to the current depth, and the last block allocated."""
    descriptor = read(heap.descriptors, heap.stride)
    (depth,) = struct.unpack_from("<H", descriptor, heap.depth_offset)
    states = []
    for index in range(depth + 1):
        offset = heap.states_offset + index * heap.state_stride
        (cursor,) = struct.unpack_from("<I", descriptor, offset + heap.cursor_offset)
        (blocks,) = struct.unpack_from("<H", descriptor, offset + heap.blocks_offset)
        (used,) = struct.unpack_from("<I", descriptor, offset + heap.used_offset)
        (wasted,) = struct.unpack_from("<I", descriptor, offset + heap.wasted_offset)
        states.append({"cursor": cursor, "blocks": blocks, "used": used, "wasted": wasted})
    (header,) = struct.unpack_from("<I", descriptor, heap.last_block_offset)
    last_block = None
    if header:
        block = read(header, max(heap.block_address_offset, heap.block_size_offset) + 4)
        (address,) = struct.unpack_from("<I", block, heap.block_address_offset)
        (size,) = struct.unpack_from("<I", block, heap.block_size_offset)
        last_block = {"address": address, "size": size}
    return {"depth": depth, "states": states, "last_block": last_block}


def worn_archives(read: Read, costumes: Costumes) -> dict[str, str | None]:
    """The player archive tag worn by each character: the first enabled entry of the costume table."""
    count = u32(read, costumes.count)
    table = read(costumes.table, count * costumes.stride)
    extras = read(costumes.extras, u32(read, costumes.extras_count) * costumes.extra_stride)
    cheats = u32(read, costumes.cheat_mask)
    worn: dict[str, str | None] = dict.fromkeys(costumes.characters)

    for index in range(count):
        offset = index * costumes.stride
        (archive,) = struct.unpack_from("<I", table, offset)
        (character,) = struct.unpack_from("<I", table, offset + costumes.character_offset)
        (mask,) = struct.unpack_from("<I", table, offset + costumes.mask_offset)
        if index < costumes.extra_entries:
            enabled = _extra_state(extras, costumes, index + 1) != 0
        else:
            enabled = mask & cheats != 0
        if enabled and character < len(costumes.characters) and worn[costumes.characters[character]] is None:
            worn[costumes.characters[character]] = tag(archive)
    return worn


def _extra_state(extras: bytes, costumes: Costumes, extra_id: int) -> int:
    for offset in range(0, len(extras), costumes.extra_stride):
        if extras[offset] == costumes.extra_kind and extras[offset + 1] == extra_id:
            return extras[offset + costumes.extra_state_offset]
    return 0


def loading_layer(read: Read, layers: Layers) -> dict[str, Any]:
    """The archive and layer the loader is loading: the archive's file name without its extension, and the layer's
    position in the archive's layer array. Raises ``ValueError`` when the loader holds no such layer."""
    archive = u32(read, layers.archive)
    layer = u32(read, layers.layer)
    if not (archive and layer):
        raise ValueError("the loader holds no layer")
    name = read(archive + layers.name_offset, layers.name_size).split(b"\0")[0].decode("ascii")
    count = u32(read, archive + layers.count_offset)
    array = u32(read, archive + layers.layers_offset)
    pointers = struct.unpack(f"<{count}I", read(array, 4 * count))
    return {"archive": name.removesuffix(layers.extension), "layer": pointers.index(layer)}
