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
from typing import Any, Dict, Iterable, List, Optional

import yaml

from pocketcode.core.discovery_rules import DiscoveryFilter
from pocketcode.core.interfaces import BaseTool

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
class ModeDefinition:
    name: str
    description: str = ""
    flow: Optional[str] = None
    agent: Optional[str] = None
    llm_profile: Optional[str] = None
    inline_prompt: str = ""
    extra_prompts: List[str] = field(default_factory=list)
    tools: Optional[List[str]] = None
    tools_specified: bool = False
    tool_confirmation: Dict[str, Any] = field(default_factory=dict)
    source: str = "workspace"
    source_path: Optional[Path] = None


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


class ModeManager:
    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._workspace_pocketcode_root = self._workspace_root / ".pocketcode"
        self._modes_dir = self._workspace_pocketcode_root / "modes"
        self._modes: Dict[str, ModeDefinition] = {}
        self._workspace_filter = DiscoveryFilter.from_root(
            self._workspace_pocketcode_root,
            ignore_dir=self._workspace_pocketcode_root,
        )

    def load(self) -> None:
        self._modes = {}
        self._workspace_filter = DiscoveryFilter.from_root(
            self._workspace_pocketcode_root,
            ignore_dir=self._workspace_pocketcode_root,
        )
        if not self._modes_dir.is_dir():
            return

        for mode_path in sorted(self._modes_dir.rglob("*.md")):
            if self._workspace_filter.ignores(mode_path, is_dir=False):
                continue
            mode = self._load_mode_file(mode_path)
            if mode is None:
                continue
            existing = self._modes.get(mode.name)
            if existing is not None:
                logger.warning(
                    "Mode name collision for '%s': '%s' overrides '%s'.",
                    mode.name,
                    mode_path,
                    existing.source_path,
                )
            self._modes[mode.name] = mode

    def get(self, name: str) -> Optional[ModeDefinition]:
        return self._modes.get(name)

    def list(self) -> list[ModeDefinition]:
        return sorted(self._modes.values(), key=lambda mode: mode.name)

    def get_mode_text(self, name: str) -> str:
        mode = self.get(name)
        if mode is None:
            raise ValueError(f"Unknown mode '{name}'.")
        source_path = mode.source_path
        if source_path is not None and source_path.exists():
            return source_path.read_text(encoding="utf-8")
        return self._dump_mode_text(mode)

    def save_text(self, name: str, markdown_text: str) -> Path:
        mode = self._mode_from_text(markdown_text, source_path=self._modes_dir / f"{name}.md")
        if mode.name != name:
            raise ValueError(
                f"Mode front matter name '{mode.name}' does not match target mode '{name}'. "
                "Use clone to create a differently named mode."
            )
        self._modes_dir.mkdir(parents=True, exist_ok=True)
        target_path = self._modes_dir / f"{name}.md"
        target_path.write_text(markdown_text.strip() + "\n", encoding="utf-8")
        self.load()
        return target_path

    def clone(self, src_name: str, new_name: str) -> Path:
        source_mode = self.get(src_name)
        if source_mode is None:
            raise ValueError(f"Unknown mode '{src_name}'.")
        cleaned_name = str(new_name).strip()
        if not cleaned_name:
            raise ValueError("Mode name cannot be empty.")
        target_path = self._modes_dir / f"{cleaned_name}.md"
        if target_path.exists():
            raise ValueError(
                f"Cannot clone: target file '{target_path}' already exists. "
                "Choose a different name or remove the existing file first."
            )
        cloned_mode = ModeDefinition(
            name=cleaned_name,
            description=source_mode.description,
            flow=source_mode.flow,
            agent=source_mode.agent,
            llm_profile=source_mode.llm_profile,
            inline_prompt=source_mode.inline_prompt,
            extra_prompts=list(source_mode.extra_prompts),
            tools=list(source_mode.tools) if source_mode.tools is not None else None,
            tools_specified=source_mode.tools_specified,
            tool_confirmation=dict(source_mode.tool_confirmation or {}),
            source="workspace",
            source_path=target_path.resolve(),
        )
        self._modes_dir.mkdir(parents=True, exist_ok=True)
        target_path.write_text(self._dump_mode_text(cloned_mode), encoding="utf-8")
        self.load()
        return target_path

    def delete(self, name: str) -> Path:
        mode = self.get(name)
        if mode is None:
            raise ValueError(f"Unknown mode '{name}'.")
        if mode.source_path is None:
            raise ValueError(f"Mode '{name}' has no source path.")
        target_path = Path(mode.source_path)
        if not target_path.exists():
            raise ValueError(f"Mode file does not exist: {target_path}")
        target_path.unlink()
        self.load()
        return target_path

    def _load_mode_file(self, mode_path: Path) -> Optional[ModeDefinition]:
        try:
            return self._mode_from_text(mode_path.read_text(encoding="utf-8"), source_path=mode_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping mode file '%s': %s", mode_path, exc)
            return None

    def _mode_from_text(self, markdown_text: str, *, source_path: Path) -> ModeDefinition:
        front_matter, body = parse_markdown_front_matter(markdown_text)
        raw_name = front_matter.get("name") or source_path.stem
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError(f"Skipping mode file '{source_path}': missing name.")

        tools_specified, tools = normalize_tool_selection(front_matter.get("tools"))
        return ModeDefinition(
            name=raw_name.strip(),
            description=str(front_matter.get("description", "")),
            flow=str(front_matter["flow"]).strip() if front_matter.get("flow") else None,
            agent=str(front_matter["agent"]).strip() if front_matter.get("agent") else None,
            llm_profile=(
                str(front_matter["llm_profile"]).strip()
                if front_matter.get("llm_profile")
                else None
            ),
            inline_prompt=body,
            extra_prompts=coerce_str_list(front_matter.get("extra_prompts")),
            tools=tools,
            tools_specified=tools_specified,
            tool_confirmation=normalize_tool_confirmation(front_matter.get("tool_confirmation")),
            source_path=source_path.resolve(),
        )

    def _dump_mode_text(self, mode: ModeDefinition) -> str:
        front_matter: Dict[str, Any] = {
            "name": mode.name,
        }
        if mode.description:
            front_matter["description"] = mode.description
        if mode.flow:
            front_matter["flow"] = mode.flow
        if mode.agent:
            front_matter["agent"] = mode.agent
        if mode.llm_profile:
            front_matter["llm_profile"] = mode.llm_profile
        if mode.tools_specified:
            front_matter["tools"] = list(mode.tools) if mode.tools is not None else []
        if mode.extra_prompts:
            front_matter["extra_prompts"] = list(mode.extra_prompts)
        if mode.tool_confirmation:
            front_matter["tool_confirmation"] = dict(mode.tool_confirmation)

        front_matter_text = yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=False).strip()
        body = mode.inline_prompt.strip()
        if body:
            return f"---\n{front_matter_text}\n---\n{body}\n"
        return f"---\n{front_matter_text}\n---\n"


