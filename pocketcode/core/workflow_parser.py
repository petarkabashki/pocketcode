from __future__ import annotations

"""Legacy markdown graph workflow parser.

This module predates the manifest-plus-FlowDefinition loading path and is no
longer the canonical authoring surface. New markdown-authored assets compile
through `pocketcode.core.markdown_assets` into the current flow, tool, prompt,
and agent loaders instead of going through this graph parser.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml

from pocketcode.core.prompt_loader import coerce_str_list, resolve_prompt_bundle
from pocketcode.core.runtime_models import (
    WorkflowDefinition,
    WorkflowEdgeDefinition,
    WorkflowNodeDefinition,
)

logger = logging.getLogger(__name__)

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_DOT_BLOCK_RE = re.compile(r"```dot\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_ATTR_RE = re.compile(
    r"([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|[^,\]]+)"
)


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _clean_identifier(value: str) -> str:
    return _strip_quotes(value.strip())


def _parse_attributes(raw_attributes: str) -> Dict[str, Any]:
    attributes: Dict[str, Any] = {}
    for key, value in _ATTR_RE.findall(raw_attributes):
        attributes[key.strip()] = _strip_quotes(value)
    return attributes


def _parse_front_matter(markdown_text: str) -> Tuple[Dict[str, object], str]:
    match = _FRONT_MATTER_RE.match(markdown_text)
    if not match:
        return {}, markdown_text

    front_matter_text = match.group(1)
    front_matter = yaml.safe_load(front_matter_text) or {}
    if not isinstance(front_matter, dict):
        raise ValueError("Workflow front matter must be a YAML mapping.")

    body = markdown_text[match.end() :]
    return front_matter, body


def _parse_dot(dot_text: str) -> Tuple[Dict[str, WorkflowNodeDefinition], list[WorkflowEdgeDefinition]]:
    nodes: Dict[str, WorkflowNodeDefinition] = {}
    edges: list[WorkflowEdgeDefinition] = []

    for raw_line in dot_text.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line:
            continue

        if line.startswith("digraph") or line in {"{", "}"}:
            continue

        if line.endswith(";"):
            line = line[:-1].strip()

        if "->" in line:
            source_part, right_part = line.split("->", 1)
            source = _clean_identifier(source_part)

            edge_attrs: Dict[str, Any] = {}
            if "[" in right_part and "]" in right_part:
                target_part, attr_part = right_part.split("[", 1)
                target = _clean_identifier(target_part)
                attr_body = attr_part.rsplit("]", 1)[0]
                edge_attrs = _parse_attributes(attr_body)
            else:
                target = _clean_identifier(right_part)

            transition = (
                edge_attrs.get("label")
                or edge_attrs.get("transition")
                or edge_attrs.get("condition")
                or "default"
            )

            if source not in nodes:
                nodes[source] = WorkflowNodeDefinition(node_id=source, attributes={})
            if target not in nodes:
                nodes[target] = WorkflowNodeDefinition(node_id=target, attributes={})

            edges.append(
                WorkflowEdgeDefinition(
                    source=source,
                    target=target,
                    transition=transition,
                    attributes=edge_attrs,
                )
            )
            continue

        node_attrs: Dict[str, Any] = {}
        if "[" in line and "]" in line:
            node_id_part, attr_part = line.split("[", 1)
            node_id = _clean_identifier(node_id_part)
            node_attrs = _parse_attributes(attr_part.rsplit("]", 1)[0])
        else:
            node_id = _clean_identifier(line)

        if not node_id:
            continue

        existing = nodes.get(node_id)
        if existing:
            existing.attributes.update(node_attrs)
        else:
            nodes[node_id] = WorkflowNodeDefinition(node_id=node_id, attributes=node_attrs)

    return nodes, edges


def _collect_handlers(mapping: Dict[str, Any], keys: list[str]) -> list[str]:
    handlers: list[str] = []
    for key in keys:
        handlers.extend(coerce_str_list(mapping.get(key)))
    return list(dict.fromkeys(handlers))


def _apply_node_overrides_and_prompts(
    *,
    nodes: Dict[str, WorkflowNodeDefinition],
    node_overrides: Dict[str, Any],
    plugin_node_definitions: Dict[str, Dict[str, Any]],
    plugin_root: Path,
) -> Dict[str, WorkflowNodeDefinition]:
    if node_overrides:
        for node_id, raw_override in node_overrides.items():
            if not isinstance(node_id, str):
                continue
            if node_id not in nodes:
                nodes[node_id] = WorkflowNodeDefinition(node_id=node_id, attributes={})
            if not isinstance(raw_override, dict):
                logger.warning("Node override for '%s' is not a mapping. Ignoring.", node_id)

    for node_id, node_definition in nodes.items():
        merged: Dict[str, Any] = {}
        override_raw = node_overrides.get(node_id, {}) if isinstance(node_overrides, dict) else {}
        override = override_raw if isinstance(override_raw, dict) else {}

        template_name = (
            override.get("use")
            or override.get("node")
            or override.get("definition")
            or node_definition.attributes.get("use")
            or node_definition.attributes.get("node")
            or node_definition.attributes.get("definition")
        )

        if template_name:
            template = plugin_node_definitions.get(str(template_name))
            if isinstance(template, dict):
                merged.update(template)
            else:
                logger.warning("Unknown node definition '%s' referenced by node '%s'.", template_name, node_id)

        merged.update(node_definition.attributes)
        merged.update(override)

        node_prompt, node_prompt_sources = resolve_prompt_bundle(
            merged,
            base_dir=plugin_root,
            inline_keys=("prompt", "system_prompt"),
            file_keys=("prompt_file", "system_prompt_file"),
            files_key="prompt_files",
            default_files=[f"prompts/nodes/{node_id}.md"],
        )
        if node_prompt:
            merged["prompt"] = node_prompt
        if node_prompt_sources:
            merged["prompt_sources"] = node_prompt_sources

        pre_handlers = _collect_handlers(merged, ["pre", "pre_steps"])
        step_handlers = _collect_handlers(merged, ["steps", "exec", "exec_steps"])
        post_handlers = _collect_handlers(merged, ["post", "post_steps"])

        if pre_handlers:
            merged["pre"] = pre_handlers
        if step_handlers:
            merged["steps"] = step_handlers
        if post_handlers:
            merged["post"] = post_handlers

        nodes[node_id] = WorkflowNodeDefinition(node_id=node_id, attributes=merged)

    return nodes


def parse_markdown_workflow(
    workflow_path: Path,
    workflow_name: str,
    plugin_name: str,
    plugin_root: Path,
    plugin_node_definitions: Dict[str, Dict[str, Any]] | None = None,
) -> WorkflowDefinition:
    if not workflow_path.exists():
        raise FileNotFoundError(f"Workflow file not found: {workflow_path}")

    node_definitions = plugin_node_definitions or {}

    markdown_text = workflow_path.read_text(encoding="utf-8")
    front_matter, markdown_body = _parse_front_matter(markdown_text)
    if not isinstance(front_matter, dict):
        raise ValueError("Workflow front matter must be a mapping.")

    dot_match = _DOT_BLOCK_RE.search(markdown_body)
    if not dot_match:
        raise ValueError(
            f"Workflow '{workflow_name}' in {workflow_path} must include a ```dot``` fenced graph."
        )

    dot_text = dot_match.group(1)
    nodes, edges = _parse_dot(dot_text)
    if not nodes:
        raise ValueError(f"Workflow '{workflow_name}' does not define any nodes.")

    node_overrides = front_matter.get("nodes", {})
    if node_overrides and not isinstance(node_overrides, dict):
        logger.warning(
            "Workflow '%s' has front matter 'nodes' value that is not a mapping. Ignoring node overrides.",
            workflow_name,
        )
        node_overrides = {}

    nodes = _apply_node_overrides_and_prompts(
        nodes=nodes,
        node_overrides=node_overrides if isinstance(node_overrides, dict) else {},
        plugin_node_definitions=node_definitions,
        plugin_root=plugin_root,
    )

    configured_start = front_matter.get("start")
    if configured_start:
        start_node = str(configured_start)
    else:
        start_candidates = [
            node.node_id
            for node in nodes.values()
            if node.attributes.get("kind", "").lower() == "start"
        ]
        start_node = start_candidates[0] if start_candidates else next(iter(nodes.keys()))

    if start_node not in nodes:
        raise ValueError(
            f"Workflow '{workflow_name}' start node '{start_node}' is not declared in graph."
        )

    description = str(front_matter.get("description", "")).strip()
    default_agent = None
    if front_matter.get("default_agent"):
        default_agent = str(front_matter["default_agent"]).strip()

    flow_prompt, flow_prompt_sources = resolve_prompt_bundle(
        front_matter,
        base_dir=plugin_root,
        inline_keys=("prompt",),
        file_keys=("prompt_file",),
        files_key="prompt_files",
        default_files=[f"prompts/flows/{workflow_name}.md"],
    )

    flow_pre_handlers = _collect_handlers(front_matter, ["pre", "pre_steps"])
    flow_step_handlers = _collect_handlers(front_matter, ["steps", "exec", "exec_steps"])
    flow_post_handlers = _collect_handlers(front_matter, ["post", "post_steps"])

    return WorkflowDefinition(
        name=workflow_name,
        description=description,
        plugin_name=plugin_name,
        plugin_root=plugin_root,
        markdown_path=workflow_path,
        start_node=start_node,
        default_agent=default_agent,
        workflow_kind="graph",
        nodes=nodes,
        edges=edges,
        prompt=flow_prompt,
        prompt_sources=flow_prompt_sources,
        pre_handlers=flow_pre_handlers,
        step_handlers=flow_step_handlers,
        post_handlers=flow_post_handlers,
        metadata=dict(front_matter),
    )
