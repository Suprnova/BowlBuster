import pytest

from bowlharness.__main__ import SOURCE_ROOT, find_gdb, gdb_command


def test_gdb_command_imports_the_harness_and_runs_the_bowl_command() -> None:
    command = gdb_command("gdb", ["record", "--out", "a b"])

    assert "python import bowlharness.gdbhost" in command
    assert command[-1] == 'bowl "record" "--out" "a b"'
    assert SOURCE_ROOT.as_posix() in command[command.index("-iex") + 1]


def test_smoke_runs_in_batch_mode() -> None:
    command = gdb_command("gdb", ["smoke"])

    assert "-batch" in command


def test_windows_paths_reach_gdb_with_forward_slashes() -> None:
    command = gdb_command("gdb", ["record", "--out", r"C:\Users\me\out"])

    assert command[-1] == 'bowl "record" "--out" "C:/Users/me/out"'


def test_the_named_gdb_wins_over_the_one_on_the_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOWL_GDB", "named-gdb")
    monkeypatch.setattr("shutil.which", lambda _: "path-gdb")

    assert find_gdb() == "named-gdb"


def test_gdb_on_the_path_is_the_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOWL_GDB", raising=False)
    monkeypatch.setattr("shutil.which", lambda _: "path-gdb")

    assert find_gdb() == "path-gdb"


def test_no_gdb_is_an_error_that_says_what_to_do(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOWL_GDB", raising=False)
    monkeypatch.setattr("shutil.which", lambda _: None)

    with pytest.raises(SystemExit, match="BOWL_GDB"):
        find_gdb()
