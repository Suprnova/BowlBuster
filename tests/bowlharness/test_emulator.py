from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from support import route

from bowlharness.backends.emulator import Emulator, EmulatorFault
from bowlharness.backends.xemu import derived_config, load_config
from bowlharness.driving.request import Request
from bowlharness.saves.commands import add_image
from bowlharness.saves.library import STORAGE, Library, Save

BYTES = b"bytes standing in for a storage image"
CONFIG = r"""[general]
show_welcome = false

[sys.files]
bootrom_path = 'D:\Games\xemu\mcpx-1.0.bin'
eeprom_path = 'D:\Games\xemu\inst3\eeprom.bin'
hdd_path = 'D:\Games\xemu\inst3\xbox_hdd.qcow2'
"""


class Control:
    """An emulator that logs what it is told to do."""

    def __init__(self, restartable: bool = True, fail_start: bool = False) -> None:
        self.restartable = restartable
        self.fail_start = fail_start
        self.calls: list[str] = []
        self.configs: list[Path] = []

    def start(self, config: Path) -> None:
        if self.fail_start:
            raise RuntimeError("xemu exited with code 1")
        self.calls.append("start")
        self.configs.append(config)

    def stop(self) -> None:
        self.calls.append("stop")

    def reset(self) -> None:
        self.calls.append("reset")

    def describe(self, config: Path) -> dict[str, Any]:
        hdd = Path(load_config(config)["sys"]["files"]["hdd_path"])
        return {"storage": {"image": hdd.name, "bytes": hdd.stat().st_size if hdd.is_file() else None}}

    def running(self) -> list[str]:
        return []


def setup(tmp_path: Path, control: Control) -> tuple[Emulator, list[str], Path]:
    config = tmp_path / "inst3" / "xemu.toml"
    config.parent.mkdir()
    config.write_text(CONFIG, encoding="utf-8")
    source = tmp_path / "source.qcow2"
    source.write_bytes(BYTES)
    root = tmp_path / "library"
    add_image(root, source, "played-1", (Save("base", "", 1, "ORIG"),), [], datetime(2026, 11, 9, tzinfo=UTC))
    reasons: list[str] = []
    emulator = Emulator(control, config, "inst3", Library(root), {"storage": {"image": "own"}}, reasons.append)
    return emulator, reasons, root


def from_save(request_id: str) -> Request:
    return replace(route("ORIG"), request_id=request_id, start="save", save="base")


def test_a_queue_of_new_game_save_save_new_game_restarts_three_times_and_resets_once(tmp_path: Path) -> None:
    control = Control()
    emulator, reasons, _ = setup(tmp_path, control)

    for request in (route("ORIG"), from_save("s1"), from_save("s2"), route("ORIG")):
        emulator.boot(request)

    assert control.calls == ["reset", "stop", "start", "stop", "start", "stop", "start"]
    assert reasons == ["save", "save", "own storage"]


def test_a_save_run_starts_on_a_derived_config_whose_storage_is_the_working_copy(tmp_path: Path) -> None:
    control = Control()
    emulator, _, root = setup(tmp_path, control)

    emulator.boot(from_save("s1"))

    working = (root / "work" / "inst3" / STORAGE).resolve()
    assert load_config(control.configs[0])["sys"]["files"]["hdd_path"] == str(working)
    assert emulator.environment["storage"] == {"image": STORAGE, "bytes": len(BYTES)}
    image = Library(root).images["played-1"]
    assert emulator.environment["save"] == {
        "name": "base",
        "slot": 1,
        "image": "played-1",
        "storage_sha256": image.sha256,
    }


def test_each_save_run_starts_from_an_untouched_copy(tmp_path: Path) -> None:
    control = Control()
    emulator, _, root = setup(tmp_path, control)
    emulator.boot(from_save("s1"))
    (root / "work" / "inst3" / STORAGE).write_bytes(b"autosaved")

    emulator.boot(from_save("s2"))

    assert (root / "work" / "inst3" / STORAGE).read_bytes() == BYTES


def test_the_run_after_a_save_run_goes_back_to_the_instances_own_configuration(tmp_path: Path) -> None:
    control = Control()
    emulator, _, _ = setup(tmp_path, control)
    emulator.boot(from_save("s1"))

    emulator.boot(route("ORIG"))

    assert control.configs[-1] == tmp_path / "inst3" / "xemu.toml" and "save" not in emulator.environment


def test_a_save_the_library_does_not_hold_is_refused_with_nothing_stopped(tmp_path: Path) -> None:
    control = Control()
    emulator, _, _ = setup(tmp_path, control)

    with pytest.raises(ValueError, match="start.save names missing"):
        emulator.boot(replace(from_save("s1"), save="missing"))

    assert control.calls == []


def test_a_save_run_on_an_attached_emulator_is_refused(tmp_path: Path) -> None:
    control = Control(restartable=False)
    emulator, _, _ = setup(tmp_path, control)

    with pytest.raises(ValueError, match="not --attach"):
        emulator.boot(from_save("s1"))

    assert control.calls == []


def test_a_restart_that_fails_is_an_emulator_fault_naming_the_cause(tmp_path: Path) -> None:
    control = Control(fail_start=True)
    emulator, _, _ = setup(tmp_path, control)

    with pytest.raises(EmulatorFault, match="restarting the emulator on save failed: xemu exited with code 1"):
        emulator.boot(from_save("s1"))


def test_a_derived_config_changes_only_the_storage_line(tmp_path: Path) -> None:
    config = tmp_path / "xemu.toml"
    config.write_text(CONFIG, encoding="utf-8")
    storage = tmp_path / "work dir" / "inst3" / STORAGE
    storage.parent.mkdir(parents=True)

    derived = derived_config(config, storage)

    lines = zip(CONFIG.splitlines(), derived.read_text(encoding="utf-8").splitlines(), strict=True)
    assert [index for index, (old, new) in enumerate(lines) if old != new] == [6]
    assert load_config(derived)["sys"]["files"]["hdd_path"] == str(storage) and derived.parent == storage.parent


def test_a_config_without_one_storage_line_is_refused(tmp_path: Path) -> None:
    config = tmp_path / "xemu.toml"
    config.write_text("[general]\nshow_welcome = false\n", encoding="utf-8")

    with pytest.raises(ValueError, match="no single hdd_path"):
        derived_config(config, tmp_path / STORAGE)
