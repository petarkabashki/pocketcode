from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import yaml

from pocketcode.core.interfaces import BaseTool
from pocketcode.core.prompt_loader import expand_prompt_markdown_text, load_prompt_markdown


@dataclass(frozen=True)
class MarkdownAssetBlock:
    language: str
    label: str = ""
    content: str = ""


@dataclass(frozen=True)
class MarkdownAssetDocument:
    source_path: Path
    front_matter: Dict[str, Any] = field(default_factory=dict)
    body: str = ""
    blocks: List[MarkdownAssetBlock] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    def find_blocks(
        self,
        *,
        languages: Iterable[str] | None = None,
        labels: Iterable[str] | None = None,
    ) -> list[MarkdownAssetBlock]:
        normalized_languages = {value.strip().lower() for value in (languages or []) if str(value).strip()}
        normalized_labels = {value.strip().lower() for value in (labels or []) if str(value).strip()}

        results: list[MarkdownAssetBlock] = []
        for block in self.blocks:
            language = block.language.strip().lower()
            label = block.label.strip().lower()
            if normalized_languages and language not in normalized_languages:
                continue
            if normalized_labels and label not in normalized_labels:
                continue
            results.append(block)
        return results


@dataclass(frozen=True)
class MarkdownToolDefinition:
    name: str
    description: str
    handler: str
    schema: Dict[str, Any] = field(default_factory=dict)
    execution_mode: str | None = None
    timeout_seconds: float | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None


def load_markdown_asset_document(
    path: Path,
    *,
    fallback_dirs: Sequence[Path] = (),
    prompt_registry: Any | None = None,
    context_namespace: str | None = None,
) -> MarkdownAssetDocument:
    resolved_path = Path(path).resolve()
    expanded_text, sources = load_prompt_markdown(
        base_dir=resolved_path.parent,
        prompt_file=str(resolved_path),
        fallback_dirs=fallback_dirs,
        prompt_registry=prompt_registry,
        context_namespace=context_namespace,
    )

    front_matter, body_with_blocks = _parse_front_matter(expanded_text)
    blocks = _parse_fenced_blocks(body_with_blocks)
    body = _strip_fenced_blocks(body_with_blocks).strip()
    return MarkdownAssetDocument(
        source_path=resolved_path,
        front_matter=front_matter,
        body=body,
        blocks=blocks,
        sources=sources,
    )


def parse_markdown_asset_text_document(
    markdown_text: str,
    *,
    source_path: Path,
    sources: Sequence[str] = (),
    expand_includes: bool = False,
    fallback_dirs: Sequence[Path] = (),
    prompt_registry: Any | None = None,
    context_namespace: str | None = None,
) -> MarkdownAssetDocument:
    resolved_path = Path(source_path).resolve()
    expanded_text = markdown_text
    resolved_sources = list(sources)
    if expand_includes:
        expanded_text, expanded_sources = expand_prompt_markdown_text(
            markdown_text,
            base_dir=resolved_path.parent,
            source_path=resolved_path,
            fallback_dirs=fallback_dirs,
            prompt_registry=prompt_registry,
            context_namespace=context_namespace,
        )
        resolved_sources = list(dict.fromkeys([*resolved_sources, *expanded_sources]))
    front_matter, body_with_blocks = _parse_front_matter(expanded_text)
    blocks = _parse_fenced_blocks(body_with_blocks)
    body = _strip_fenced_blocks(body_with_blocks).strip()
    return MarkdownAssetDocument(
        source_path=resolved_path,
        front_matter=front_matter,
        body=body,
        blocks=blocks,
        sources=resolved_sources,
    )


def compile_markdown_flow_definition(
    document: MarkdownAssetDocument,
    *,
    default_name: str,
) -> Dict[str, Any]:
    definition = _mapping_copy(document.front_matter)
    definition.setdefault("name", default_name)
    _merge_yaml_blocks(definition, document, labels=("spec", "flow", "definition", "config"))
    _merge_prompt_sections(definition, _collect_prompt_sections(document, include_body=True))
    vm_sections = [
        block.content.strip()
        for block in document.find_blocks(languages=("vm", "stackvm"))
        if block.content.strip()
    ]
    if vm_sections:
        definition["vm_source"] = "\n\n".join(vm_sections).strip()
        definition.setdefault("execution_mode", "vm")
    return definition