class SkillManager:
    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._workspace_pocketcode_root = self._workspace_root / ".pocketcode"
        self._skills_dir = self._workspace_pocketcode_root / "skills"
        self._skills: Dict[str, SkillDefinition] = {}
        self._dynamic_module_names: set[str] = set()
        self._workspace_filter = DiscoveryFilter.from_root(
            self._workspace_pocketcode_root,
            ignore_dir=self._workspace_pocketcode_root,
        )

    def load(self) -> None:
        self._unload_dynamic_modules()
        self._skills = {}
        self._workspace_filter = DiscoveryFilter.from_root(
            self._workspace_pocketcode_root,
            ignore_dir=self._workspace_pocketcode_root,
        )
        if not self._skills_dir.is_dir():
            return

        for skill_dir in sorted(path for path in self._skills_dir.iterdir() if path.is_dir()):
            if self._workspace_filter.ignores(skill_dir, is_dir=True):
                continue
            skill = self._load_skill_dir(skill_dir)
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

    def _load_skill_dir(self, skill_dir: Path) -> Optional[SkillDefinition]:
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

        provided_tools = self._load_skill_tools(skill_dir / "tools", raw_name.strip())
        return SkillDefinition(
            name=raw_name.strip(),
            description=str(front_matter.get("description", "")),
            inline_prompt=body,
            tool_refs=coerce_str_list(front_matter.get("tools")),
            extra_prompts=coerce_str_list(front_matter.get("extra_prompts")),
            provided_tools=provided_tools,
            references=self._list_relative_files(skill_dir / "references", skill_dir),
            scripts=self._list_relative_files(skill_dir / "scripts", skill_dir),
            assets=self._list_relative_files(skill_dir / "assets", skill_dir),
            source_path=skill_path.resolve(),
        )

    def _list_relative_files(self, root: Path, skill_dir: Path) -> list[str]:
        if not root.is_dir():
            return []
        return sorted(
            str(path.resolve().relative_to(skill_dir.resolve()))
            for path in root.rglob("*")
            if path.is_file()
            if not self._workspace_filter.ignores(path, is_dir=False)
        )

    def _load_skill_tools(self, tools_root: Path, skill_name: str) -> Dict[str, Any]:
        loaded: Dict[str, Any] = {}
        if not tools_root.is_dir():
            return loaded

        skill_slug = self._slugify(skill_name)
        for tool_file in sorted(tools_root.rglob("*.py")):
            if tool_file.name == "__init__.py":
                continue
            if self._workspace_filter.ignores(tool_file, is_dir=False):
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
