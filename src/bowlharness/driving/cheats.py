"""Reads the game's cheat table and works out which codes a step must enter."""

import struct
from dataclasses import dataclass
from functools import cache

from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.observe import Read, costume_entries, u32


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

    @property
    def text(self) -> str:
        """The code as a request spells it: ``X`` and ``Y`` separated by spaces."""
        return " ".join(press.upper() for press in self.presses)

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


def plan_codes(
    read: Read, profile: PlatformProfile, requested: tuple[str, ...], costumes: tuple[str, ...] | None
) -> list[Code]:
    """The codes to enter, in order: the ``requested`` ones, then those that leave exactly ``costumes`` worn.

    A requested code that doesn't change the cheat mask is left out, and so is a costume that is already as wanted.
    ``costumes`` is ``None`` when no costume is wanted of this step, so none is toggled.

    Raises:
        ValueError: No row enters a requested code, or a costume isn't one a cheat can give.
    """
    table = cache(lambda: read_codes(read, profile))
    mask = u32(read, profile.costumes.cheat_mask)
    plan: list[Code] = []

    def enter(code: Code) -> None:
        nonlocal mask
        plan.append(code)
        mask = code.apply(mask)

    for text in requested:
        code = next((code for code in table() if code.text == text), None)
        if code is None:
            raise ValueError(f"no cheat is entered with {text}")
        if code.toggles or not mask & code.bit:
            enter(code)
    if costumes is None:
        return plan
    entries = costume_entries(read, profile.costumes)
    for tag in costumes:
        if not any(entry.tag == tag and not entry.extra for entry in entries):
            raise ValueError(f"{tag} is not a costume a cheat gives")
    for entry in (entry for entry in entries if not entry.extra):
        if bool(entry.mask & mask) == (entry.tag in costumes):
            continue
        code = next((code for code in table() if code.toggles and code.bit & entry.mask), None)
        if code is None:
            raise ValueError(f"no cheat toggles {entry.tag}")
        enter(code)
    return plan