def compile_markdown_agent_definition(
    document: MarkdownAssetDocument,
    *,
    default_name: str,
) -> Dict[str, Any]:
    definition = _mapping_copy(document.front_matter)
    definition.setdefault("name", default_name)
    _merge_yaml_blocks(definition, document, labels=("spec", "agent", "profile", "config"))
    if "base_agent" not in definition and "extends" in definition:
        definition["base_agent"] = definition.get("extends")
    inline_prompt_sections = _collect_prompt_sections(document, include_body=True)
    if inline_prompt_sections:
        definition["inline_prompt"] = "\n\n".join(section for section in inline_prompt_sections if section).strip()
    return definition


def compile_markdown_hook_definition(
    document: MarkdownAssetDocument,
    *,
    default_name: str,
) -> Dict[str, Any]:
    definition = _mapping_copy(document.front_matter)
    definition.setdefault("name", default_name)
    _merge_yaml_blocks(definition, document, labels=("spec", "hook", "config"))

    normalized_phases: Dict[str, str] = {}
    raw_phases = definition.get("phases")
    if isinstance(raw_phases, dict):
        for phase_name, phase_source in raw_phases.items():
            if isinstance(phase_name, str) and isinstance(phase_source, str) and phase_source.strip():
                normalized_phases[phase_name.strip()] = phase_source.strip()

    for block in document.find_blocks(languages=("vm", "stackvm")):
        phase_name = block.label.strip()
        if phase_name and block.content.strip():
            normalized_phases[phase_name] = block.content.strip()

    definition["phases"] = normalized_phases

    description_sections = _collect_prompt_sections(document, include_body=True)
    if description_sections and not str(definition.get("description") or "").strip():
        definition["description"] = "\n\n".join(section for section in description_sections if section).strip()

    return definition


def compile_markdown_tool_definition(
    document: MarkdownAssetDocument,
    *,
    default_name: str,
) -> MarkdownToolDefinition:
    definition = _mapping_copy(document.front_matter)
    definition.setdefault("name", default_name)
    _merge_yaml_blocks(definition, document, labels=("spec", "tool", "config"))

    schema = _mapping_copy(_load_first_yaml_block(document, labels=("schema",)))
    if not schema and isinstance(definition.get("schema"), dict):
        schema = _mapping_copy(definition.get("schema"))

    description_sections = _collect_prompt_sections(document, include_body=True)
    description = str(definition.get("description") or "").strip()
    if not description and description_sections:
        description = "\n\n".join(section for section in description_sections if section).strip()

    handler = str(definition.get("handler") or definition.get("callable") or "").strip()
    if not handler:
        raise ValueError(f"Markdown tool '{document.source_path}' is missing required field 'handler'.")

    timeout_value = definition.get("timeout_seconds")
    timeout_seconds = float(timeout_value) if timeout_value is not None else None

    metadata = _mapping_copy(definition)
    metadata.pop("handler", None)
    metadata.pop("callable", None)
    metadata.pop("schema", None)

    return MarkdownToolDefinition(
        name=str(definition.get("name") or default_name).strip() or default_name,
        description=description,
        handler=handler,
        schema=schema,
        execution_mode=(
            str(definition.get("execution_mode")).strip()
            if definition.get("execution_mode")
            else None
        ),
        timeout_seconds=timeout_seconds,
        metadata=metadata,
        source_path=document.source_path,
    )


