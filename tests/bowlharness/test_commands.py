from pathlib import Path

import pytest

from bowlharness.session.commands import (
    parse_drive_arguments,
    parse_queue_arguments,
    parse_record_arguments,
    scene_selection,
)

OUT = str(Path.cwd() / "recordings-test")


@pytest.fixture(autouse=True)
def no_named_emulator(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tests name their emulator, or set ``BOWL_XEMU`` themselves, whatever the shell running them has."""
    monkeypatch.delenv("BOWL_XEMU", raising=False)


def parse(*arguments: str):
    return parse_record_arguments(list(arguments), "run")


def test_scenes_are_all_none_or_a_list() -> None:
    assert (scene_selection("all"), scene_selection("none"), scene_selection("bb02, b101")) == (
        True,
        False,
        frozenset({"BB02", "B101"}),
    )


def test_a_scene_is_four_characters() -> None:
    with pytest.raises(ValueError, match="four characters"):
        scene_selection("BB02,TOOLONG")


def test_starting_an_emulator_takes_its_executable_and_defaults_the_rest() -> None:
    arguments = parse("--out", OUT, "--xemu", "xemu.exe")

    assert (arguments.attach, arguments.port, arguments.options.heap_events, arguments.options.cutoff_captures) == (
        False,
        1234,
        True,
        False,
    )


def test_attaching_uses_the_given_port() -> None:
    arguments = parse("--out", OUT, "--attach", "2345")

    assert (arguments.attach, arguments.port, arguments.xemu) == (True, 2345, None)


def test_captures_and_budget_become_options() -> None:
    arguments = parse("--out", OUT, "--xemu", "x", "--captures", "cutoff:BB02", "--budget", "3", "--heap", "none")

    options = arguments.options
    assert (options.cutoff_captures, options.capture_budget, options.heap_events) == (frozenset({"BB02"}), 3, False)


@pytest.mark.parametrize(
    "arguments",
    [
        ["--xemu", "x"],
        ["--out", OUT],
        ["--out", OUT, "--xemu", "x", "--attach", "1234"],
        ["--out", "relative", "--xemu", "x"],
        ["--out", OUT, "--xemu", "x", "--bogus"],
    ],
)
def test_bad_arguments_are_refused_with_a_message(arguments: list[str]) -> None:
    with pytest.raises(ValueError):
        parse_record_arguments(arguments, "run")


def test_driving_takes_a_request_and_the_same_launch_arguments_as_recording() -> None:
    arguments = parse_drive_arguments(["--out", OUT, "--xemu", "xemu.exe", "--request", "route.json"], "run")

    assert (arguments.request, arguments.xemu, arguments.port, arguments.attach, arguments.name) == (
        Path("route.json"),
        Path("xemu.exe"),
        1234,
        False,
        "run",
    )


def test_driving_needs_a_request() -> None:
    with pytest.raises(ValueError, match="--request"):
        parse_drive_arguments(["--out", OUT, "--xemu", "xemu.exe"], "run")


def test_driving_needs_an_emulator_or_a_port_to_attach_to() -> None:
    with pytest.raises(ValueError, match="--xemu"):
        parse_drive_arguments(["--out", OUT, "--request", "route.json"], "run")


def test_a_queue_takes_its_store_and_instance_and_the_launch_arguments() -> None:
    arguments = parse_queue_arguments(["--store", OUT, "--instance", "inst3", "--xemu", "xemu.exe", "--place", "b.exe"])

    assert (arguments.store, arguments.instance, arguments.place, arguments.recordings, arguments.stall) == (
        Path(OUT),
        "inst3",
        Path("b.exe"),
        None,
        600.0,
    )


def test_drive_and_queue_take_the_save_library() -> None:
    drive = parse_drive_arguments(["--out", OUT, "--xemu", "x.exe", "--request", "r.json", "--saves", "lib"], "run")
    queue = parse_queue_arguments(["--store", OUT, "--instance", "inst3", "--xemu", "x.exe", "--saves", "lib"])

    assert (drive.saves, queue.saves) == (Path("lib"), Path("lib"))


def test_without_a_save_library_there_is_none() -> None:
    arguments = parse_queue_arguments(["--store", OUT, "--instance", "inst3", "--xemu", "x.exe"])

    assert arguments.saves is None


def test_a_queue_store_is_an_absolute_path() -> None:
    with pytest.raises(ValueError, match="--store must be an absolute path"):
        parse_queue_arguments(["--store", "store", "--instance", "inst3", "--xemu", "xemu.exe"])


def test_the_emulator_named_in_bowl_xemu_is_started_when_none_is_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOWL_XEMU", "D:/xemu/xemu.exe")

    arguments = parse("--out", OUT)

    assert (arguments.xemu, arguments.attach) == (Path("D:/xemu/xemu.exe"), False)


def test_the_emulator_given_wins_over_bowl_xemu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOWL_XEMU", "D:/xemu/xemu.exe")

    assert parse("--out", OUT, "--xemu", "other.exe").xemu == Path("other.exe")


def test_attaching_ignores_bowl_xemu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOWL_XEMU", "D:/xemu/xemu.exe")

    assert (parse("--out", OUT, "--attach", "1234").xemu, parse("--out", OUT, "--attach", "1234").attach) == (
        None,
        True,
    )


def test_no_emulator_and_no_bowl_xemu_says_what_to_do(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOWL_XEMU", raising=False)

    with pytest.raises(ValueError, match="give --xemu, or set BOWL_XEMU"):
        parse("--out", OUT)
