"""Generates the harness's contract types from the JSON schemas in ``schema/``.

Usage: ``uv run python scripts/generate_contract.py [<output folder>]``. With no argument it rewrites
``src/bowlharness/contract/generated/``; with one, it writes there instead, which must not exist yet.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schema"
GENERATED = ROOT / "src" / "bowlharness" / "contract" / "generated"
HEADER = "# Generated from schema/ by scripts/generate_contract.py. Do not edit; change the schema and run it again."


def generate(output: Path) -> None:
    """Writes the generated package to ``output``, replacing the files it already holds."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "datamodel_code_generator",
            "--input",
            str(SCHEMAS),
            "--input-file-type",
            "jsonschema",
            "--output",
            str(output),
            "--output-model-type",
            "dataclasses.dataclass",
            "--frozen-dataclasses",
            "--keyword-only",
            "--target-python-version",
            "3.14",
            "--use-standard-collections",
            "--use-union-operator",
            "--use-double-quotes",
            "--use-schema-description",
            "--use-field-description",
            "--use-exact-imports",
            "--enum-field-as-literal",
            "all",
            "--disable-timestamp",
            "--custom-file-header",
            HEADER,
            "--formatters",
            "ruff-check",
            "ruff-format",
        ],
        check=True,
        cwd=ROOT,
    )
    for module in output.glob("*.py"):
        module.write_text(module.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    config = str(ROOT / "pyproject.toml")
    for command in (["check", "--fix", "--quiet", "--ignore", "E501"], ["format", "--quiet"]):
        subprocess.run([sys.executable, "-m", "ruff", *command, "--config", config, str(output)], check=True)


def main() -> None:
    if len(sys.argv) > 2:
        raise SystemExit("usage: generate_contract.py [<output folder>]")
    if len(sys.argv) == 2:
        output = Path(sys.argv[1]).resolve()
        if output.exists():
            raise SystemExit(f"{output} already exists")
        generate(output)
        return
    with tempfile.TemporaryDirectory() as scratch:
        fresh = Path(scratch) / "generated"
        generate(fresh)
        GENERATED.mkdir(parents=True, exist_ok=True)
        for stale in GENERATED.glob("*.py"):
            if not (fresh / stale.name).exists():
                stale.unlink()
        for module in fresh.glob("*.py"):
            (GENERATED / module.name).write_bytes(module.read_bytes())


if __name__ == "__main__":
    main()
