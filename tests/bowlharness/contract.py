"""Validates documents against the JSON schemas, as a client of the contract would."""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schema"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _registry() -> Registry:
    resources = []
    for path in SCHEMAS.glob("*.schema.json"):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resources.append((contents["$id"], Resource.from_contents(contents)))
    return Registry().with_resources(resources)


def schema_errors(document: Any, schema: str) -> list[str]:
    """Every way ``document`` breaks the schema named ``schema`` (``request`` or ``result``)."""
    contents = json.loads((SCHEMAS / f"{schema}.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(contents, registry=_registry(), format_checker=Draft202012Validator.FORMAT_CHECKER)
    return [f"{'/'.join(map(str, error.absolute_path))}: {error.message}" for error in validator.iter_errors(document)]
