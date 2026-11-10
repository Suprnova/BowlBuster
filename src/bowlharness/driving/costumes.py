"""Works out how a step leaves exactly the next step's costumes worn: cheat-costume codes, then Extras choices.

The costume table resolves a character to its first enabled entry: the Extras costumes (each enabled by its ``Extra``
row's state byte) come before the cheat costumes (each by a bit of the cheat mask). Choosing an Extras row toggles its
byte, and turning one on, like entering a cheat costume's code, runs the game's take-off routine, which clears other
costumes. That routine is given the Extras row's id where it expects a table entry, so Plain Sponge and Plain Patrick
take off the other character's costumes instead of their own (mechanism.md 1.2). The planner simulates it exactly, and
looks for an order of Extras choices that ends in the wanted costumes.
"""

import struct
from dataclasses import dataclass, field, replace
from itertools import permutations

from bowlharness.driving.cheats import Code
from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.observe import CostumeEntry, Read, costume_entries, u32
from bowlharness.target import TargetError


@dataclass(frozen=True)
class CostumePlan:
    """What a step does to leave the next step's costumes worn.

    Attributes:
        codes: The cheat-costume codes to enter, in order, after the step's own cheats.
        extras: The rows of the ``Extra`` table to choose on the Extras screen, in order, after the codes.
    """

    codes: tuple[Code, ...] = ()
    extras: tuple[int, ...] = ()


@dataclass(frozen=True)
class _State:
    extras: tuple[bool, ...]
    mask: int
    trail: tuple[int, ...] = field(default=())


def plan_costumes(
    read: Read, profile: PlatformProfile, codes: list[Code], mask: int, wanted: tuple[str, ...]
) -> CostumePlan:
    """The codes and Extras choices that leave exactly ``wanted`` worn once the step's own cheats are in.

    Args:
        read: Reads guest memory.
        profile: The platform's addresses and constants.
        codes: The cheat table.
        mask: The cheat mask once the step's own cheats are entered.
        wanted: The archive tags the next step wears, at most one per character.

    Raises:
        ValueError: A costume no entry gives, an Extras costume the save hasn't unlocked, a cheat costume no code
            toggles, or wanted costumes no order of choices reaches.
    """
    costumes = profile.costumes
    entries = costume_entries(read, costumes)
    for tag in wanted:
        if not any(entry.tag == tag for entry in entries):
            raise ValueError(f"{tag} is not a costume the costume table gives")
    rows = _extra_rows(read, profile, len([entry for entry in entries if entry.extra]))
    state = _State(tuple(entry.enabled for entry in entries if entry.extra), mask)
    planned: list[Code] = []
    for index, entry in enumerate(entries):
        if entry.extra or bool(state.mask & entry.mask) == (entry.tag in wanted):
            continue
        code = next((code for code in codes if code.toggles and code.bit & entry.mask), None)
        if code is None:
            raise ValueError(f"no cheat toggles {entry.tag}")
        planned.append(code)
        state = _enter(entries, state, index, code.bit)
    off = [index for index, on in enumerate(state.extras) if on and entries[index].tag not in wanted]
    on = [index for index, now in enumerate(state.extras) if not now and entries[index].tag in wanted]
    if missing := [entries[index].tag for index in on if index not in rows]:
        raise ValueError(f"no Extra row gives {', '.join(missing)}")
    chests = u32(read, costumes.chest_count) if on else 0
    for index in on:
        if rows[index][1] > chests:
            raise ValueError(f"{entries[index].tag} is locked: it needs {rows[index][1]} chests, the save has {chests}")
    goal = _worn(entries, wanted)
    for order in permutations(on):
        end = state
        for index in (*off, *order):
            end = _choose(entries, end, index)
        if _worn_now(entries, end) == goal:
            return CostumePlan(tuple(planned), tuple(rows[index][0] for index in end.trail))
    raise ValueError(f"no order of Extras choices leaves {', '.join(wanted) or 'no costume'} worn")


