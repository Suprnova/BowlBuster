"""Reads the game's cheat table and works out which codes a step must enter."""

import struct
from dataclasses import dataclass
from functools import cache

from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.observe import Read, u32


@dataclass(frozen=True)
class Code:
    """A row of the cheat table.

    Attributes:
        presses: The buttons (``x`` or ``y``) the code is entered with, in order.
        bit: The bit it sets in the cheat mask, or toggles when it ``toggles``.
        toggles: Whether entering it again takes the bit off.
    """

    presses: tuple[str, ...]
    bit: int
    toggles: bool

    def apply(self, mask: int) -> int:
        """The cheat mask after the code is entered into ``mask``."""
        return mask ^ self.bit if self.toggles else mask | self.bit


def read_codes(read: Read, profile: PlatformProfile) -> list[Code]:
    """Reads every row of the cheat table. A press that is neither X nor Y reads as ``?``."""
    cheats, buttons = profile.navigation.cheats, profile.input.buttons
    named = {buttons.x: "x", buttons.y: "y"}
    half = cheats.history_length // 2
    codes = []
    for index in range(cheats.rows):
        row = read(cheats.table + index * cheats.row_stride, cheats.row_stride)
        (sequence,) = struct.unpack_from("<I", row, cheats.sequence_offset)
        (bit,) = struct.unpack_from("<I", row, cheats.mask_offset)
        (flags,) = struct.unpack_from("<I", row, cheats.flags_offset)
        history = struct.unpack(f"<{cheats.history_length}I", read(sequence, 4 * cheats.history_length))
        codes.append(
            Code(tuple(named.get(word, "?") for word in history[half:]), bit, bool(flags & cheats.toggle_flag))
        )
    return codes


def plan_codes(read: Read, profile: PlatformProfile, requested: tuple[str, ...]) -> list[Code]:
    """The codes of the ``requested`` cheats, in order, each by the table's row with the bit the profile gives its name.

    A code that doesn't change the cheat mask is left out. The costume codes are :func:`plan_costumes`'s.

    Raises:
        ValueError: No row sets a requested cheat's bit.
    """
    table = cache(lambda: read_codes(read, profile))
    mask = u32(read, profile.costumes.cheat_mask)
    plan: list[Code] = []
    for name in requested:
        bit = profile.navigation.cheats.bit(name)
        code = next((code for code in table() if code.bit == bit), None)
        if code is None:
            raise ValueError(f"no cheat sets {bit:#x}" if bit else f"no cheat is called {name}")
        if code.toggles or not mask & code.bit:
            plan.append(code)
            mask = code.apply(mask)
    return plan
