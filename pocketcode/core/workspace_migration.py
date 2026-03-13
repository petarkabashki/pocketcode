from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pocketcode.config.loader import WORKSPACE_SETTINGS_FILENAME
from pocketcode.core.reference_syntax import normalize_prompt_source, normalize_registry_reference
from pocketcode.core.resource_roots import primary_resource_root, resource_root_namespace
from pocketcode.core.runtime_storage import entry_history_file_path, session_storage_dir

logger = logging.getLogger(__name__)

REFERENCE_SCALAR_KEYS = {
    "active_agent": {"agent", "flow"},
    "active_profile": {"agent", "flow"},
    "default_agent": {"agent", "flow"},
    "flow": {"agent", "flow"},
    "extends": {"agent", "flow"},
    "base_agent": {"agent", "flow"},
}
REFERENCE_LIST_KEYS = {
    "tools": {"tool"},
    "hooks": {"hook"},
}
PROMPT_LIST_KEYS = {"extra_prompts"}
SHIM_FILE_MARKER = "Compatibility re-export"
WORKSPACE_NAMESPACE_PREFIX = "workspace."
WORKSPACE_PROMPT_PREFIX = "prompt:workspace#"
WORKSPACE_PROMPT_DOTTED_PREFIX = "prompt:workspace."


class WorkspaceMigrationRequiredError(RuntimeError):
    pass


@dataclass
class WorkspaceMigrationReport:
    changed_files: list[str] = field(default_factory=list)
    moved_paths: list[dict[str, str]] = field(default_factory=list)
    removed_paths: list[str] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)

    def mark_changed(self, path: Path) -> None:
        path_text = str(path.resolve())
        if path_text not in self.changed_files:
            self.changed_files.append(path_text)

    def add_move(self, src: Path, dest: Path) -> None:
        self.moved_paths.append({"from": str(src.resolve()), "to": str(dest.resolve())})

    def add_removed(self, path: Path) -> None:
        self.removed_paths.append(str(path.resolve()))

    @property
    def changed(self) -> bool:
        return bool(self.changed_files or self.moved_paths or self.removed_paths)

    def as_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "changed_files": list(self.changed_files),
            "moved_paths": list(self.moved_paths),
            "removed_paths": list(self.removed_paths),
            "summary": list(self.summary),
        }


def migrate_workspace(workspace_root: str | Path) -> WorkspaceMigrationReport:
    root = Path(workspace_root).resolve()
    report = WorkspaceMigrationReport()

    _migrate_config(root, report)
    _migrate_sessions(root, report)
    _migrate_resource_roots(root, report)
    _remove_workspace_shims(root, report)
    _write_report(root, report)
    if not report.summary:
        report.summary.append("No unsupported workspace artifacts found.")
    return report


def ensure_workspace_migration(workspace_root: str | Path, *, auto_apply: bool) -> WorkspaceMigrationReport:
    root = Path(workspace_root).resolve()
    issues = scan_workspace_migration(root)
    if not issues:
        return WorkspaceMigrationReport(summary=["Workspace already canonical."])
    if auto_apply:
        return migrate_workspace(root)
    message = (
        "Unsupported workspace state detected. Run `pocketcode --migrate-workspace` "
        "or `/migrate workspace` before starting the runtime."
    )
    raise WorkspaceMigrationRequiredError(message)


