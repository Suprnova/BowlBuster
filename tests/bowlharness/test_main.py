from bowlharness.__main__ import SOURCE_ROOT, gdb_command


def test_gdb_command_imports_the_harness_and_runs_the_bowl_command() -> None:
    command = gdb_command("gdb", ["record", "--out", "a b"])

    assert "python import bowlharness.gdbhost" in command
    assert command[-1] == 'bowl "record" "--out" "a b"'
    assert SOURCE_ROOT.as_posix() in command[command.index("-iex") + 1]


def test_smoke_runs_in_batch_mode() -> None:
    command = gdb_command("gdb", ["smoke"])

    assert "-batch" in command
