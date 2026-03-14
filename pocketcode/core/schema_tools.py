from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


def validate_schema_value(value: Any, schema: Mapping[str, Any] | None, *, path: str = "value") -> list[str]:
    normalized_schema = dict(schema or {})
    if not normalized_schema:
        return []
    _, errors = _apply_schema(value, normalized_schema, path=path, coerce=False)
    return errors


def apply_schema_value(value: Any, schema: Mapping[str, Any] | None, *, path: str = "value") -> tuple[Any, list[str]]:
    normalized_schema = dict(schema or {})
    if not normalized_schema:
        return value, []
    return _apply_schema(value, normalized_schema, path=path, coerce=True)


def _apply_schema(
    value: Any,
    schema: Mapping[str, Any],
    *,
    path: str,
    coerce: bool,
) -> tuple[Any, list[str]]:
    working_value = deepcopy(schema["default"]) if coerce and value is None and "default" in schema else value
    expected_type = str(schema.get("type") or "").strip().lower()
    errors: list[str] = []

    if expected_type:
        if coerce:
            working_value, type_errors = _coerce_type(working_value, expected_type, path=path)
        else:
            type_errors = _require_type(working_value, expected_type, path=path)
        errors.extend(type_errors)
        if type_errors:
            return working_value, errors

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values and working_value not in enum_values:
        errors.append(f"{path} must be one of {enum_values!r}.")
        return working_value, errors

    if expected_type == "object":
        if not isinstance(working_value, dict):
            return working_value, errors
        result = dict(working_value)
        required = {str(field).strip() for field in (schema.get("required") or []) if str(field).strip()}
        properties = schema.get("properties") or {}
        if isinstance(properties, dict):
            for name, subschema in properties.items():
                clean_name = str(name or "").strip()
                if not clean_name or not isinstance(subschema, dict):
                    continue
                if clean_name in result:
                    coerced_value, property_errors = _apply_schema(
                        result[clean_name],
                        subschema,
                        path=f"{path}.{clean_name}",
                        coerce=coerce,
                    )
                    result[clean_name] = coerced_value
                    errors.extend(property_errors)
                    continue
                if coerce and "default" in subschema:
                    result[clean_name] = deepcopy(subschema["default"])
                    continue
                if clean_name in required:
                    errors.append(f"{path}.{clean_name} is required.")
        else:
            for clean_name in required:
                if clean_name not in result:
                    errors.append(f"{path}.{clean_name} is required.")
        return result, errors

    if expected_type == "array":
        if not isinstance(working_value, list):
            return working_value, errors
        result_items: list[Any] = []
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(working_value):
                coerced_item, item_errors = _apply_schema(
                    item,
                    item_schema,
                    path=f"{path}[{index}]",
                    coerce=coerce,
                )
                result_items.append(coerced_item)
                errors.extend(item_errors)
            return result_items, errors
        return list(working_value), errors

    return working_value, errors


def _require_type(value: Any, expected_type: str, *, path: str) -> list[str]:
    if expected_type == "object":
        return [] if isinstance(value, dict) else [f"{path} must be an object."]
    if expected_type == "array":
        return [] if isinstance(value, list) else [f"{path} must be an array."]
    if expected_type == "string":
        return [] if isinstance(value, str) else [f"{path} must be a string."]
    if expected_type == "boolean":
        return [] if isinstance(value, bool) else [f"{path} must be a boolean."]
    if expected_type == "integer":
        return [] if isinstance(value, int) and not isinstance(value, bool) else [f"{path} must be an integer."]
    if expected_type == "number":
        return [] if isinstance(value, (int, float)) and not isinstance(value, bool) else [f"{path} must be a number."]
    return []


def _coerce_type(value: Any, expected_type: str, *, path: str) -> tuple[Any, list[str]]:
    if expected_type in {"object", "array"}:
        return value, _require_type(value, expected_type, path=path)
    if expected_type == "string":
        if isinstance(value, (dict, list)):
            return value, [f"{path} must be a string."]
        return str(value), []
    if expected_type == "boolean":
        if isinstance(value, bool):
            return value, []
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True, []
            if normalized in {"false", "0", "no", "off"}:
                return False, []
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return bool(value), []
        return value, [f"{path} must be a boolean."]
    if expected_type == "integer":
        if isinstance(value, int) and not isinstance(value, bool):
            return value, []
        if isinstance(value, float) and value.is_integer():
            return int(value), []
        if isinstance(value, str):
            try:
                return int(value.strip()), []
            except ValueError:
                return value, [f"{path} must be an integer."]
        return value, [f"{path} must be an integer."]
    if expected_type == "number":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value, []
        if isinstance(value, str):
            text = value.strip()
            try:
                return int(text), []
            except ValueError:
                try:
                    return float(text), []
                except ValueError:
                    return value, [f"{path} must be a number."]
        return value, [f"{path} must be a number."]
    return value, []
