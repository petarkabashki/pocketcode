from __future__ import annotations

import hashlib
import importlib.util
import inspect
import logging
import re
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import yaml

from pocketcode.core.discovery_rules import DiscoveryFilter
from pocketcode.core.interfaces import BaseTool
from pocketcode.core.prompt_loader import is_prompt_reference, load_prompt_markdown, resolve_prompt_reference
from pocketcode.core.reference_syntax import (
    normalize_prompt_source,
    normalize_registry_reference,
    validate_prompt_source,
    validate_registry_reference,
)
from pocketcode.core.resource_roots import ResourceRoot, discover_resource_roots, primary_resource_root
from pocketcode.core.tool_conventions import iter_tool_module_files

logger = logging.getLogger(__name__)

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_markdown_front_matter(markdown_text: str) -> tuple[Dict[str, Any], str]:
    match = _FRONT_MATTER_RE.match(markdown_text)
    if not match:
        return {}, markdown_text.strip()

    raw_front_matter = match.group(1)
    front_matter = yaml.safe_load(raw_front_matter) or {}
    if not isinstance(front_matter, dict):
        raise ValueError("Markdown front matter must be a YAML mapping.")
    return front_matter, markdown_text[match.end() :].strip()


def coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def normalize_tool_confirmation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    overrides = value.get("overrides", {})
    return {
        "default": str(value["default"]) if value.get("default") else None,
        "overrides": {
            str(tool_name): str(policy)
            for tool_name, policy in overrides.items()
            if isinstance(tool_name, str) and isinstance(policy, str)
        }
        if isinstance(overrides, dict)
        else {},
    }


def normalize_tool_selection(
    raw_value: Any,
) -> tuple[bool, Optional[list[str]]]:
    if raw_value is None:
        return False, None
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in {"inherit", "default"}:
            return False, None
        if normalized in {"all", "*"}:
            return True, None
        if normalized in {"none", "deny"}:
            return True, []
        return True, [raw_value.strip()]
    return True, coerce_str_list(raw_value)


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str = ""
    inline_prompt: str = ""
    tool_refs: List[str] = field(default_factory=list)
    extra_prompts: List[str] = field(default_factory=list)
    provided_tools: Dict[str, Any] = field(default_factory=dict)
    references: List[str] = field(default_factory=list)
    scripts: List[str] = field(default_factory=list)
    assets: List[str] = field(default_factory=list)
    source: str = "workspace"
    source_path: Optional[Path] = None


