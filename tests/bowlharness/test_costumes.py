import struct

import pytest
from scripted import CHEATS, COMPACT, ScriptedGame

from bowlharness.driving.cheats import read_codes
from bowlharness.driving.costumes import CostumePlan, plan_costumes

PLSA_BIT, PLSC_BIT = CHEATS[1][1], CHEATS[2][1]
MERMAID_MAN, PLAIN_SPONGE, DISCO_PATRICK, PLAIN_PATRICK = 1, 2, 3, 4


def reader(memory: dict[int, bytes]):
    def read(address: int, length: int) -> bytes:
        for start, data in memory.items():
            if start <= address and address + length <= start + len(data):
                return data[address - start : address - start + length]
        return bytes(length)

    return read


def plan(
    wanted: tuple[str, ...], on: tuple[int, ...] = (), cheats: int = 0, chests: int = 42, unlock: int = 1
) -> CostumePlan:
    """Plans ``wanted`` from a game whose Extra rows 0-3 give the four Extras costumes, ``on`` of them worn."""
    game = ScriptedGame()
    game.chests = chests
    memory = game._costumes({}, cheats)
    costumes = COMPACT.costumes
    rows = b"".join(bytes([costumes.extra_kind, extra, unlock, int(extra in on)]) for extra in range(1, 5))
    memory |= {costumes.extras_count: struct.pack("<I", 4), costumes.extras: rows}
    read = reader(memory)
    return plan_costumes(read, COMPACT, read_codes(read, COMPACT), cheats, wanted)


def test_an_extras_costume_is_chosen_on_its_row() -> None:
    assert plan(("PLSB",)) == CostumePlan((), (MERMAID_MAN - 1,))


def test_a_worn_extras_costume_not_wanted_is_chosen_again_to_take_it_off() -> None:
    assert plan((), on=(MERMAID_MAN,)) == CostumePlan((), (MERMAID_MAN - 1,))


def test_nothing_is_chosen_when_the_costumes_are_already_worn() -> None:
    assert plan(("PLSB", "PLPB"), on=(MERMAID_MAN, DISCO_PATRICK)) == CostumePlan()


def test_mermaid_man_is_taken_off_by_hand_before_plain_sponge_goes_on() -> None:
    assert plan(("PLSD",), on=(MERMAID_MAN,)).extras == (MERMAID_MAN - 1, PLAIN_SPONGE - 1)


def test_plain_sponge_goes_on_before_disco_patrick_since_it_takes_off_patricks_costumes() -> None:
    assert plan(("PLSD", "PLPB")).extras == (PLAIN_SPONGE - 1, DISCO_PATRICK - 1)


def test_a_cheat_costume_takes_off_its_characters_extras_costume_itself() -> None:
    planned = plan(("PLSA",), on=(MERMAID_MAN,))

    assert ([code.bit for code in planned.codes], planned.extras) == ([PLSA_BIT], ())


def test_an_extras_costume_takes_off_its_characters_cheat_costume_after_the_cheat_is_toggled_off() -> None:
    planned = plan(("PLSB",), cheats=PLSA_BIT)

    assert ([code.bit for code in planned.codes], planned.extras) == ([PLSA_BIT], (MERMAID_MAN - 1,))


def test_a_locked_extras_costume_is_refused_naming_the_chests_it_needs() -> None:
    with pytest.raises(ValueError, match="PLSB is locked: it needs 2 chests, the save has 1"):
        plan(("PLSB",), chests=1, unlock=2)


def test_a_costume_the_table_does_not_give_is_refused() -> None:
    with pytest.raises(ValueError, match="PLX9 is not a costume the costume table gives"):
        plan(("PLX9",))


def test_costumes_no_order_reaches_are_refused() -> None:
    with pytest.raises(ValueError, match="no order of Extras choices leaves PLSC, PLP1 worn"):
        plan(("PLSC", "PLP1"))
