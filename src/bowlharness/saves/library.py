"""The save library: xemu storage images, each holding the game's saves in its slots.

```
<saves>/<image>/image.json        the image's identity and its saves; written last, so a half-added image isn't listed
<saves>/<image>/xbox_hdd.qcow2    the storage image; never run and never changed
<saves>/work/<instance>/          an instance's working copy (storage.py)
```

A save's name is unique across the library and always means the same bytes, so a request names a save, never a path.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

INDEX = "image.json"
STORAGE = "xbox_hdd.qcow2"
WORK = "work"
SLOTS = range(1, 4)

_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
_SCENE = re.compile(r"[A-Z0-9]{4}")


class LibraryError(ValueError):
    """Something about the library, or a change asked of it, that the harness refuses; the message says what."""


@dataclass(frozen=True)
class Save:
    """A save in one slot of a library image.

    Attributes:
        name: The save's name, unique across the library.
        image: The name of the image that holds it.
        slot: Its save slot, 1 to 3.
        scene: The scene it loads into.
        about: What was played to make it: tasks, tokens, which Extras are unlocked.
    """

    name: str
    image: str
    slot: int
    scene: str
    about: str = ""


@dataclass(frozen=True)
class Image:
    """A storage image in the library and the saves it holds.

    Attributes:
        name: The image's name, which is its folder's.
        folder: Its folder.
        sha256: The storage image's SHA-256, taken when it was added.
        size: The storage image's size in bytes.
        added: When it was added, in ISO 8601.
        source: The file it was copied from.
        saves: Its saves, by slot.
    """

    name: str
    folder: Path
    sha256: str
    size: int
    added: str
    source: str
    saves: tuple[Save, ...]

    @property
    def storage(self) -> Path:
        """The storage image."""
        return self.folder / STORAGE

    def to_json(self) -> dict[str, Any]:
        """The image as its ``image.json`` holds it."""
        return {
            "sha256": self.sha256,
            "bytes": self.size,
            "added": self.added,
            "source": self.source,
            "saves": [{"slot": s.slot, "name": s.name, "scene": s.scene, "about": s.about} for s in self.saves],
        }


def check_name(kind: str, name: str) -> None:
    """Refuses a name that isn't lower-case letters, digits and hyphens, which also keeps it one path segment."""
    if not _NAME.fullmatch(name) or name == WORK:
        raise LibraryError(f"{kind} name {name!r} must be lower-case letters, digits and hyphens, and not {WORK!r}")


def check_saves(saves: tuple[Save, ...]) -> None:
    """Refuses saves with a bad name, slot or scene, or two in one slot or under one name."""
    for save in saves:
        check_name("save", save.name)
        if save.slot not in SLOTS:
            raise LibraryError(f"save {save.name} is in slot {save.slot}; the game has slots 1 to 3")
        if not _SCENE.fullmatch(save.scene):
            raise LibraryError(f"save {save.name} loads into {save.scene!r}, which isn't a four-character scene")
    for field in ("slot", "name"):
        values = [getattr(save, field) for save in saves]
        if repeated := sorted({str(value) for value in values if values.count(value) > 1}):
            raise LibraryError(f"more than one save has the {field} {', '.join(repeated)}")


def read_image(folder: Path) -> Image:
    """Reads the image in ``folder`` from its ``image.json``.

    Raises:
        LibraryError: The file doesn't read, or its saves don't pass :func:`check_saves`; the message names the file.
    """
    path = folder / INDEX
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        saves = tuple(
            Save(entry["name"], folder.name, entry["slot"], entry["scene"], entry.get("about", ""))
            for entry in document["saves"]
        )
        image = Image(
            folder.name, folder, document["sha256"], document["bytes"], document["added"], document["source"], saves
        )
        check_name("image", image.name)
        check_saves(saves)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise LibraryError(f"{path} doesn't read: {error}") from error
    return image


class Library:
    """The images and saves under a library folder.

    A folder without an ``image.json`` is an image still being added, and isn't listed; the ``work`` folder holds the
    instances' working copies.

    Args:
        root: The library folder.

    Raises:
        LibraryError: The folder doesn't exist, an ``image.json`` doesn't read, or two images hold a save of one name.
    """

    def __init__(self, root: Path) -> None:
        if not root.is_dir():
            raise LibraryError(f"there is no save library at {root}")
        self.root = root
        folders = sorted(f for f in root.iterdir() if f.is_dir() and f.name != WORK and (f / INDEX).is_file())
        self.images: dict[str, Image] = {image.name: image for image in map(read_image, folders)}
        self.saves: dict[str, Save] = {}
        for image in self.images.values():
            for save in image.saves:
                if (other := self.saves.get(save.name)) is not None:
                    raise LibraryError(f"save {save.name} is in both {other.image} and {image.name}")
                self.saves[save.name] = save

    def image_of(self, save: Save) -> Image:
        """The image that holds ``save``."""
        return self.images[save.image]