class MarkdownWrappedTool(BaseTool):
    def __init__(
        self,
        *,
        name: str,
        description: str,
        schema: Dict[str, Any] | None,
        delegate: Any,
        source_path: Path | None,
        execution_mode: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._name = name
        self._description = description.strip() or f"Tool '{name}'."
        self._schema = dict(schema or {"type": "object", "properties": {}})
        self._delegate = delegate
        self._tool_source_path = source_path.resolve() if isinstance(source_path, Path) else None
        self._execution_mode_override = execution_mode
        self._timeout_seconds_override = timeout_seconds
        self._delegate_instance: BaseTool | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        delegate_instance = self._get_delegate_instance()
        if self._description:
            return self._description
        if delegate_instance is not None:
            return delegate_instance.description
        return f"Tool '{self._name}'."

    @property
    def schema(self) -> Dict[str, Any]:
        delegate_instance = self._get_delegate_instance()
        if self._schema.get("properties") or self._schema.get("required") or len(self._schema) > 2:
            return self._schema
        if delegate_instance is not None:
            return delegate_instance.schema
        return self._schema

    @property
    def execution_mode(self) -> str:
        if self._execution_mode_override:
            return self._execution_mode_override
        delegate_instance = self._get_delegate_instance()
        if delegate_instance is not None:
            return delegate_instance.execution_mode
        return "inline"

    @property
    def timeout_seconds(self) -> float | None:
        if self._timeout_seconds_override is not None:
            return self._timeout_seconds_override
        delegate_instance = self._get_delegate_instance()
        if delegate_instance is not None:
            return delegate_instance.timeout_seconds
        return None

    def execute(self, **kwargs) -> Any:
        delegate_instance = self._get_delegate_instance()
        if delegate_instance is not None:
            return delegate_instance.execute(**kwargs)
        if callable(self._delegate):
            return self._delegate(**kwargs)
        raise TypeError(f"Markdown tool '{self._name}' resolved to unsupported delegate type '{type(self._delegate)}'.")

    def spawn_subprocess(self, **kwargs) -> Any:
        delegate_instance = self._get_delegate_instance()
        if delegate_instance is None:
            return super().spawn_subprocess(**kwargs)
        return delegate_instance.spawn_subprocess(**kwargs)

    def handle_subprocess_result(self, *, returncode: int, stdout: str, stderr: str, **kwargs) -> Any:
        delegate_instance = self._get_delegate_instance()
        if delegate_instance is None:
            return super().handle_subprocess_result(
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                **kwargs,
            )
        return delegate_instance.handle_subprocess_result(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            **kwargs,
        )

    def _get_delegate_instance(self) -> BaseTool | None:
        if self._delegate_instance is not None:
            return self._delegate_instance
        if isinstance(self._delegate, BaseTool):
            self._delegate_instance = self._delegate
            return self._delegate_instance
        if isinstance(self._delegate, type) and issubclass(self._delegate, BaseTool):
            self._delegate_instance = self._delegate()
            return self._delegate_instance
        return None


def build_markdown_tool_wrapper(
    *,
    tool_definition: MarkdownToolDefinition,
    delegate: Any,
    registered_name: str,
) -> MarkdownWrappedTool:
    return MarkdownWrappedTool(
        name=registered_name,
        description=tool_definition.description,
        schema=tool_definition.schema,
        delegate=delegate,
        source_path=tool_definition.source_path,
        execution_mode=tool_definition.execution_mode,
        timeout_seconds=tool_definition.timeout_seconds,
    )


def serialize_markdown_agent_definition(agent: Any) -> str:
    front_matter: Dict[str, Any] = {
        "name": str(agent.name),
        "flow": str(agent.flow),
    }
    if getattr(agent, "base_agent", None):
        front_matter["extends"] = str(agent.base_agent)
    if getattr(agent, "description", ""):
        front_matter["description"] = str(agent.description)
    if getattr(agent, "llm_profile", None):
        front_matter["llm_profile"] = str(agent.llm_profile)
    if getattr(agent, "hooks", None) is not None:
        front_matter["hooks"] = list(agent.hooks)
    if getattr(agent, "skills", None) is not None:
        front_matter["skills"] = list(agent.skills)
    if getattr(agent, "tools", None) is not None:
        front_matter["tools"] = list(agent.tools)
    if getattr(agent, "commands", None):
        front_matter["commands"] = [
            {
                "name": str(command.name),
                "target": (
                    str(command.target)
                    if str(getattr(command, "target_kind", "command") or "command").strip().lower() == "command"
                    else {
                        "kind": str(getattr(command, "target_kind", "command") or "command"),
                        **(
                            {"agent": str(getattr(command, "target_agent", "") or "")}
                            if str(getattr(command, "target_agent", "") or "").strip()
                            else {}
                        ),
                        **(
                            {"handler": str(getattr(command, "target_handler", "") or "")}
                            if str(getattr(command, "target_handler", "") or "").strip()
                            else {}
                        ),
                        "command": str(getattr(command, "target", "") or ""),
                        **(
                            {"visibility": str(getattr(command, "target_visibility", "") or "")}
                            if str(getattr(command, "target_visibility", "") or "").strip()
                            else {}
                        ),
                    }
                ),
                **({"visibility": str(command.visibility)} if str(getattr(command, "visibility", "") or "").strip() else {}),
                **({"description": str(command.description)} if str(getattr(command, "description", "") or "").strip() else {}),
                **({"capabilities": list(command.capabilities)} if getattr(command, "capabilities", None) else {}),
                **({"payload_schema": dict(command.payload_schema)} if getattr(command, "payload_schema", None) else {}),
                **({"result_schema": dict(command.result_schema)} if getattr(command, "result_schema", None) else {}),
                **({"policy": dict(command.policy)} if getattr(command, "policy", None) else {}),
            }
            for command in list(agent.commands)
            if str(getattr(command, "name", "") or "").strip() and str(getattr(command, "target", "") or "").strip()
        ]
    if getattr(agent, "extra_prompts", None):
        front_matter["extra_prompts"] = list(agent.extra_prompts)
    if getattr(agent, "tool_confirmation", None):
        front_matter["tool_confirmation"] = dict(agent.tool_confirmation)

    front_matter_text = yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=False).strip()
    body = str(getattr(agent, "inline_prompt", "") or "").strip()
    if body:
        return f"---\n{front_matter_text}\n---\n{body}\n"
    return f"---\n{front_matter_text}\n---\n"


