import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bowlharness.__main__ import main
from bowlharness.saves.commands import add_image, describe, parse_saves
from bowlharness.saves.library import INDEX, STORAGE, Library, LibraryError, Save
from bowlharness.saves.storage import prepare, work_folder

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
BYTES = b"not a real image, only bytes standing in for one"


def image_file(folder: Path, content: bytes = BYTES) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "source.qcow2"
    path.write_bytes(content)
    return path


def saves(*names: str) -> tuple[Save, ...]:
    return tuple(Save(name, "", slot, "BB02", f"about {name}") for slot, name in enumerate(names, start=1))


def library_with(tmp_path: Path, name: str = "played-1", *names: str) -> Path:
    root = tmp_path / "library"
    add_image(root, image_file(tmp_path / "source"), name, saves(*(names or ("base",))), [], NOW)
    return root


def test_an_added_image_lists_its_saves_by_name(tmp_path: Path) -> None:
    root = library_with(tmp_path, "played-1", "base", "time")

    library = Library(root)

    assert library.saves["time"] == Save("time", "played-1", 2, "BB02", "about time")


def test_an_added_image_is_a_byte_copy_hashed_in_its_index(tmp_path: Path) -> None:
    root = library_with(tmp_path)

    image = Library(root).images["played-1"]

    assert image.storage.read_bytes() == BYTES
    assert image.sha256 == hashlib.sha256(BYTES).hexdigest() and image.size == len(BYTES)


def test_adding_leaves_the_source_where_it_was(tmp_path: Path) -> None:
    source = image_file(tmp_path / "source")

    add_image(tmp_path / "library", source, "played-1", saves("base"), [], NOW)

    assert source.read_bytes() == BYTES


def test_adding_is_refused_while_xemu_runs(tmp_path: Path) -> None:
    with pytest.raises(LibraryError, match="process 4242"):
        add_image(tmp_path / "library", image_file(tmp_path), "played-1", saves("base"), ["4242"], NOW)


def test_an_image_name_already_in_the_library_is_refused(tmp_path: Path) -> None:
    root = library_with(tmp_path, "played-1", "base")

    with pytest.raises(LibraryError, match="already has a folder named played-1"):
        add_image(root, image_file(tmp_path / "other"), "played-1", saves("ring"), [], NOW)


def test_a_save_name_already_in_the_library_is_refused(tmp_path: Path) -> None:
    root = library_with(tmp_path, "played-1", "base")

    with pytest.raises(LibraryError, match="already has a save named base"):
        add_image(root, image_file(tmp_path / "other"), "played-2", saves("base"), [], NOW)


def test_the_index_is_written_last_so_a_failed_copy_is_not_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_copy(source: Path, target: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("shutil.copyfile", failing_copy)

    with pytest.raises(OSError):
        add_image(tmp_path / "library", image_file(tmp_path / "source"), "played-1", saves("base"), [], NOW)

    assert not (tmp_path / "library" / "played-1" / INDEX).exists() and Library(tmp_path / "library").saves == {}


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        ((Save("base", "", 4, "BB02"),), "slots 1 to 3"),
        ((Save("base", "", 1, "BB2"),), "four-character scene"),
        ((Save("Base", "", 1, "BB02"),), "lower-case"),
        ((Save("base", "", 1, "BB02"), Save("time", "", 1, "BB02")), "slot 1"),
        ((Save("base", "", 1, "BB02"), Save("base", "", 2, "BB02")), "name base"),
    ],
)
def test_bad_saves_are_refused(tmp_path: Path, bad: tuple[Save, ...], message: str) -> None:
    with pytest.raises(LibraryError, match=message):
        add_image(tmp_path / "library", image_file(tmp_path), "played-1", bad, [], NOW)


