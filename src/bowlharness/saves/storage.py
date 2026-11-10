"""The working copy of a library image that a save run plays on.

The game writes to its storage image (an autosave at every token once a save is loaded), so no run plays on a library
image: each save run gets a fresh copy at ``<saves>/work/<instance>/``, the one place the harness overwrites one.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from bowlharness.saves.library import STORAGE, WORK, Image, Library, LibraryError, Save, check_name


@dataclass(frozen=True)
class Storage:
    """A fresh working copy, and the save and image it came from.

    Attributes:
        path: The working copy.
        save: The save the run loads.
        image: The library image the copy was made from.
    """

    path: Path
    save: Save
    image: Image

    def record(self) -> dict[str, object]:
        """What the run's manifest records of the save: its name, slot, image and the image's hash when added."""
        return {
            "name": self.save.name,
            "slot": self.save.slot,
            "image": self.image.name,
            "storage_sha256": self.image.sha256,
        }


def work_folder(root: Path, instance: str) -> Path:
    """The folder an instance's working copy lives in.

    Raises:
        LibraryError: The instance's name isn't a plain name, or the folder would lie outside ``<root>/work``.
    """
    check_name("instance", instance)
    work = (root / WORK).resolve()
    folder = (work / instance).resolve()
    if folder.parent != work:
        raise LibraryError(f"the working copy for {instance} would lie outside {work}")
    return folder


def prepare(library: Library, save_name: str, instance: str, running: list[str]) -> Storage:
    """Copies the image holding ``save_name`` over ``instance``'s working copy.

    Args:
        library: The library.
        save_name: The save the run loads.
        instance: The emulator instance the run is leased to.
        running: The xemu processes running, any of which may hold the working copy.

    Raises:
        LibraryError: xemu is running, the library has no such save, or the copy's size isn't the image's.
    """
    if running:
        raise LibraryError(f"xemu is running (process {', '.join(running)}), and may hold the working copy")
    if (save := library.saves.get(save_name)) is None:
        raise LibraryError(f"the library has no save named {save_name}")
    image = library.image_of(save)
    folder = work_folder(library.root, instance)
    folder.mkdir(parents=True, exist_ok=True)
    copy = folder / STORAGE
    shutil.copyfile(image.storage, copy)
    if (size := copy.stat().st_size) != image.size:
        raise LibraryError(f"image {image.name} is damaged: it is {size} bytes, and its image.json says {image.size}")
    return Storage(copy, save, image)