def _parse_front_matter(markdown_text: str) -> tuple[Dict[str, Any], str]:
    if not markdown_text.startswith("---"):
        return {}, markdown_text

    lines = markdown_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, markdown_text

    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            front_matter_text = "\n".join(lines[1:index])
            front_matter = yaml.safe_load(front_matter_text) or {}
            if not isinstance(front_matter, dict):
                raise ValueError("Markdown front matter must be a YAML mapping.")
            body = "\n".join(lines[index + 1 :])
            return front_matter, body
    return {}, markdown_text


def _parse_fenced_blocks(markdown_text: str) -> list[MarkdownAssetBlock]:
    blocks: list[MarkdownAssetBlock] = []
    lines = markdown_text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.startswith("```"):
            index += 1
            continue
        info = line[3:].strip()
        language, label = _parse_fence_info(info)
        index += 1
        content_lines: list[str] = []
        while index < len(lines) and not lines[index].startswith("```"):
            content_lines.append(lines[index])
            index += 1
        if index < len(lines) and lines[index].startswith("```"):
            index += 1
        blocks.append(
            MarkdownAssetBlock(
                language=language,
                label=label,
                content="\n".join(content_lines).strip(),
            )
        )
    return blocks


def _strip_fenced_blocks(markdown_text: str) -> str:
    output_lines: list[str] = []
    lines = markdown_text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                index += 1
            if index < len(lines):
                index += 1
            continue
        output_lines.append(line)
        index += 1
    return "\n".join(output_lines)


def _parse_fence_info(info: str) -> tuple[str, str]:
    if not info:
        return "", ""
    tokens = [token.strip() for token in info.split() if token.strip()]
    if not tokens:
        return "", ""
    language = tokens[0].lower()
    label = " ".join(tokens[1:]).strip().lower()
    return language, label


def _load_yaml_block_mapping(document: MarkdownAssetDocument, block: MarkdownAssetBlock) -> Dict[str, Any]:
    if block.language.strip().lower() not in {"yaml", "yml"}:
        return {}
    loaded = yaml.safe_load(block.content) or {}
    if not isinstance(loaded, dict):
        raise ValueError(
            f"Markdown asset YAML block in '{document.source_path}' must be a mapping."
        )
    return loaded


def _load_first_yaml_block(
    document: MarkdownAssetDocument,
    *,
    labels: Iterable[str],
) -> Dict[str, Any]:
    for block in document.find_blocks(languages={"yaml", "yml"}, labels=set(labels)):
        loaded = _load_yaml_block_mapping(document, block)
        if loaded:
            return loaded
    return {}


def _merge_yaml_blocks(
    target: Dict[str, Any],
    document: MarkdownAssetDocument,
    *,
    labels: Iterable[str],
) -> None:
    allowed_labels = {label.strip().lower() for label in labels if str(label).strip()}
    for block in document.find_blocks(languages={"yaml", "yml"}):
        if block.label and block.label not in allowed_labels:
            continue
        _deep_merge(target, _load_yaml_block_mapping(document, block))


def _collect_prompt_sections(
    document: MarkdownAssetDocument,
    *,
    include_body: bool,
) -> list[str]:
    sections: list[str] = []
    if include_body and document.body.strip():
        sections.append(document.body.strip())

    for block in document.blocks:
        language = block.language.strip().lower()
        label = block.label.strip().lower()
        if language not in {"markdown", "md", "text"}:
            continue
        if label and label not in {"prompt", "system", "description", "body"}:
            continue
        if block.content.strip():
            sections.append(block.content.strip())
    return sections


def _merge_prompt_sections(target: Dict[str, Any], sections: Sequence[str]) -> None:
    cleaned_sections = [section.strip() for section in sections if str(section).strip()]
    if not cleaned_sections:
        return

    for key in ("system_prompt", "prompt"):
        existing = target.get(key)
        if isinstance(existing, str) and existing.strip():
            target[key] = "\n\n".join([existing.strip(), *cleaned_sections]).strip()
            return

    target["prompt"] = "\n\n".join(cleaned_sections).strip()


def _mapping_copy(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _deep_merge(target: Dict[str, Any], incoming: Dict[str, Any]) -> None:
    for key, value in incoming.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _deep_merge(target[key], value)
            continue
        target[key] = value
