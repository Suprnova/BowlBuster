"""Reads JSON documents into the contract's generated types, and writes them back.

A generated type is a frozen dataclass whose fields carry type hints. Reading follows the hints: an object becomes the
dataclass, refusing a field the dataclass doesn't have and requiring every field without a default; a list, a union,
a literal and the JSON scalars are checked as the hint says. A field whose name is a Python keyword (``from``) is the
generated attribute with a trailing underscore (``from_``). The checks a hint can't state, such as a minimum, are the
reader's caller's.
"""

import dataclasses
import keyword
import types
import typing
from functools import cache
from typing import Any, Literal, TypeAliasType, Union

type Path = tuple[str | int, ...]


def read_document[T](kind: type[T], value: Any, root: str) -> T:
    """Builds ``kind`` from parsed JSON.

    Args:
        kind: The generated type to build.
        value: The parsed document.
        root: What a message calls the document itself, as in ``request has an unknown field 'x'``.

    Raises:
        ValueError: The document doesn't have the type's shape. The message names the path of the field at fault,
            such as ``steps[2].menu.slot``.
    """
    return _read(kind, value, (), root)


def write_document(value: Any) -> Any:
    """The JSON form of a generated type: every field by its JSON name, ``None`` as null, so none is ever absent."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            json_name(field.name): write_document(getattr(value, field.name)) for field in dataclasses.fields(value)
        }
    if isinstance(value, list | tuple):
        return [write_document(item) for item in value]
    if isinstance(value, dict):
        return {key: write_document(item) for key, item in value.items()}
    return value


def json_name(attribute: str) -> str:
    """The JSON name of a generated attribute: ``from_`` is ``from``."""
    return attribute[:-1] if attribute.endswith("_") and keyword.iskeyword(attribute[:-1]) else attribute


def _label(path: Path, root: str) -> str:
    if not path:
        return root
    text = ""
    for part in path:
        text += f"[{part}]" if isinstance(part, int) else f".{part}" if text else part
    return text


@cache
def _hints(kind: type) -> dict[str, Any]:
    return typing.get_type_hints(kind)


def _unalias(hint: Any) -> Any:
    while isinstance(hint, TypeAliasType):
        hint = hint.__value__
    return hint


def _options(hint: Any) -> list[Any]:
    """The alternatives of a union, nested unions and aliases included; a hint that isn't a union is its own."""
    hint = _unalias(hint)
    if typing.get_origin(hint) in (Union, types.UnionType):
        return [option for member in typing.get_args(hint) for option in _options(member)]
    return [hint]


def _describe(options: list[Any]) -> str:
    """What the alternatives accept, for a message: ``"all", "none" or a list of scenes``."""
    words = []
    for option in options:
        if typing.get_origin(option) is Literal:
            words += [f'"{value}"' if isinstance(value, str) else str(value) for value in typing.get_args(option)]
        elif typing.get_origin(option) is list:
            (item,) = typing.get_args(option)
            words.append(f"a list of {item.__name__.lower()}s" if isinstance(item, TypeAliasType) else "a list")
        elif typing.get_origin(option) is dict or dataclasses.is_dataclass(option):
            words.append("an object")
        else:
            names = {str: "a string", int: "a whole number", float: "a number", bool: "true or false"}
            words.append(names.get(option, "null" if option is types.NoneType else str(option)))
    words = list(dict.fromkeys(words))
    return ", ".join(words[:-1]) + f" or {words[-1]}" if len(words) > 1 else words[0]


