from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import yaml


def load_stackvm_stdlib_manifest(workspace_root: str | Path) -> dict[str, Any]:
    root = Path(workspace_root).resolve()
    manifest_path = root / "vm" / "stdlib" / "stdlib.yaml"
    if not manifest_path.is_file():
        return {
            "package": "stackvm-stdlib",
            "version": "unversioned",
            "module_root": "vm/stdlib",
            "modules": [],
            "manifest_path": str(manifest_path),
        }

    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid StackVM stdlib manifest: {manifest_path}")

    modules = data.get("modules", [])
    if not isinstance(modules, list):
        modules = []

    normalized_modules: list[dict[str, Any]] = []
    for item in modules:
        if not isinstance(item, dict):
            continue
        exports = item.get("exports", [])
        dependencies = item.get("dependencies", [])
        normalized_modules.append(
            {
                "name": str(item.get("name") or "").strip(),
                "ref": str(item.get("ref") or "").strip(),
                "file": str(item.get("file") or "").strip(),
                "summary": str(item.get("summary") or "").strip(),
                "exports": [str(entry).strip() for entry in exports if str(entry).strip()],
                "dependencies": [str(entry).strip() for entry in dependencies if str(entry).strip()],
            }
        )

    return {
        "package": str(data.get("package") or "stackvm-stdlib").strip() or "stackvm-stdlib",
        "version": str(data.get("version") or "unversioned").strip() or "unversioned",
        "module_root": str(data.get("module_root") or "vm/stdlib").strip() or "vm/stdlib",
        "modules": normalized_modules,
        "manifest_path": str(manifest_path),
    }


def list_stackvm_stdlib_modules(workspace_root: str | Path) -> list[dict[str, Any]]:
    manifest = load_stackvm_stdlib_manifest(workspace_root)
    modules = manifest.get("modules", [])
    if not isinstance(modules, list):
        return []
    return [dict(item) for item in modules if isinstance(item, dict)]


def find_stackvm_stdlib_module(
    module_name: str,
    *,
    search_roots: Iterable[str | Path],
) -> tuple[Path, dict[str, Any]] | None:
    cleaned = str(module_name or "").strip()
    if not cleaned:
        return None

    for root_value in search_roots:
        root = Path(root_value).resolve()
        manifest = load_stackvm_stdlib_manifest(root)
        modules = manifest.get("modules", [])
        if not isinstance(modules, list):
            continue
        for item in modules:
            if not isinstance(item, dict):
                continue
            if str(item.get("name") or "").strip() == cleaned:
                return root, dict(item)
    return None


def resolve_stackvm_stdlib_module_alias(
    module_name: str,
    *,
    search_roots: Iterable[str | Path],
) -> Path | None:
    found = find_stackvm_stdlib_module(module_name, search_roots=search_roots)
    if found is None:
        return None

    root, item = found
    declared_file = str(item.get("file") or "").strip()
    if not declared_file:
        return None

    path = (root / declared_file).resolve()
    if path.is_file():
        return path
    return None
