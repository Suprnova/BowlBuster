from pathlib import Path

from bowlharness.backends.xemu import launch_command, load_config, parse_banner, preconditions

BOUND = {"input": {"bindings": {"port1": "0300fa67"}}}


def test_a_bound_controller_and_no_running_xemu_pass() -> None:
    assert preconditions(BOUND, []) == []


def test_an_unbound_controller_fails_naming_port_1() -> None:
    assert "port 1" in preconditions({"input": {"bindings": {"port1_driver": "usb-xbox-gamepad"}}}, [])[0]


def test_a_running_xemu_fails_naming_its_process() -> None:
    failures = preconditions(BOUND, ["4242"])

    assert len(failures) == 1 and "4242" in failures[0]


def test_every_failure_is_reported() -> None:
    assert len(preconditions({}, ["1"])) == 2


def test_the_banner_gives_the_version_commit_and_date() -> None:
    banner = "xemu_version: 0.8.139\nxemu_commit: aa54c34\nxemu_date: Wed Oct 21\nnvapi: Saved settings\n"

    assert parse_banner(banner) == {"version": "0.8.139", "commit": "aa54c34", "date": "Wed Oct 21"}


def test_a_configuration_is_read_from_its_file(tmp_path: Path) -> None:
    path = tmp_path / "xemu.toml"
    path.write_text("[input.bindings]\nport1 = 'abc'\n", encoding="utf-8")

    assert load_config(path)["input"]["bindings"]["port1"] == "abc"


def test_xemu_is_started_under_a_cmd_that_keeps_quoted_paths_whole() -> None:
    command = launch_command(Path(r"C:\Program Files\xemu\xemu.exe"), Path(r"D:\my games\xemu.toml"), 2345)

    expected = (
        r'cmd.exe /s /c ""C:\Program Files\xemu\xemu.exe" -config_path "D:\my games\xemu.toml" -gdb tcp::2345 -S"'
    )
    assert command == expected


def test_a_running_xemu_fails_naming_the_storage_image() -> None:
    config = {**BOUND, "sys": {"files": {"hdd_path": "D:/Games/xemu/inst3/xbox_hdd.qcow2"}}}

    assert preconditions(config, ["4242"])[0].endswith("holds the storage image xbox_hdd.qcow2")
