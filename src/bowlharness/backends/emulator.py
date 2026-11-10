"""The emulator an instance runs its runs on, and which storage image each run gets.

A reset doesn't restore the storage image, and a loaded save writes to it, so a run that starts from a save gets the
emulator restarted on a fresh working copy of its image, and the run after one gets it restarted on the instance's own
storage. Any other run gets a reset.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from bowlharness.backends.xemu import derived_config
from bowlharness.driving.request import Request, check_save
from bowlharness.saves.library import Library
from bowlharness.saves.storage import prepare

SAVE = "save"
OWN_STORAGE = "own storage"


class EmulatorFault(RuntimeError):
    """The emulator was stopped and couldn't be started again; the message says why."""


class EmulatorControl(Protocol):
    """Starts, stops and resets one emulator, and says what a manifest records of it."""

    @property
    def restartable(self) -> bool:
        """Whether the harness started the emulator, and so can stop and start it; not when it attached."""
        ...

    def start(self, config: Path) -> None:
        """Starts the emulator on ``config``, connects to it and resets it."""
        ...

    def stop(self) -> None:
        """Disconnects and stops the emulator, and waits for its process to exit."""
        ...

    def reset(self) -> None:
        """Resets the guest."""
        ...

    def describe(self, config: Path) -> dict[str, Any]:
        """What a manifest records of the emulator, its configuration, the disc and the host."""
        ...

    def running(self) -> list[str]:
        """The ids of the xemu processes running."""
        ...


class Emulator:
    """Boots the guest for each run on the storage the run needs.

    Args:
        control: The emulator, already started on ``config`` or attached to.
        config: The instance's own configuration.
        instance: The instance's name, which names its working copy.
        library: The save library, or ``None`` when the harness was given none.
        environment: What the manifest records of the emulator as it was started.
        report: Told the reason of each restart: ``save`` or ``own storage``.
    """

    def __init__(
        self,
        control: EmulatorControl,
        config: Path,
        instance: str,
        library: Library | None,
        environment: dict[str, Any],
        report: Callable[[str], None],
    ) -> None:
        self._control = control
        self._config = config
        self._instance = instance
        self._library = library
        self._report = report
        self._own = True
        self.environment = environment

    def boot(self, request: Request) -> None:
        """Gives the guest a fresh boot on the storage ``request`` needs, and updates :attr:`environment`.

        Raises:
            ValueError: The request can't run here: its save isn't in the library, or the emulator was attached to.
                Nothing was stopped.
            EmulatorFault: The emulator was stopped and couldn't be started again.
        """
        if (save := request.save) is not None:
            check_save(request, self._library)
            if not self._control.restartable:
                raise ValueError("a run that starts from a save needs an emulator the harness starts, not --attach")
            self._restart(SAVE, save)
            self._own = False
        elif not self._own:
            self._restart(OWN_STORAGE, None)
            self._own = True
        else:
            self._control.reset()

    def _restart(self, reason: str, save: str | None) -> None:
        self._control.stop()
        try:
            storage = None
            if save is not None and self._library is not None:
                storage = prepare(self._library, save, self._instance, self._control.running())
            config = derived_config(self._config, storage.path) if storage else self._config
            self._control.start(config)
            environment = self._control.describe(config)
        except (OSError, ValueError, RuntimeError) as error:
            raise EmulatorFault(f"restarting the emulator on {reason} failed: {error}") from error
        self.environment = {**environment, **({"save": storage.record()} if storage else {})}
        self._report(reason)