class SkillManager:
    def __init__(
        self,
        workspace_root: Path,
        *,
        tool_registry: Any | None = None,
        prompt_registry: Any | None = None,
    ) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._tool_registry = tool_registry
        self._prompt_registry = prompt_registry
        self._resource_roots: list[ResourceRoot] = discover_resource_roots(self._workspace_root)
        self._primary_resource_root = primary_resource_root(self._workspace_root, self._resource_roots)
        self._skills_dir = self._primary_resource_root.path / "skills"
        self._skills: Dict[str, SkillDefinition] = {}
        self._dynamic_module_names: set[str] = set()
        self._resource_root_filters = self._build_resource_root_filters()

    def set_registries(
        self,
        *,
        tool_registry: Any | None = None,
        prompt_registry: Any | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._prompt_registry = prompt_registry

    def load(self) -> None:
        self._unload_dynamic_modules()
        self._skills = {}
        self._resource_roots = discover_resource_roots(self._workspace_root)
        self._primary_resource_root = primary_resource_root(self._workspace_root, self._resource_roots)
        self._skills_dir = self._primary_resource_root.path / "skills"
        self._resource_root_filters = self._build_resource_root_filters()

        for resource_root in self._resource_roots:
            resource_filter = self._resource_root_filter(resource_root)
            for skill_dir in self._iter_skill_dirs(resource_root):
                if resource_filter.ignores(skill_dir, is_dir=True):
                    continue
                skill = self._load_skill_dir(skill_dir, resource_root)
                if skill is None:
                    continue
                existing = self._skills.get(skill.name)
                if existing is not None:
                    logger.warning(
                        "Skill name collision for '%s': '%s' overrides '%s'.",
                        skill.name,
                        skill.source_path,
                        existing.source_path,
                    )
                self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[SkillDefinition]:
        return self._skills.get(name)

    def list(self) -> list[SkillDefinition]:
        return sorted(self._skills.values(), key=lambda skill: skill.name)

    def _load_skill_dir(self, skill_dir: Path, resource_root: ResourceRoot) -> Optional[SkillDefinition]:
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.is_file():
            return None

        try:
            front_matter, body = parse_markdown_front_matter(
                skill_path.read_text(encoding="utf-8")
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping skill '%s': %s", skill_dir.name, exc)
            return None

        raw_name = front_matter.get("name") or skill_dir.name
        if not isinstance(raw_name, str) or not raw_name.strip():
            logger.warning("Skipping skill '%s': missing name.", skill_dir)
            return None

        try:
            provided_tools = self._load_skill_tools(skill_dir / "tools", raw_name.strip(), resource_root)
            tool_refs = coerce_str_list(front_matter.get("tools"))
            for index, tool_ref in enumerate(tool_refs):
                validate_registry_reference(
                    tool_ref,
                    allowed_kinds={"tool"},
                    field_name=f"{skill_path.name}: tools[{index}]",
                )
            tool_refs = [normalize_registry_reference(tool_ref, allowed_kinds={"tool"}) for tool_ref in tool_refs]
            for index, tool_ref in enumerate(tool_refs):
                self._qualify_registry_reference_or_raise(
                    self._tool_registry,
                    tool_ref,
                    field_name=f"{skill_path.name}: tools[{index}]",
                )
            extra_prompts = coerce_str_list(front_matter.get("extra_prompts"))
            for index, prompt_ref in enumerate(extra_prompts):
                validate_prompt_source(prompt_ref, field_name=f"{skill_path.name}: extra_prompts[{index}]")
            extra_prompts = [normalize_prompt_source(prompt_ref) for prompt_ref in extra_prompts]
            for index, prompt_ref in enumerate(extra_prompts):
                self._validate_prompt_source_reference(
                    prompt_ref,
                    source_path=skill_path,
                    field_name=f"{skill_path.name}: extra_prompts[{index}]",
                )
            return SkillDefinition(
                name=raw_name.strip(),
                description=str(front_matter.get("description", "")),
                inline_prompt=body,
                tool_refs=tool_refs,
                extra_prompts=extra_prompts,
                provided_tools=provided_tools,
                references=self._list_relative_files(skill_dir / "references", skill_dir, resource_root),
                scripts=self._list_relative_files(skill_dir / "scripts", skill_dir, resource_root),
                assets=self._list_relative_files(skill_dir / "assets", skill_dir, resource_root),
                source_path=skill_path.resolve(),
            )
        except ValueError as exc:
            logger.warning("Skipping skill '%s': %s", skill_dir.name, exc)
            return None

    def _list_relative_files(self, root: Path, skill_dir: Path, resource_root: ResourceRoot) -> list[str]:
        if not root.is_dir():
            return []
        resource_filter = self._resource_root_filter(resource_root)
        return sorted(
            str(path.resolve().relative_to(skill_dir.resolve()))
            for path in root.rglob("*")
            if path.is_file()
            if not resource_filter.ignores(path, is_dir=False)
        )

    def _load_skill_tools(self, tools_root: Path, skill_name: str, resource_root: ResourceRoot) -> Dict[str, Any]:
        loaded: Dict[str, Any] = {}
        if not tools_root.is_dir():
            return loaded

        skill_slug = self._slugify(skill_name)
        resource_filter = self._resource_root_filter(resource_root)
        for tool_file in iter_tool_module_files(tools_root):
            if resource_filter.ignores(tool_file, is_dir=False):
                continue
            try:
                module = self._load_module_from_file(tool_file)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed loading skill tool module '%s': %s",
                    tool_file,
                    exc,
                )
                continue

            for tool_name, tool_impl in self._iter_workspace_tool_exports(module):
                qualified_name = f"skill.{skill_slug}.{tool_name}"
                loaded[qualified_name] = tool_impl
        return loaded

    def _iter_skill_dirs(self, resource_root: ResourceRoot) -> list[Path]:
        candidates: list[Path] = []
        seen: set[Path] = set()

        skills_dir = resource_root.path / "skills"
        if skills_dir.is_dir():
            for path in sorted(candidate for candidate in skills_dir.iterdir() if candidate.is_dir()):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                candidates.append(path)

        for path in sorted(candidate for candidate in resource_root.path.iterdir() if candidate.is_dir()):
            if not path.name.startswith("skill."):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(path)

        return candidates

    def _build_resource_root_filters(self) -> Dict[Path, DiscoveryFilter]:
        return {
            resource_root.path.resolve(): DiscoveryFilter.from_root(
                resource_root.path,
                ignore_dir=resource_root.path,
            )
            for resource_root in self._resource_roots
        }

    def _resource_root_filter(self, resource_root: ResourceRoot) -> DiscoveryFilter:
        return self._resource_root_filters[resource_root.path.resolve()]

    def _workspace_prompt_fallback_dirs(self) -> tuple[Path, ...]:
        return (self._primary_resource_root.path / "prompts",)

    def _qualify_registry_reference_or_raise(self, registry: Any, reference: str, *, field_name: str) -> str:
        if registry is None:
            return reference
        try:
            return registry.qualify(reference, context_namespace="workspace")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"{field_name} could not be resolved: {reference} ({exc})") from exc

    def _validate_prompt_source_reference(self, prompt_ref: str, *, source_path: Path, field_name: str) -> None:
        if is_prompt_reference(prompt_ref):
            if self._prompt_registry is None:
                return
            try:
                resolve_prompt_reference(
                    prompt_ref,
                    prompt_registry=self._prompt_registry,
                    context_namespace="workspace",
                )
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"{field_name} could not be resolved: {prompt_ref} ({exc})") from exc
            return
        try:
            load_prompt_markdown(
                base_dir=source_path.parent,
                prompt_file=prompt_ref,
                fallback_dirs=self._workspace_prompt_fallback_dirs(),
                prompt_registry=self._prompt_registry,
                context_namespace="workspace",
            )
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"{field_name} could not be resolved: {prompt_ref} ({exc})") from exc

    def _load_module_from_file(self, file_path: Path) -> types.ModuleType:
        digest = hashlib.sha1(str(file_path.resolve()).encode("utf-8")).hexdigest()[:12]
        module_name = f"pocketcode.dynamic.skill_{digest}"
        self._dynamic_module_names.add(module_name)
        sys.modules.pop(module_name, None)
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module spec for '{file_path}'.")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def _iter_workspace_tool_exports(self, module: types.ModuleType) -> Iterable[tuple[str, Any]]:
        exports = getattr(module, "TOOLS", None)
        if exports is not None:
            yield from self._normalize_workspace_tool_exports(module, exports)
            return

        seen: set[str] = set()
        for name, value in sorted(module.__dict__.items()):
            if name.startswith("_"):
                continue
            if not self._is_workspace_tool_candidate(module, value):
                continue
            if name in seen:
                continue
            seen.add(name)
            yield name, value

    def _normalize_workspace_tool_exports(
        self,
        module: types.ModuleType,
        exports: Any,
    ) -> Iterable[tuple[str, Any]]:
        if isinstance(exports, dict):
            for raw_name, raw_value in exports.items():
                if not isinstance(raw_name, str) or not raw_name.strip():
                    continue
                resolved = self._resolve_workspace_tool_export(module, raw_value)
                if resolved is not None:
                    yield raw_name.strip(), resolved
            return

        if isinstance(exports, (list, tuple, set)):
            for raw_value in exports:
                resolved_name, resolved_value = self._resolve_workspace_tool_export_entry(
                    module,
                    raw_value,
                )
                if resolved_name and resolved_value is not None:
                    yield resolved_name, resolved_value

    def _resolve_workspace_tool_export_entry(
        self,
        module: types.ModuleType,
        raw_value: Any,
    ) -> tuple[str | None, Any | None]:
        if isinstance(raw_value, str):
            candidate = getattr(module, raw_value, None)
            if candidate is not None and self._is_workspace_tool_candidate(module, candidate):
                return raw_value, candidate
            return None, None

        if self._is_workspace_tool_candidate(module, raw_value):
            inferred_name = getattr(raw_value, "__name__", getattr(raw_value, "name", None))
            if isinstance(inferred_name, str) and inferred_name.strip():
                return inferred_name.strip(), raw_value
        return None, None

    def _resolve_workspace_tool_export(self, module: types.ModuleType, raw_value: Any) -> Any | None:
        if isinstance(raw_value, str):
            raw_value = getattr(module, raw_value, None)
        if raw_value is not None and self._is_workspace_tool_candidate(module, raw_value):
            return raw_value
        return None

    def _is_workspace_tool_candidate(self, module: types.ModuleType, value: Any) -> bool:
        if inspect.isfunction(value):
            return value.__module__ == module.__name__
        if isinstance(value, type) and issubclass(value, BaseTool) and value is not BaseTool:
            return value.__module__ == module.__name__
        if isinstance(value, BaseTool):
            return value.__class__.__module__ == module.__name__
        if callable(value):
            return getattr(value.__class__, "__module__", None) == module.__name__
        return False

    def _unload_dynamic_modules(self) -> None:
        for module_name in list(self._dynamic_module_names):
            sys.modules.pop(module_name, None)
        self._dynamic_module_names.clear()

    def _slugify(self, value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
        return normalized or "skill"
