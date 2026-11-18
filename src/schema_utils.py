"""Turn a Pydantic model into a tool `input_schema` (blueprint Day 6, step 3).

`model_json_schema()` produces references (`{"$ref": "#/$defs/Category"}`) and `title` fields.
Tool schemas are simpler and safer for the model without them, so `tool_schema` inlines every
reference and drops the titles. Constraints such as `minimum`, `maximum` and `maxLength` stay.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

_REF_PREFIX = "#/$defs/"


def tool_schema(model_cls: type[BaseModel]) -> dict[str, Any]:
    """Return a self-contained JSON schema for `model_cls` (no `$ref`, `$defs` or `title`)."""
    schema = model_cls.model_json_schema()
    defs: dict[str, Any] = schema.get("$defs", {})
    result = _walk(schema, defs, ())
    result.pop("$defs", None)
    return result


def _walk(node: Any, defs: dict[str, Any], stack: tuple[str, ...]) -> Any:
    if isinstance(node, list):
        return [_walk(item, defs, stack) for item in node]
    if not isinstance(node, dict):
        return node

    node = dict(node)
    ref = node.pop("$ref", None)
    resolved: dict[str, Any] = {}
    if ref is not None:
        if not ref.startswith(_REF_PREFIX):
            raise ValueError(f"unsupported $ref {ref!r}")
        name = ref[len(_REF_PREFIX) :]
        if name in stack:
            raise ValueError(f"recursive schema is not supported: {name}")
        resolved = _walk(defs[name], defs, (*stack, name))

    out: dict[str, Any] = dict(resolved)
    for key, value in node.items():
        if key == "$defs":
            continue
        if key == "title" and isinstance(value, str):
            continue  # a schema keyword; a FIELD called "title" lives under "properties" below
        if key == "properties":
            # Keys of "properties" are field names: keep every one, even a field called "title".
            out[key] = {name: _walk(sub, defs, stack) for name, sub in value.items()}
        elif key in {"default", "enum", "const", "examples"}:
            out[key] = value  # literal data, not schema
        else:
            out[key] = _walk(value, defs, stack)
    return out
