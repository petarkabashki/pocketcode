from __future__ import annotations

from pathlib import Path
from typing import Any


def namespace_name_from_metadata(
    metadata: dict[str, Any] | None,
    *,
    fallback_qualified_name: str | None = None,
) -> str | None:
    raw_metadata = metadata or {}
    for key in ("namespace",):
        value = raw_metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    if isinstance(fallback_qualified_name, str) and fallback_qualified_name.strip():
        candidate = fallback_qualified_name.strip()
        if "." in candidate:
            return candidate.split(".", 1)[0].strip() or None
    return None


def namespace_root_from_metadata(metadata: dict[str, Any] | None) -> Path | None:
    raw_metadata = metadata or {}
    for key in ("namespace_root",):
        value = raw_metadata.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value).resolve()
    return None
