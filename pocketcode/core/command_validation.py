from __future__ import annotations

from typing import Any, Mapping


def validate_command_payload(payload: Mapping[str, Any] | None, schema: Mapping[str, Any] | None) -> None:
    normalized_payload = dict(payload or {})
    normalized_schema = dict(schema or {})
    if not normalized_schema:
        return
    _validate_value(normalized_payload, normalized_schema, path="payload")


def validate_command_result_data(data: Mapping[str, Any] | None, schema: Mapping[str, Any] | None) -> None:
    normalized_data = dict(data or {})
    normalized_schema = dict(schema or {})
    if not normalized_schema:
        return
    _validate_value(normalized_data, normalized_schema, path="result.data")


def _validate_value(value: Any, schema: Mapping[str, Any], *, path: str) -> None:
    expected_type = str(schema.get("type") or "").strip().lower()
    if expected_type:
        _require_type(value, expected_type, path=path)

    if expected_type == "object":
        if not isinstance(value, dict):
            return
        required = schema.get("required") or []
        if isinstance(required, list):
            for field in required:
                name = str(field or "").strip()
                if name and name not in value:
                    raise ValueError(f"{path}.{name} is required.")
        properties = schema.get("properties") or {}
        if isinstance(properties, dict):
            for name, subschema in properties.items():
                clean_name = str(name or "").strip()
                if not clean_name or clean_name not in value or not isinstance(subschema, dict):
                    continue
                _validate_value(value[clean_name], subschema, path=f"{path}.{clean_name}")
        return

    if expected_type == "array":
        if not isinstance(value, list):
            return
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_value(item, item_schema, path=f"{path}[{index}]")


def _require_type(value: Any, expected_type: str, *, path: str) -> None:
    type_map = {
        "object": dict,
        "array": list,
        "string": str,
        "boolean": bool,
        "integer": int,
        "number": (int, float),
    }
    expected = type_map.get(expected_type)
    if expected is None:
        return
    if expected_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{path} must be an integer.")
        return
    if expected_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{path} must be a number.")
        return
    if not isinstance(value, expected):
        article = "an" if expected_type[:1] in {"a", "e", "i", "o", "u"} else "a"
        raise ValueError(f"{path} must be {article} {expected_type}.")