def _read(hint: Any, value: Any, path: Path, root: str) -> Any:
    hint = _unalias(hint)
    origin = typing.get_origin(hint)
    if hint is Any:
        return value
    if dataclasses.is_dataclass(hint):
        return _read_object(hint, value, path, root)
    if origin is Literal:
        options = typing.get_args(hint)
        if value in options and not isinstance(value, bool):
            return value
        listed = ", ".join(str(option) for option in options)
        raise ValueError(f"{_label(path, root)} must be {listed if len(options) == 1 else f'one of {listed}'}")
    if origin in (Union, types.UnionType):
        return _read_union(_options(hint), value, path, root)
    if origin is list:
        (item,) = typing.get_args(hint)
        if not isinstance(value, list):
            raise ValueError(f"{_label(path, root)} must be {_describe([hint])}")
        return [_read(item, element, (*path, index), root) for index, element in enumerate(value)]
    if origin is dict:
        _, item = typing.get_args(hint)
        if not isinstance(value, dict):
            raise ValueError(f"{_label(path, root)} must be an object")
        return {key: _read(item, element, (*path, key), root) for key, element in value.items()}
    if hint is types.NoneType:
        if value is None:
            return None
    elif hint is float:
        if isinstance(value, int | float) and not isinstance(value, bool):
            return value
    elif hint is int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    elif isinstance(value, hint):
        return value
    raise ValueError(f"{_label(path, root)} must be {_describe([hint])}")


def _read_object(kind: type, value: Any, path: Path, root: str) -> Any:
    if not isinstance(value, dict):
        raise ValueError(f"{_label(path, root)} must be an object")
    fields = {json_name(field.name): field for field in dataclasses.fields(kind)}
    if unknown := sorted(set(value) - set(fields)):
        raise ValueError(f"{_label(path, root)} has an unknown field {unknown[0]!r}")
    hints = _hints(kind)
    built = {}
    for name, field in fields.items():
        if name in value:
            built[field.name] = _read_field(hints[field.name], field, value[name], (*path, name), root)
        elif field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:
            raise ValueError(f"{_label((*path, name), root)} is required")
    return kind(**built)


def _read_field(hint: Any, field: dataclasses.Field[Any], value: Any, path: Path, root: str) -> Any:
    """Reads a field's value. An optional field may be null, and any other value is held to the rest of its hint."""
    if field.default is not None:
        return _read(hint, value, path, root)
    if value is None:
        return None
    options = [option for option in _options(hint) if option is not types.NoneType]
    return _read(options[0], value, path, root) if len(options) == 1 else _read_union(options, value, path, root)


def _read_union(options: list[Any], value: Any, path: Path, root: str) -> Any:
    if value is None and types.NoneType in options:
        return None
    if isinstance(value, dict) and (kinds := [option for option in options if dataclasses.is_dataclass(option)]):
        matching = [kind for kind in kinds if _discriminated(kind, value)]
        if len(matching) == 1:
            return _read_object(matching[0], value, path, root)
        if not matching and (found := _discriminator(kinds)):
            name, values = found
            for kind, allowed in zip(kinds, values, strict=True):
                if value.get(name) in allowed:
                    return _read_object(kind, value, path, root)
            listed = ", ".join(str(item) for allowed in values for item in allowed)
            raise ValueError(f"{_label((*path, name), root)} must be one of {listed}")
    for option in options:
        try:
            return _read(option, value, path, root)
        except ValueError:
            continue
    raise ValueError(f"{_label(path, root)} must be {_describe(options)}")


@cache
def _literals(kind: type) -> dict[str, tuple[Any, ...]]:
    """The literal fields of ``kind``, by JSON name, with the values each allows."""
    return {
        json_name(name): typing.get_args(_unalias(hint))
        for name, hint in _hints(kind).items()
        if typing.get_origin(_unalias(hint)) is Literal
    }


def _discriminated(kind: type, value: dict[str, Any]) -> bool:
    """Whether every literal field of ``kind`` that ``value`` has holds one of the values it allows."""
    return all(value[name] in allowed for name, allowed in _literals(kind).items() if name in value)


def _discriminator(kinds: list[type]) -> tuple[str, list[tuple[Any, ...]]] | None:
    """The literal field that tells ``kinds`` apart, every kind allowing values no other does, and those values."""
    for name in _literals(kinds[0]):
        values = [_literals(kind).get(name, ()) for kind in kinds]
        flat = [item for allowed in values for item in allowed]
        if all(values) and len(set(flat)) == len(flat):
            return name, values
    return None
