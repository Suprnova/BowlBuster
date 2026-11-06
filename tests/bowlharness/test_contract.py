import json
import subprocess
import sys
import typing
from pathlib import Path

import pytest
from contract import FIXTURES, ROOT, schema_errors

from bowlharness.contract.documents import read_document, write_document
from bowlharness.contract.generated import request_schema
from bowlharness.profiles import XBOX_NTSC_U

GENERATED = ROOT / "src" / "bowlharness" / "contract" / "generated"
REQUESTS = sorted((FIXTURES / "requests").glob("*.json"))


def fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_generated_types_are_what_the_schemas_generate(tmp_path: Path) -> None:
    out = tmp_path / "generated"

    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_contract.py"), str(out)], check=True)

    assert {path.name: path.read_bytes() for path in out.glob("*.py")} == {
        path.name: path.read_bytes() for path in GENERATED.glob("*.py")
    }


@pytest.mark.parametrize("path", REQUESTS, ids=lambda path: path.stem)
def test_every_request_fixture_follows_the_schema(path: Path) -> None:
    assert schema_errors(fixture(path), "request") == []


@pytest.mark.parametrize("path", REQUESTS, ids=lambda path: path.stem)
def test_every_request_fixture_written_back_reads_the_same(path: Path) -> None:
    request = read_document(request_schema.Request, fixture(path), "request")

    assert read_document(request_schema.Request, write_document(request), "request") == request


def test_a_request_reads_as_the_type_its_kind_names() -> None:
    request = read_document(request_schema.Request, fixture(FIXTURES / "requests" / "landing.json"), "request")

    assert isinstance(request, request_schema.LandingRequest) and request.tests[0].recipe.load == 3


def test_an_unknown_field_is_named_by_its_path() -> None:
    document = fixture(FIXTURES / "requests" / "landing.json")
    document["tests"][0]["recipe"]["extra"] = 1

    with pytest.raises(ValueError, match=r"^tests\[0\]\.recipe has an unknown field 'extra'$"):
        read_document(request_schema.Request, document, "request")


def test_a_missing_field_is_named_by_its_path() -> None:
    document = fixture(FIXTURES / "requests" / "landing.json")
    del document["tests"][0]["expected"]["offset"]

    with pytest.raises(ValueError, match=r"^tests\[0\]\.expected\.offset is required$"):
        read_document(request_schema.Request, document, "request")


def test_a_wrong_type_is_named_by_its_path() -> None:
    document = fixture(FIXTURES / "requests" / "record.json")
    document["steps"][1]["menu"]["slot"] = "1"

    with pytest.raises(ValueError, match=r"^steps\[1\]\.menu\.slot must be a whole number$"):
        read_document(request_schema.Request, document, "request")


def test_an_unknown_kind_lists_the_kinds() -> None:
    document = fixture(FIXTURES / "requests" / "record.json") | {"kind": "chain"}

    with pytest.raises(ValueError, match=r"^kind must be one of record, landing, control, inject$"):
        read_document(request_schema.Request, document, "request")


def test_a_document_that_is_not_an_object_is_refused_by_its_root_name() -> None:
    with pytest.raises(ValueError, match=r"^request must be an object$"):
        read_document(request_schema.Request, [], "request")


def test_every_profile_maps_exactly_the_cheats_the_schema_names() -> None:
    names = set(typing.get_args(request_schema.CheatName.__value__))

    assert {name for name, _ in XBOX_NTSC_U.navigation.cheats.names} == names
