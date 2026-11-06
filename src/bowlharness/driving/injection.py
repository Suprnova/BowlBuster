"""Resolving an injection's target in the live load."""

import struct
from dataclasses import dataclass

from bowlharness.driving.request import ADDRESS, ASSET, LIVE, Target
from bowlharness.profiles.profile import PlatformProfile
from bowlharness.recording.observe import Read, u32
from bowlharness.target import TargetError

NO_BASE = "no base"
ASSET_ID_MISMATCH = "asset id mismatch"
NO_LOOKUP_ENTRY = "no lookup entry"
UNREADABLE = "unreadable"


@dataclass(frozen=True)
class Resolved:
    """A target found: the anchor the injection's words are laid against."""

    anchor: int


@dataclass(frozen=True)
class Unresolved:
    """A target the load doesn't hold, and why: ``no base``, ``asset id mismatch``, ``no lookup entry`` or
    ``unreadable``."""

    reason: str


def resolve(target: Target, read: Read, profile: PlatformProfile) -> Resolved | Unresolved:
    """Finds where ``target`` falls in the live load, reading only through ``read``.

    The scene's base array and the lookup table are each read once.
    """
    try:
        found = _resolve(target, read, profile)
    except TargetError, struct.error:
        return Unresolved(UNREADABLE)
    return Resolved(found.anchor & 0xFFFFFFFF) if isinstance(found, Resolved) else found


def _resolve(target: Target, read: Read, profile: PlatformProfile) -> Resolved | Unresolved:
    if target.kind == ADDRESS:
        return Resolved(target.offset)
    assert target.id is not None
    objects = profile.objects
    if target.kind in (ASSET, LIVE):
        scene = u32(read, profile.globals.scene_pointer)
        count = u32(read, scene + objects.base_count)
        pointers = struct.unpack(f"<{count}I", read(u32(read, scene + objects.base_array), count * 4))
        base = next((p for p in pointers if p and u32(read, p + objects.base_id) == target.id), None)
        if base is None:
            return Unresolved(NO_BASE)
        if target.kind == LIVE:
            return Resolved(base + target.offset)
        asset = u32(read, base + objects.base_asset)
        if asset == 0 or u32(read, asset + objects.asset_id) != target.id:
            return Unresolved(ASSET_ID_MISMATCH)
        return Resolved(asset + target.offset)
    table = u32(read, objects.lookup)
    entries = read(table, objects.lookup_count * objects.lookup_stride)
    index = next(
        (
            i
            for i in range(objects.lookup_count)
            if struct.unpack_from("<I", entries, i * objects.lookup_stride)[0] == target.id
        ),
        None,
    )
    return (
        Unresolved(NO_LOOKUP_ENTRY)
        if index is None
        else Resolved(table + index * objects.lookup_stride + target.offset)
    )