def _extra_rows(read: Read, profile: PlatformProfile, count: int) -> dict[int, tuple[int, int]]:
    """Each Extras entry's ``Extra`` table row and the chest count that unlocks it, by the entry's index."""
    costumes = profile.costumes
    table = read(costumes.extras, u32(read, costumes.extras_count) * costumes.extra_stride)
    rows = {}
    for offset in range(0, len(table), costumes.extra_stride):
        kind, extra_id = table[offset], table[offset + 1]
        if kind == costumes.extra_kind and 1 <= extra_id <= count:
            rows[extra_id - 1] = (offset // costumes.extra_stride, table[offset + costumes.extra_unlock_offset])
    return rows


def _take_off(entries: list[CostumeEntry], state: _State, argument: int) -> _State:
    """The game's take-off routine (``0x44BD0``): entry ``argument``'s character loses every other costume."""
    character = entries[argument].character
    extras = tuple(
        on and not (index + 1 != argument and entries[index].character == character)
        for index, on in enumerate(state.extras)
    )
    mask = state.mask
    for index, entry in enumerate(entries):
        if not entry.extra and index != argument and entry.character == character:
            mask &= ~entry.mask
    return replace(state, extras=extras, mask=mask)


def _choose(entries: list[CostumeEntry], state: _State, index: int) -> _State:
    """Choosing an Extras costume's row: its byte toggles, and turning it on runs the take-off with its row's id."""
    extras = list(state.extras)
    extras[index] = not extras[index]
    chosen = replace(state, extras=tuple(extras), trail=(*state.trail, index))
    return _take_off(entries, chosen, index + 1) if extras[index] else chosen


def _enter(entries: list[CostumeEntry], state: _State, index: int, bit: int) -> _State:
    """Entering a cheat costume's code: its bit toggles, and turning it on runs the take-off with its own entry."""
    toggled = replace(state, mask=state.mask ^ bit)
    return _take_off(entries, toggled, index) if toggled.mask & bit else toggled


def _worn(entries: list[CostumeEntry], tags: tuple[str, ...]) -> dict[str | None, str | None]:
    worn: dict[str | None, str | None] = {entry.character: None for entry in entries}
    for entry in entries:
        if entry.tag in tags:
            worn[entry.character] = entry.tag
    return worn


def _worn_now(entries: list[CostumeEntry], state: _State) -> dict[str | None, str | None]:
    worn: dict[str | None, str | None] = {entry.character: None for entry in entries}
    extras = iter(state.extras)
    for entry in entries:
        enabled = next(extras) if entry.extra else bool(state.mask & entry.mask)
        if enabled and worn[entry.character] is None:
            worn[entry.character] = entry.tag
    return worn


def extra_row_state(read: Read, profile: PlatformProfile, row: int) -> int:
    """The state byte of row ``row`` of the ``Extra`` table: non-zero while that Extra is on."""
    costumes = profile.costumes
    word = u32(read, costumes.extras + row * costumes.extra_stride)
    return struct.pack("<I", word)[costumes.extra_state_offset]


def find_extras(read: Read, profile: PlatformProfile) -> int | None:
    """The Extras screen's controller: the object a base of the scene points to at the screen's controller offset, told
    apart by its vtable. ``None`` when no base points to one, or the scene's base array doesn't read."""
    extras, objects = profile.navigation.extras, profile.objects
    try:
        scene = u32(read, profile.globals.scene_pointer)
        count = u32(read, scene + objects.base_count)
        bases = struct.unpack(f"<{count}I", read(u32(read, scene + objects.base_array), 4 * count))
    except TargetError:
        return None
    for base in bases:
        if not base:
            continue
        try:
            controller = u32(read, base + extras.controller)
            if controller and u32(read, controller) == extras.vtable:
                return controller
        except TargetError:
            continue
    return None