def test_two_images_holding_one_save_name_are_refused_naming_both(tmp_path: Path) -> None:
    root = library_with(tmp_path, "played-1", "base")
    copy = root / "played-2"
    copy.mkdir()
    (copy / INDEX).write_text((root / "played-1" / INDEX).read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(LibraryError, match="base is in both played-1 and played-2"):
        Library(root)


def test_an_index_that_does_not_read_is_refused_naming_its_file(tmp_path: Path) -> None:
    root = library_with(tmp_path)
    (root / "played-1" / INDEX).write_text("{", encoding="utf-8")

    with pytest.raises(LibraryError, match=r"played-1[\\/]image\.json doesn't read"):
        Library(root)


def test_a_missing_library_is_refused() -> None:
    with pytest.raises(LibraryError, match="no save library"):
        Library(Path("Z:/no/such/library"))


def test_prepare_copies_the_saves_image_into_the_instances_work_folder(tmp_path: Path) -> None:
    root = library_with(tmp_path, "played-1", "base")

    storage = prepare(Library(root), "base", "inst3", [])

    assert storage.path == (root / "work" / "inst3" / STORAGE).resolve() and storage.path.read_bytes() == BYTES
    assert storage.save.slot == 1 and storage.image.name == "played-1"


def test_each_prepare_starts_from_an_untouched_copy(tmp_path: Path) -> None:
    root = library_with(tmp_path, "played-1", "base")
    library = Library(root)
    prepare(library, "base", "inst3", []).path.write_bytes(b"written by the game")

    storage = prepare(library, "base", "inst3", [])

    assert storage.path.read_bytes() == BYTES and library.images["played-1"].storage.read_bytes() == BYTES


def test_prepare_is_refused_while_xemu_runs(tmp_path: Path) -> None:
    library = Library(library_with(tmp_path))

    with pytest.raises(LibraryError, match="process 4242"):
        prepare(library, "base", "inst3", ["4242"])


def test_prepare_refuses_a_save_the_library_does_not_hold(tmp_path: Path) -> None:
    library = Library(library_with(tmp_path))

    with pytest.raises(LibraryError, match="no save named missing"):
        prepare(library, "missing", "inst3", [])


def test_a_damaged_image_is_refused(tmp_path: Path) -> None:
    root = library_with(tmp_path)
    (root / "played-1" / STORAGE).write_bytes(BYTES[:-1])

    with pytest.raises(LibraryError, match="played-1 is damaged"):
        prepare(Library(root), "base", "inst3", [])


@pytest.mark.parametrize("instance", ["..", "a/b", "work", ""])
def test_a_working_copy_outside_the_work_folder_is_refused(tmp_path: Path, instance: str) -> None:
    with pytest.raises(LibraryError):
        work_folder(tmp_path, instance)


def test_save_arguments_name_slot_scene_and_about() -> None:
    parsed = parse_saves(["1:base:bb02", "2:time:BB02"], ["time: Main done, Time next"])

    assert parsed == (Save("base", "", 1, "BB02"), Save("time", "", 2, "BB02", "Main done, Time next"))


@pytest.mark.parametrize(
    ("entries", "abouts"), [(["base:BB02"], []), (["x:base:BB02"], []), (["1:base:BB02"], ["time:x"])]
)
def test_malformed_save_arguments_are_refused(entries: list[str], abouts: list[str]) -> None:
    with pytest.raises(LibraryError):
        parse_saves(entries, abouts)


def test_the_listing_has_a_line_per_save(tmp_path: Path) -> None:
    root = library_with(tmp_path, "played-1", "base", "time")

    lines = describe(Library(root))

    assert lines == ["base  played-1  slot 1  BB02  about base", "time  played-1  slot 2  BB02  about time"]


def test_saves_commands_run_without_gdb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    root = library_with(tmp_path, "played-1", "base")
    monkeypatch.setattr(sys, "argv", ["bowlharness", "saves", "list", "--saves", str(root)])
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.delenv("BOWL_GDB", raising=False)

    code = main()

    assert code == 0 and capsys.readouterr().out.startswith("base  played-1  slot 1")


def test_the_index_holds_what_was_added(tmp_path: Path) -> None:
    root = library_with(tmp_path, "played-1", "base")

    document = json.loads((root / "played-1" / INDEX).read_text(encoding="utf-8"))

    assert document["added"] == NOW.isoformat() and document["saves"] == [
        {"slot": 1, "name": "base", "scene": "BB02", "about": "about base"}
    ]
