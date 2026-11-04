from dataclasses import fields, replace

from bowlharness.profiles import XBOX_NTSC_U
from bowlharness.profiles.profile import Point, Ready
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


def test_the_pad_read_is_in_the_code() -> None:
    first, last = XBOX_NTSC_U.code

    assert first <= XBOX_NTSC_U.points.pad_read.entry[0] < last


def test_every_button_has_its_own_mask() -> None:
    masks = [getattr(XBOX_NTSC_U.input.buttons, field.name) for field in fields(XBOX_NTSC_U.input.buttons)]

    assert len(set(masks)) == len(masks)


def test_the_cheat_entry_needs_both_triggers() -> None:
    buttons = XBOX_NTSC_U.input.buttons

    assert XBOX_NTSC_U.navigation.cheats.held == buttons.l | buttons.r


def test_every_paused_mode_is_a_menu_mode_or_listed() -> None:
    modes = XBOX_NTSC_U.navigation.modes

    assert {modes.boot_movies, modes.menu, modes.pause_menu} <= set(modes.paused) and modes.play not in modes.paused


def test_every_scene_class_has_a_signal_and_a_settle_count() -> None:
    classes = (*XBOX_NTSC_U.scene_classes.classes, XBOX_NTSC_U.scene_classes.other)

    assert all(isinstance(found.ready, Ready) and found.settle_frames > 0 for found in classes)


def test_no_scene_is_in_two_classes() -> None:
    scenes = [scene for found in XBOX_NTSC_U.scene_classes.classes for scene in found.scenes]

    assert len(set(scenes)) == len(scenes)


def test_a_scene_in_a_class_is_that_class_and_any_other_is_other() -> None:
    classes = XBOX_NTSC_U.scene_classes

    assert (classes.of("FB02").name, classes.of("BB02").name) == ("floating_block", "other")


def test_digest_changes_with_an_input_value() -> None:
    changed = replace(XBOX_NTSC_U, input=replace(XBOX_NTSC_U.input, hold_polls=7))

    assert changed.digest != XBOX_NTSC_U.digest


def test_every_named_cheat_has_its_own_name_and_bit() -> None:
    names, bits = zip(*XBOX_NTSC_U.navigation.cheats.names, strict=True)

    assert len(set(names)) == len(names) and len(set(bits)) == len(bits)


def test_a_cheat_the_profile_does_not_name_has_no_bit() -> None:
    assert XBOX_NTSC_U.navigation.cheats.bit("all-coins") is None


def test_the_bowl_storage_writes_lie_among_the_bowls_statics() -> None:
    first, last = XBOX_NTSC_U.globals.bowl_statics
    storage = XBOX_NTSC_U.bowl_storage

    assert all(first <= address <= last for address in (XBOX_NTSC_U.globals.sphere, storage.flag, storage.scale))
