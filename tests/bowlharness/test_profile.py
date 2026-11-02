from dataclasses import fields, replace

from bowlharness.profiles import XBOX_NTSC_U
from bowlharness.profiles.profile import Point
from bowlharness.recording.observe import tag


def all_points() -> dict[str, Point]:
    points = XBOX_NTSC_U.points
    return {field.name: getattr(points, field.name) for field in fields(points)}


def test_every_point_has_an_address() -> None:
    assert [name for name, point in all_points().items() if not (point.entry or point.returns)] == []


def test_every_point_lies_in_the_code() -> None:
    first, last = XBOX_NTSC_U.code
    addresses = [address for point in all_points().values() for address in (*point.entry, *point.returns)]

    assert all(first <= address < last for address in addresses)


def test_a_point_that_clobbers_its_arguments_reads_them_at_the_entry() -> None:
    pop = XBOX_NTSC_U.points.pop

    assert pop.entry and pop.returns and pop.args > 0


def test_digest_is_stable() -> None:
    assert XBOX_NTSC_U.digest == replace(XBOX_NTSC_U).digest


def test_digest_changes_with_the_profile() -> None:
    changed = replace(XBOX_NTSC_U, boot_scene="ORIG")

    assert changed.digest != XBOX_NTSC_U.digest


def test_a_tag_reads_with_its_first_character_most_significant() -> None:
    assert tag(0x42423032) == "BB02"
