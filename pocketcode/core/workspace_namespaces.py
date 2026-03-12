from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkspaceNamespace:
    name: str
    path: Path
    filename_prefix: str | None = None


def discover_workspace_namespaces(
    config: dict[str, Any] | None,
    workspace_root: str | Path,
) -> list[WorkspaceNamespace]:
    root = Path(workspace_root).resolve()
    runtime = config.get("runtime", {}) if isinstance(config, dict) else {}
    raw_paths = runtime.get("workspace_paths")

    if not isinstance(raw_paths, list):
        return []

    namespaces: list[WorkspaceNamespace] = []
    seen_names: set[str] = set()
    seen_paths: set[Path] = set()

    for raw_path in raw_paths:
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        else:
            candidate = candidate.resolve()

        if candidate in seen_paths:
            continue
        if not candidate.is_dir():
            logger.warning("Skipping workspace namespace path '%s': directory not found.", candidate)
            continue

        namespace_name = candidate.name.lstrip(".") or candidate.name
        if not namespace_name:
            logger.warning("Skipping workspace namespace path '%s': empty namespace name.", candidate)
            continue
        if namespace_name in seen_names:
            logger.warning(
                "Skipping workspace namespace path '%s': namespace '%s' already registered.",
                candidate,
                namespace_name,
            )
            continue

        namespaces.append(WorkspaceNamespace(name=namespace_name, path=candidate))
        seen_names.add(namespace_name)
        seen_paths.add(candidate)

    return namespaces


def namespace_asset_name(
    namespace_root: str | Path,
    asset_path: str | Path,
    *,
    suffix: str,
    filename_prefix: str | None = None,
) -> str:
    root = Path(namespace_root).resolve()
    resolved_asset = Path(asset_path).resolve()
    relative = resolved_asset.relative_to(root)
    parts = list(relative.parts)
    if not parts:
        return ""

    filename = parts[-1]
    if not filename.endswith(suffix):
        return ""
    basename = filename[: -len(suffix)]
    if filename_prefix:
        if not basename.startswith(filename_prefix):
            return ""
        basename = basename[len(filename_prefix):]
    parts[-1] = basename
    return ".".join(part for part in parts if part)
