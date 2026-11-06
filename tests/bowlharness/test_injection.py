import struct

import pytest

from bowlharness.backends.mock import MockTarget
from bowlharness.driving.injection import Resolved, Unresolved, resolve
from bowlharness.driving.request import Target
from bowlharness.profiles import XBOX_NTSC_U
from bowlharness.profiles.profile import PlatformProfile

PROFILE = XBOX_NTSC_U
OBJECTS = PROFILE.objects
SCENE, ARRAY, BASE, ASSET, TABLE = 0x500000, 0x501000, 0x502000, 0x503000, 0x510000
ID = 0x1A2B3C4D


def words(address: int, *values: int) -> dict[int, bytes]:
    return {address: struct.pack(f"<{len(values)}I", *values)}


def memory(
    *, base_id: int = ID, asset_id: int = ID, entry: int | None = 7, profile: PlatformProfile = PROFILE
) -> dict[int, bytes]:
    objects = profile.objects
    pointers = {profile.globals.scene_pointer: struct.pack("<I", SCENE)}
    scene = words(SCENE + objects.base_count, 2) | words(SCENE + objects.base_array, ARRAY)
    array = words(ARRAY, 0, BASE)
    base = words(BASE + objects.base_id, base_id) | words(BASE + objects.base_asset, ASSET)
    asset = words(ASSET + objects.asset_id, asset_id)
    table = bytearray(objects.lookup_count * objects.lookup_stride)
    if entry is not None:
        struct.pack_into("<II", table, entry * objects.lookup_stride, ID, 0x520000)
    lookup = words(objects.lookup, TABLE) | {TABLE: bytes(table)}
    merged: dict[int, bytes] = {}
    for part in (pointers, scene, array, base, asset, lookup):
        for address, data in part.items():
            merged.update({address + i: bytes([byte]) for i, byte in enumerate(data)})
    return merged


def resolved(target: Target, content: dict[int, bytes]) -> Resolved | Unresolved:
    return resolve(target, MockTarget([], content).read, PROFILE)


@pytest.mark.parametrize(
    ("target", "anchor"),
    [
        (Target("asset", ID, 0x38), ASSET + 0x38),
        (Target("asset", ID, -8), ASSET - 8),
        (Target("live", ID, 0x10), BASE + 0x10),
        (Target("lookup", ID, -0x38), TABLE + 7 * 8 - 0x38),
        (Target("lookup", ID, 0), TABLE + 7 * 8),
        (Target("address", None, 0x2B1000), 0x2B1000),
    ],
)
def test_each_kind_resolves_to_its_anchor(target: Target, anchor: int) -> None:
    assert resolved(target, memory()) == Resolved(anchor)


def test_an_anchor_wraps_to_32_bits() -> None:
    assert resolved(Target("live", ID, -BASE - 4), memory()) == Resolved(0xFFFFFFFC)


def test_an_asset_whose_own_id_differs_is_a_mismatch() -> None:
    assert resolved(Target("asset", ID, 0), memory(asset_id=0xDEAD)) == Unresolved("asset id mismatch")


def test_a_live_base_does_not_check_its_asset() -> None:
    assert resolved(Target("live", ID, 0), memory(asset_id=0xDEAD)) == Resolved(BASE)


@pytest.mark.parametrize("kind", ["asset", "live"])
def test_an_id_no_base_has_is_no_base(kind: str) -> None:
    assert resolved(Target(kind, ID, 0), memory(base_id=0xBEEF)) == Unresolved("no base")


def test_an_id_the_table_lacks_is_no_lookup_entry() -> None:
    assert resolved(Target("lookup", ID, 0), memory(entry=None)) == Unresolved("no lookup entry")


@pytest.mark.parametrize("kind", ["asset", "live", "lookup"])
def test_unmapped_memory_is_unreadable(kind: str) -> None:
    assert resolved(Target(kind, ID, 0), {}) == Unresolved("unreadable")
