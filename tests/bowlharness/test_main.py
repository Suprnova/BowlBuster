import pytest

from bowlharness.__main__ import SOURCE_ROOT, find_gdb, gdb_command, run_gdb, split_gdb


class InterruptedGdb:
    """A gdb whose first wait a person's Ctrl-C interrupts, and which then exits with code 3."""

    def __init__(self, command: list[str]) -> None:
        self.waits = 0

    def wait(self) -> int:
        self.waits += 1
        if self.waits == 1:
            raise KeyboardInterrupt
        return 3


def test_gdb_command_imports_the_harness_and_runs_the_bowl_command() -> None:
    command = gdb_command("gdb", ["record", "--out", "a b"])

    assert "python import bowlharness.backends.gdbhost" in command
    assert command[-1] == 'bowl "record" "--out" "a b"'
    assert SOURCE_ROOT.as_posix() in next(arg for arg in command if "sys.path.insert" in arg)


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


def test_gdb_is_told_not_to_page_or_ask() -> None:
    command = gdb_command("gdb", ["record"])

    assert [arg for arg in command if arg.startswith("set ")] == ["set pagination off", "set confirm off"]


def test_the_gdb_given_on_the_command_line_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOWL_GDB", "named-gdb")

    assert find_gdb("given-gdb") == "given-gdb"


def test_the_gdb_argument_is_taken_out_wherever_it_is() -> None:
    assert split_gdb(["drive", "--gdb", "C:/gdb.exe", "--out", "x"]) == ("C:/gdb.exe", ["drive", "--out", "x"])


def test_without_a_gdb_argument_the_arguments_are_the_bowl_commands() -> None:
    assert split_gdb(["drive", "--out", "x"]) == (None, ["drive", "--out", "x"])


def test_a_gdb_argument_needs_a_path() -> None:
    with pytest.raises(SystemExit, match="--gdb needs the path"):
        split_gdb(["drive", "--gdb"])


def test_a_ctrl_c_is_left_to_gdb_and_its_exit_code_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("subprocess.Popen", InterruptedGdb)

    assert run_gdb(["gdb"]) == 3
