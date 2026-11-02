from pathlib import Path

import pytest

from bowlharness.session.commands import parse_record_arguments, scene_selection

OUT = str(Path.cwd() / "recordings-test")


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
