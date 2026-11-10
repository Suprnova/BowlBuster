"""Finds a menu's rows and reads which one the cursor is on."""

import struct

from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.observe import Read, u32
from bowlharness.target import TargetError


def find_focus(read: Read, profile: PlatformProfile) -> list[int]:
    """The addresses of the highlight bytes of the scene's menu rows, in the order of the scene's base array.

    Empty when the scene has no menu rows or its base array doesn't read.
    """
    focus, objects = profile.navigation.focus, profile.objects
    try:
        scene = u32(read, profile.globals.scene_pointer)
        count = u32(read, scene + objects.base_count)
        bases = struct.unpack(f"<{count}I", read(u32(read, scene + objects.base_array), 4 * count))
    except TargetError:
        return []
    return [base + focus.flag for base in bases if base and _is_row(read, base + focus.type_offset, focus.type)]


def _is_row(read: Read, address: int, row_type: int) -> bool:
    try:
        return u32(read, address) == row_type
    except TargetError:
        return False


def row_ids(read: Read, profile: PlatformProfile, flags: list[int]) -> list[int]:
    """The ids of the rows whose highlight bytes are at ``flags``."""
    focus = profile.navigation.focus
    return [u32(read, address - focus.flag + focus.id) for address in flags]


def highlighted(read: Read, flags: list[int]) -> int:
    """A mask with bit ``n`` set while the row whose highlight byte is ``flags[n]`` is highlighted."""
    return sum(1 << n for n, address in enumerate(flags) if read(address, 1)[0] & 1)
