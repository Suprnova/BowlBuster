from pathlib import Path

import pytest

from bowlharness.mock import MockTarget, Step
from bowlharness.target import Stop, TargetError


def test_run_stops_only_at_armed_addresses() -> None:
    target = MockTarget([Step(0x10), Step(0x20), Step(0x30)])
    stops: list[Stop] = []
    target.set_breakpoint(0x20, stops.append)

    target.run()

    assert stops == [Stop(0x20)]


def test_run_calls_watchpoint_handlers_with_the_written_address() -> None:
    target = MockTarget([Step(0x10, written=0x1002), Step(0x20, written=0x2000)])
    stops: list[Stop] = []
    target.set_watchpoint(0x1000, 4, stops.append)

    target.run()

    assert stops == [Stop(0x10, 0x1002)]


def test_cleared_point_no_longer_stops() -> None:
    target = MockTarget([Step(0x10)])
    stops: list[Stop] = []
    handle = target.set_breakpoint(0x10, stops.append)
    target.clear(handle)

    target.run()

    assert stops == []


def test_handler_sees_the_registers_and_memory_of_its_step() -> None:
    target = MockTarget([Step(0x10, {"eax": 7}, {0x500: b"\x01\x02"})])
    seen: list[tuple[int, bytes]] = []
    target.set_breakpoint(0x10, lambda _: seen.append((target.registers()["eax"], target.read(0x500, 2))))

    target.run()

    assert seen == [(7, b"\x01\x02")]


def test_read_of_unmapped_memory_raises() -> None:
    target = MockTarget([])

    with pytest.raises(TargetError):
        target.read(0x500, 1)


def test_interrupt_ends_run_and_run_resumes_after_it() -> None:
    target = MockTarget([Step(0x10), Step(0x20)])
    stops: list[Stop] = []
    target.set_breakpoint(0x10, lambda _: target.interrupt())
    target.set_breakpoint(0x20, stops.append)

    target.run()
    assert stops == []
    target.run()

    assert stops == [Stop(0x20)]


def test_write_is_recorded_and_visible_to_reads() -> None:
    target = MockTarget([])

    target.write(0x500, b"\xaa\xbb")

    assert target.writes == [(0x500, b"\xaa\xbb")]
    assert target.read(0x500, 2) == b"\xaa\xbb"


def test_dump_saves_the_range(tmp_path: Path) -> None:
    target = MockTarget([Step(0x10, memory={0x500: b"\x01\x02\x03"})])
    target.run()

    target.dump(0x500, 3, tmp_path / "range.bin")

    assert (tmp_path / "range.bin").read_bytes() == b"\x01\x02\x03"


def test_reset_restarts_the_script() -> None:
    target = MockTarget([Step(0x10)])
    stops: list[Stop] = []
    target.set_breakpoint(0x10, stops.append)
    target.run()

    target.reset()
    target.run()

    assert stops == [Stop(0x10), Stop(0x10)]


def test_run_with_a_timeout_stops_the_guest_after_a_silent_stretch() -> None:
    target = MockTarget([Step(0x10, seconds=3), Step(0x20, seconds=3), Step(0x30, seconds=3)])

    expired = target.run(timeout=5)

    assert expired is True


def test_run_with_a_timeout_is_not_stopped_while_stops_keep_coming() -> None:
    target = MockTarget([Step(0x10, seconds=3), Step(0x10, seconds=3), Step(0x10, seconds=3)])
    target.set_breakpoint(0x10, lambda _: None)

    expired = target.run(timeout=5)

    assert expired is False