def scan_workspace_migration(workspace_root: str | Path) -> list[str]:
    root = Path(workspace_root).resolve()
    issues: list[str] = []
    config_path = root / WORKSPACE_SETTINGS_FILENAME
    if config_path.is_file():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        textual = ((raw.get("runtime") or {}).get("textual") or {}) if isinstance(raw, dict) else {}
        if isinstance(textual, dict):
            if "workspace_mode" in textual:
                issues.append(f"{config_path}: runtime.textual.workspace_mode")
            if "user_input_popups" in textual:
                issues.append(f"{config_path}: runtime.textual.user_input_popups")
        if _contains_noncanonical_references(raw):
            issues.append(f"{config_path}: unsupported registry references")

    sessions_dir = session_storage_dir(root, {})
    if sessions_dir.exists():
        for session_file in sessions_dir.glob("*.json"):
            try:
                raw = json.loads(session_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if _contains_noncanonical_references(raw):
                issues.append(f"{session_file}: unsupported registry references")

    for resource_root in sorted(path for path in root.iterdir() if path.is_dir() and path.name.startswith(".pocket")):
        for path in resource_root.glob("*.agent.yaml"):
            issues.append(f"{path}: flat workspace agent")
        for path in resource_root.glob("*.agent.md"):
            issues.append(f"{path}: flat workspace agent")
        for path in resource_root.iterdir():
            if path.is_dir() and path.name.startswith("skill."):
                issues.append(f"{path}: skill alias directory")
            if path.is_file() and _is_workspace_compat_shim(path):
                issues.append(f"{path}: shim module")
    return issues


def _migrate_config(root: Path, report: WorkspaceMigrationReport) -> None:
    config_path = root / WORKSPACE_SETTINGS_FILENAME
    if not config_path.is_file():
        return
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return

    runtime = raw.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
        raw["runtime"] = runtime
    textual = runtime.get("textual")
    if not isinstance(textual, dict):
        textual = {}
        runtime["textual"] = textual

    workspace_mode = textual.pop("workspace_mode", None)
    if workspace_mode and not textual.get("workspace_view"):
        textual["workspace_view"] = workspace_mode
    if "user_input_popups" in textual:
        user_input_popups = bool(textual.pop("user_input_popups"))
        if not textual.get("control_presentation"):
            textual["control_presentation"] = "modal" if user_input_popups else "inline"

    migrated = _normalize_config_tree(raw, workspace_alias_namespace=_default_resource_namespace(root))
    if migrated != raw:
        raw = migrated
    config_text = yaml.safe_dump(raw, sort_keys=False)
    original_text = config_path.read_text(encoding="utf-8")
    if config_text != original_text:
        _atomic_write(config_path, config_text)
        report.mark_changed(config_path)
        report.summary.append("Migrated pocketcode.yml to canonical config keys and resource-root registry ids.")


def _migrate_sessions(root: Path, report: WorkspaceMigrationReport) -> None:
    sessions_dir = session_storage_dir(root, {})
    if not sessions_dir.exists():
        return
    for session_file in sorted(sessions_dir.glob("*.json")):
        try:
            raw = json.loads(session_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Skipping unreadable session file '%s' during workspace migration: %s", session_file, exc)
            continue
        migrated = _normalize_session_tree(raw, workspace_alias_namespace=_default_resource_namespace(root))
        if migrated == raw:
            continue
        _atomic_write(session_file, json.dumps(migrated, indent=2, sort_keys=False))
        report.mark_changed(session_file)
    history_file = entry_history_file_path(root, {})
    if history_file.exists():
        try:
            json.loads(history_file.read_text(encoding="utf-8"))
        except Exception:
            history_file.unlink()
            report.add_removed(history_file)
    if any(path.endswith(".json") for path in report.changed_files):
        report.summary.append("Migrated saved session state to canonical resource-root registry ids.")


def _migrate_resource_roots(root: Path, report: WorkspaceMigrationReport) -> None:
    for resource_root in sorted(path for path in root.iterdir() if path.is_dir() and path.name.startswith(".pocket")):
        _migrate_flat_agent_files(resource_root, report)
        _migrate_skill_alias_dirs(resource_root, report)
        _migrate_flow_prompt_aliases(resource_root, report)


def _migrate_flat_agent_files(resource_root: Path, report: WorkspaceMigrationReport) -> None:
    for source_path in sorted(resource_root.glob("*.agent.yaml")) + sorted(resource_root.glob("*.agent.md")):
        payload, body = _load_structured_document(source_path)
        agent_name = str(payload.get("name") or _asset_name_from_path(source_path, ".agent.yaml", ".agent.md")).strip()
        if not agent_name:
            continue
        payload = _normalize_agent_payload(payload, workspace_alias_namespace=_default_resource_namespace(resource_root))
        target_path = _grouped_agent_path(resource_root, agent_name, source_path.suffixes[-2] + source_path.suffixes[-1])
        if target_path.resolve() != source_path.resolve():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            _write_structured_document(target_path, payload, body, markdown=source_path.name.endswith(".md"))
            source_path.unlink()
            report.add_move(source_path, target_path)
            report.mark_changed(target_path)
        else:
            rendered = _render_structured_document(payload, body, markdown=source_path.name.endswith(".md"))
            if rendered != source_path.read_text(encoding="utf-8"):
                _atomic_write(source_path, rendered)
                report.mark_changed(source_path)
    if report.moved_paths:
        report.summary.append("Moved flat workspace agent files into grouped agent.<group>/ layout.")


def _migrate_skill_alias_dirs(resource_root: Path, report: WorkspaceMigrationReport) -> None:
    for skill_dir in sorted(path for path in resource_root.iterdir() if path.is_dir() and path.name.startswith("skill.")):
        skill_name = skill_dir.name.split(".", 1)[1].strip()
        if not skill_name:
            continue
        target_dir = resource_root / "skills" / skill_name
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        if target_dir.exists():
            raise WorkspaceMigrationRequiredError(
                f"Cannot migrate '{skill_dir}' because canonical skill directory '{target_dir}' already exists."
            )
        shutil.move(str(skill_dir), str(target_dir))
        report.add_move(skill_dir, target_dir)
        skill_md = target_dir / "SKILL.md"
        if skill_md.is_file():
            payload, body = _load_structured_document(skill_md)
            payload = _normalize_skill_payload(payload, workspace_alias_namespace=_default_resource_namespace(resource_root))
            rendered = _render_structured_document(payload, body, markdown=True)
            if rendered != skill_md.read_text(encoding="utf-8"):
                _atomic_write(skill_md, rendered)
                report.mark_changed(skill_md)
    if any("skills/" in item["to"] for item in report.moved_paths):
        report.summary.append("Moved skill.<name> bundles into skills/<name>/.")


def _migrate_flow_prompt_aliases(resource_root: Path, report: WorkspaceMigrationReport) -> None:
    for markdown_path in sorted(path for path in resource_root.rglob("*.md") if path.is_file()):
        if markdown_path.name.endswith((".prompt.md", ".tool.md", ".hook.md", ".agent.md", "SKILL.md")):
            continue
        payload, body = _load_structured_document(markdown_path)
        if not payload or "prompts" not in payload or "prompt_files" in payload:
            continue
        payload["prompt_files"] = payload.pop("prompts")
        _write_structured_document(markdown_path, payload, body, markdown=True)
        report.mark_changed(markdown_path)
    if any(path.endswith(".md") for path in report.changed_files):
        if "Migrated flow prompt aliases to prompt_files." not in report.summary:
            report.summary.append("Migrated flow prompt aliases to prompt_files.")


def _remove_workspace_shims(root: Path, report: WorkspaceMigrationReport) -> None:
    workspace_root = root / ".pocketcode"
    if not workspace_root.is_dir():
        return
    for shim_path in sorted(path for path in workspace_root.glob("*.tool.py") if path.is_file()):
        if not _is_workspace_compat_shim(shim_path):
            continue
        shim_path.unlink()
        report.add_removed(shim_path)
    if report.removed_paths:
        report.summary.append("Removed workspace shim modules.")


def _write_report(root: Path, report: WorkspaceMigrationReport) -> None:
    report_path = root / ".pocketstate" / "workspace_migration_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(report_path, json.dumps(report.as_dict(), indent=2, sort_keys=False))


def _normalize_config_tree(value: Any, *, workspace_alias_namespace: str) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text == "session_confirmation_overrides" and isinstance(item, dict):
                normalized[key_text] = _normalize_confirmation_override_map(
                    item,
                    workspace_alias_namespace=workspace_alias_namespace,
                )
                continue
            normalized[key_text] = _normalize_mapping_value(
                key_text,
                item,
                workspace_alias_namespace=workspace_alias_namespace,
            )
        return normalized
    if isinstance(value, list):
        return [_normalize_config_tree(item, workspace_alias_namespace=workspace_alias_namespace) for item in value]
    return value


def _normalize_session_tree(value: Any, *, workspace_alias_namespace: str) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in {"session_profile_overrides", "session_confirmation_overrides"} and isinstance(item, dict):
                normalized[key_text] = _normalize_session_override_map(
                    item,
                    workspace_alias_namespace=workspace_alias_namespace,
                )
                continue
            normalized[key_text] = _normalize_mapping_value(
                key_text,
                item,
                workspace_alias_namespace=workspace_alias_namespace,
            )
        return normalized
    if isinstance(value, list):
        return [_normalize_session_tree(item, workspace_alias_namespace=workspace_alias_namespace) for item in value]
    return value


def _normalize_session_override_map(value: dict[str, Any], *, workspace_alias_namespace: str) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        normalized_key = _normalize_reference_scalar(
            str(key),
            {"agent", "flow"},
            workspace_alias_namespace=workspace_alias_namespace,
        )
        normalized[normalized_key] = _normalize_session_tree(item, workspace_alias_namespace=workspace_alias_namespace)
    return normalized


def _normalize_confirmation_override_map(value: dict[str, Any], *, workspace_alias_namespace: str) -> dict[str, Any]:
    normalized = dict(value)
    for field in ("tool_policies", "agent_policies"):
        current = normalized.get(field)
        if not isinstance(current, dict):
            continue
        kinds = {"tool"} if field == "tool_policies" else {"agent", "flow"}
        normalized[field] = {
            _normalize_reference_scalar(str(key), kinds, workspace_alias_namespace=workspace_alias_namespace): (
                _normalize_config_tree(item, workspace_alias_namespace=workspace_alias_namespace)
            )
            for key, item in current.items()
        }
    return normalized


def _normalize_mapping_value(key: str, value: Any, *, workspace_alias_namespace: str) -> Any:
    if key in REFERENCE_SCALAR_KEYS and isinstance(value, str):
        return _normalize_reference_scalar(value, REFERENCE_SCALAR_KEYS[key], workspace_alias_namespace=workspace_alias_namespace)
    if key in REFERENCE_LIST_KEYS and isinstance(value, list):
        kinds = REFERENCE_LIST_KEYS[key]
        return [
            _normalize_reference_scalar(str(item), kinds, workspace_alias_namespace=workspace_alias_namespace)
            for item in value
        ]
    if key in PROMPT_LIST_KEYS and isinstance(value, list):
        return [
            normalize_prompt_source(_normalize_workspace_namespace_alias(str(item), workspace_alias_namespace))
            for item in value
        ]
    if key == "overrides" and isinstance(value, dict):
        return {
            _normalize_reference_scalar(
                str(item_key),
                {"tool"},
                workspace_alias_namespace=workspace_alias_namespace,
            ): _normalize_config_tree(item_value, workspace_alias_namespace=workspace_alias_namespace)
            for item_key, item_value in value.items()
        }
    return _normalize_config_tree(value, workspace_alias_namespace=workspace_alias_namespace)


def _normalize_agent_payload(payload: dict[str, Any], *, workspace_alias_namespace: str) -> dict[str, Any]:
    normalized = _normalize_config_tree(payload, workspace_alias_namespace=workspace_alias_namespace)
    if "agent" in normalized and "flow" not in normalized:
        normalized["flow"] = _normalize_reference_scalar(
            str(normalized.pop("agent")),
            {"agent", "flow"},
            workspace_alias_namespace=workspace_alias_namespace,
        )
    return normalized


def _normalize_skill_payload(payload: dict[str, Any], *, workspace_alias_namespace: str) -> dict[str, Any]:
    return _normalize_config_tree(payload, workspace_alias_namespace=workspace_alias_namespace)


def _normalize_reference_scalar(value: str, allowed_kinds: set[str], *, workspace_alias_namespace: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    cleaned = _normalize_workspace_namespace_alias(cleaned, workspace_alias_namespace)
    if cleaned.startswith("prompt:"):
        return normalize_prompt_source(cleaned)
    return normalize_registry_reference(cleaned.replace("::", "."), allowed_kinds=allowed_kinds)


def _contains_noncanonical_references(value: Any) -> bool:
    if isinstance(value, str):
        return "::" in value or value.startswith(WORKSPACE_NAMESPACE_PREFIX) or value.startswith(
            (WORKSPACE_PROMPT_PREFIX, WORKSPACE_PROMPT_DOTTED_PREFIX)
        )
    if isinstance(value, dict):
        return any(_contains_noncanonical_references(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_noncanonical_references(item) for item in value)
    return False


def _normalize_workspace_namespace_alias(value: str, workspace_alias_namespace: str) -> str:
    if value.startswith(WORKSPACE_PROMPT_PREFIX):
        return f"prompt:{workspace_alias_namespace}.{value[len(WORKSPACE_PROMPT_PREFIX):]}"
    if value.startswith(WORKSPACE_PROMPT_DOTTED_PREFIX):
        return f"prompt:{workspace_alias_namespace}.{value[len(WORKSPACE_PROMPT_DOTTED_PREFIX):]}"
    if value.startswith(WORKSPACE_NAMESPACE_PREFIX):
        return f"{workspace_alias_namespace}.{value[len(WORKSPACE_NAMESPACE_PREFIX):]}"
    return value


def _default_resource_namespace(root: Path) -> str:
    return resource_root_namespace(primary_resource_root(root))


def _load_structured_document(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if path.name.endswith(".md"):
        if text.startswith("---\n"):
            _, rest = text.split("---\n", 1)
            front_matter, body = rest.split("\n---\n", 1)
            payload = yaml.safe_load(front_matter) or {}
            return dict(payload), body.lstrip("\n")
        return {}, text
    payload = yaml.safe_load(text) or {}
    return dict(payload), ""


def _render_structured_document(payload: dict[str, Any], body: str, *, markdown: bool) -> str:
    serialized = yaml.safe_dump(payload, sort_keys=False).strip()
    if not markdown:
        return f"{serialized}\n"
    body_text = body.lstrip("\n")
    if body_text:
        return f"---\n{serialized}\n---\n{body_text}"
    return f"---\n{serialized}\n---\n"


def _write_structured_document(path: Path, payload: dict[str, Any], body: str, *, markdown: bool) -> None:
    _atomic_write(path, _render_structured_document(payload, body, markdown=markdown))


def _asset_name_from_path(path: Path, *suffixes: str) -> str:
    name = path.name
    for suffix in suffixes:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def _grouped_agent_path(resource_root: Path, agent_name: str, suffix: str) -> Path:
    parts = [part for part in str(agent_name).split(".") if part]
    group = parts[0]
    relative_parts = parts[1:] or [group]
    target_dir = resource_root / f"agent.{group}"
    if len(relative_parts) > 1:
        target_dir = target_dir.joinpath(*relative_parts[:-1])
    return target_dir / f"{relative_parts[-1]}{suffix}"


def _is_workspace_compat_shim(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return False
    return SHIM_FILE_MARKER in text


def _atomic_write(path: Path, content: str) -> None:
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)
