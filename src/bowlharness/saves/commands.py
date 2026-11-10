"""The ``saves`` commands, which manage the save library and need no emulator or gdb.

python -m bowlharness saves add --saves <library> --image <qcow2> --name <image>
    --save <slot>:<name>:<scene> [--save ...] [--about <name>:<text> ...]
python -m bowlharness saves list --saves <library>
"""

import argparse
import json
import shutil
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from bowlharness.backends.xemu import file_sha256, running_xemu
from bowlharness.saves.library import INDEX, STORAGE, Image, Library, LibraryError, Save, check_name, check_saves


def add_image(root: Path, source: Path, name: str, saves: tuple[Save, ...], running: list[str], now: datetime) -> Image:
    """Copies a storage image into the library as ``name``, with the saves it holds.

    It never moves or changes ``source``. ``image.json`` is written last, so an image whose copy failed isn't listed;
    its folder stays, and keeps the name taken until it is cleared by hand.

    Args:
        root: The library folder, made if it doesn't exist.
        source: The storage image to add.
        name: The image's name in the library.
        saves: The saves it holds; their ``image`` is replaced by ``name``.
        running: The xemu processes running, any of which may be writing the image.
        now: When it is added.

    Raises:
        LibraryError: xemu is running, a name is bad or taken, a save is refused, or ``source`` isn't a file.
    """
    if running:
        raise LibraryError(f"xemu is running (process {', '.join(running)}): close it before adding an image")
    check_name("image", name)
    saves = tuple(Save(save.name, name, save.slot, save.scene, save.about) for save in saves)
    if not saves:
        raise LibraryError(f"image {name} needs at least one --save")
    check_saves(saves)
    if not source.is_file():
        raise LibraryError(f"there is no storage image at {source}")
    root.mkdir(parents=True, exist_ok=True)
    library = Library(root)
    if (folder := root / name).exists():
        raise LibraryError(f"the library already has a folder named {name}")
    if taken := sorted(save.name for save in saves if save.name in library.saves):
        raise LibraryError(f"the library already has a save named {', '.join(taken)}")
    folder.mkdir()
    copy = folder / STORAGE
    shutil.copyfile(source, copy)
    image = Image(name, folder, file_sha256(copy), copy.stat().st_size, now.isoformat(), str(source.resolve()), saves)
    (folder / INDEX).write_text(json.dumps(image.to_json(), indent=2) + "\n", encoding="utf-8")
    return image


def parse_saves(entries: Sequence[str], abouts: Sequence[str]) -> tuple[Save, ...]:
    """The saves ``--save <slot>:<name>:<scene>`` and ``--about <name>:<text>`` describe, before they get an image."""
    saves = {}
    for entry in entries:
        parts = entry.split(":")
        if len(parts) != 3 or not parts[0].isdigit():
            raise LibraryError(f"--save {entry!r} should be <slot>:<name>:<scene>, such as 1:base:BB02")
        slot, name, scene = int(parts[0]), parts[1], parts[2].upper()
        saves[name] = Save(name, "", slot, scene)
    for about in abouts:
        name, colon, text = about.partition(":")
        if not colon or name not in saves:
            raise LibraryError(f"--about {about!r} should be <name>:<text>, naming one of the --save entries")
        saves[name] = Save(name, "", saves[name].slot, saves[name].scene, text.strip())
    return tuple(saves.values())


def describe(library: Library) -> list[str]:
    """One line per save: its name, image, slot, scene and what was played."""
    rows = [(s.name, s.image, f"slot {s.slot}", s.scene, s.about) for s in library.saves.values()]
    if not rows:
        return [f"no saves in {library.root}"]
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    return ["  ".join([*(row[i].ljust(widths[i]) for i in range(4)), row[4]]).rstrip() for row in rows]


def main(arguments: Sequence[str]) -> int:
    """Runs a ``saves`` command; a refusal ends it with its message."""
    parser = argparse.ArgumentParser(prog="python -m bowlharness saves")
    verbs = parser.add_subparsers(dest="verb", required=True)
    add = verbs.add_parser("add", help="copy a storage image and its saves into the library")
    add.add_argument("--saves", type=Path, required=True, help="the library folder")
    add.add_argument("--image", type=Path, required=True, help="the storage image to add")
    add.add_argument("--name", required=True, help="the image's name in the library")
    add.add_argument("--save", action="append", default=[], help="<slot>:<name>:<scene>, once per save")
    add.add_argument("--about", action="append", default=[], help="<name>:<text>, what was played to make a save")
    listing = verbs.add_parser("list", help="list the library's saves")
    listing.add_argument("--saves", type=Path, required=True, help="the library folder")
    found = parser.parse_args(arguments)
    try:
        if found.verb == "add":
            saves = parse_saves(found.save, found.about)
            image = add_image(found.saves, found.image, found.name, saves, running_xemu(), datetime.now(UTC))
            print(f"added {image.name} with {', '.join(save.name for save in image.saves)}")
        else:
            print("\n".join(describe(Library(found.saves))))
    except LibraryError as error:
        raise SystemExit(str(error)) from error
    return 0
