from __future__ import annotations

from pathlib import Path
from typing import Any

from pocketcode.core.stackvm_loader import (
    _build_module_definition,
    _read_stackvm_file,
    _resolve_stackvm_ref,
)
from pocketcode.core.stackvm_stdlib_manifest import (
    list_stackvm_stdlib_modules,
    load_stackvm_stdlib_manifest,
)


def validate_stackvm_stdlib_manifest(workspace_root: str | Path) -> dict[str, Any]:
    root = Path(workspace_root).resolve()
    manifest = load_stackvm_stdlib_manifest(root)
    module_entries = manifest.get("modules", [])
    if not isinstance(module_entries, list):
        module_entries = []

    results: list[dict[str, Any]] = []
    error_count = 0
    warning_count = 0
    known_module_names = {
        str(item.get("name") or "").strip()
        for item in module_entries
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }

    for item in module_entries:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        ref = str(item.get("ref") or "").strip()
        declared_file = str(item.get("file") or "").strip()
        declared_exports = [str(entry).strip() for entry in item.get("exports") or [] if str(entry).strip()]
        declared_dependencies = [str(entry).strip() for entry in item.get("dependencies") or [] if str(entry).strip()]
        result = {
            "name": name,
            "ref": ref,
            "declared_file": declared_file,
            "declared_exports": list(declared_exports),
            "declared_dependencies": list(declared_dependencies),
            "resolved_file": None,
            "actual_module_name": None,
            "actual_exports": [],
            "actual_dependencies": [],
            "valid": True,
            "errors": [],
            "warnings": [],
        }
        try:
            resolved_path = _resolve_stackvm_ref(ref=ref, base_dir=root, search_roots=(root,))
            result["resolved_file"] = str(resolved_path.relative_to(root).as_posix())
            source = _read_stackvm_file(resolved_path)
            definition = _build_module_definition(
                ref=ref,
                source=source,
                source_path=resolved_path,
                compatibility_prefix=None,
            )
            result["actual_module_name"] = definition.module_name
            result["actual_exports"] = sorted(definition.export_names)
            actual_dependencies = sorted(
                {
                    imported.target_name.rsplit(".", 1)[0]
                    for imported in definition.imports
                    if imported.target_name.startswith("stdlib.") and "." in imported.target_name
                }
            )
            result["actual_dependencies"] = actual_dependencies

            if declared_file and declared_file != result["resolved_file"]:
                result["warnings"].append(
                    f"Declared file '{declared_file}' resolved to '{result['resolved_file']}'."
                )
            if name and definition.module_name != name:
                result["errors"].append(
                    f"Declared module name '{name}' does not match actual module name '{definition.module_name}'."
                )
            if sorted(declared_exports) != sorted(definition.export_names):
                missing = sorted(set(declared_exports) - set(definition.export_names))
                extra = sorted(set(definition.export_names) - set(declared_exports))
                if missing:
                    result["errors"].append(f"Manifest exports missing from module: {', '.join(missing)}.")
                if extra:
                    result["errors"].append(f"Module exports missing from manifest: {', '.join(extra)}.")
            unknown_dependencies = sorted(dep for dep in declared_dependencies if dep not in known_module_names)
            if unknown_dependencies:
                result["errors"].append(
                    f"Manifest dependencies missing from package manifest: {', '.join(unknown_dependencies)}."
                )
            if sorted(declared_dependencies) != actual_dependencies:
                missing = sorted(set(declared_dependencies) - set(actual_dependencies))
                extra = sorted(set(actual_dependencies) - set(declared_dependencies))
                if missing:
                    result["errors"].append(f"Manifest dependencies missing from module imports: {', '.join(missing)}.")
                if extra:
                    result["errors"].append(f"Module imports missing from manifest dependencies: {', '.join(extra)}.")
        except Exception as exc:
            result["errors"].append(str(exc))

        result["valid"] = not result["errors"]
        error_count += len(result["errors"])
        warning_count += len(result["warnings"])
        results.append(result)

    return {
        "package": manifest.get("package") or "stackvm-stdlib",
        "version": manifest.get("version") or "unversioned",
        "module_root": manifest.get("module_root") or "vm/stdlib",
        "manifest_path": manifest.get("manifest_path"),
        "module_count": len(results),
        "error_count": error_count,
        "warning_count": warning_count,
        "valid": error_count == 0,
        "modules": results,
    }
