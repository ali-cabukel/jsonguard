"""Validate parsed JSON against either a JSON-schema subset or a pydantic model.

No dependency on the ``jsonschema`` package: a small, readable subset covers
the vast majority of "does the LLM's output match my expected shape" use
cases (type, required, properties, items, enum, min/max, string length).
Pass a pydantic ``BaseModel`` subclass instead of a dict for full validation
if you already have one.
"""

from __future__ import annotations

from typing import Any, List

_TYPE_MAP = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "object": dict,
    "array": list,
    "null": type(None),
}


def validate(data: Any, schema: Any) -> List[str]:
    """Return a list of human-readable validation errors (empty = valid).

    ``schema`` can be:
    - a dict following a JSON-schema-like subset, or
    - a pydantic ``BaseModel`` subclass, in which case pydantic itself
      performs the validation and its errors are reformatted as strings.
    """
    if _is_pydantic_model(schema):
        return _validate_with_pydantic(data, schema)
    return _validate_jsonschema_subset(data, schema, path="$")


def _is_pydantic_model(schema: Any) -> bool:
    try:
        import pydantic

        return isinstance(schema, type) and issubclass(schema, pydantic.BaseModel)
    except ImportError:
        return False


def _validate_with_pydantic(data: Any, model) -> List[str]:
    import pydantic

    try:
        if isinstance(data, dict):
            model(**data)
        else:
            model.model_validate(data)  # pydantic v2; falls back to exception below on v1
        return []
    except pydantic.ValidationError as exc:
        errors = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", []))
            errors.append(f"{loc or '$'}: {err.get('msg', 'invalid')}")
        return errors
    except TypeError as exc:
        return [f"$: {exc}"]


def _validate_jsonschema_subset(data: Any, schema: dict, path: str) -> List[str]:
    errors: List[str] = []
    if schema is None:
        return errors

    expected_type = schema.get("type")
    if expected_type is not None:
        if expected_type in ("integer", "number") and isinstance(data, bool):
            errors.append(f"{path}: expected {expected_type}, got boolean")
            return errors
        py_type = _TYPE_MAP.get(expected_type)
        if py_type is not None and not isinstance(data, py_type):
            errors.append(f"{path}: expected {expected_type}, got {type(data).__name__}")
            return errors  # further checks would be meaningless on the wrong type

    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: value {data!r} not in allowed enum {schema['enum']}")

    if isinstance(data, str):
        if "minLength" in schema and len(data) < schema["minLength"]:
            errors.append(f"{path}: string shorter than minLength={schema['minLength']}")
        if "maxLength" in schema and len(data) > schema["maxLength"]:
            errors.append(f"{path}: string longer than maxLength={schema['maxLength']}")

    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            errors.append(f"{path}: value {data} below minimum={schema['minimum']}")
        if "maximum" in schema and data > schema["maximum"]:
            errors.append(f"{path}: value {data} above maximum={schema['maximum']}")

    if isinstance(data, dict):
        for key in schema.get("required", []):
            if key not in data:
                errors.append(f"{path}: missing required property '{key}'")
        if "properties" in schema:
            for key, value in data.items():
                prop_schema = schema["properties"].get(key)
                if prop_schema is not None:
                    errors.extend(_validate_jsonschema_subset(value, prop_schema, f"{path}.{key}"))
                elif schema.get("additionalProperties") is False:
                    errors.append(f"{path}: unexpected additional property '{key}'")

    if isinstance(data, list) and "items" in schema:
        for i, item in enumerate(data):
            errors.extend(_validate_jsonschema_subset(item, schema["items"], f"{path}[{i}]"))
        if "minItems" in schema and len(data) < schema["minItems"]:
            errors.append(f"{path}: array shorter than minItems={schema['minItems']}")

    return errors
