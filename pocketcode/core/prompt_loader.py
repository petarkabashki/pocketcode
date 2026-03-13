from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, List, Sequence, Tuple

from pocketcode.core.reference_syntax import (
    normalize_prompt_reference as normalize_prompt_reference_value,
    parse_prompt_reference,
)

_INCLUDE_RE = re.compile(r"\{\{\s*(?:include|import)\s*:\s*([^}]+?)\s*\}\}")
_PROMPT_REF_PREFIX = "prompt:"


def is_prompt_reference(value: str) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith(_PROMPT_REF_PREFIX)


def normalize_prompt_reference(prompt_ref: str) -> str:
    return normalize_prompt_reference_value(prompt_ref)


def resolve_prompt_reference(
    prompt_ref: str,
    *,
    prompt_registry: Any,
    context_namespace: str | None = None,
) -> Tuple[str, List[str]]:
    if prompt_registry is None:
        raise ValueError(f"Prompt registry is required to resolve prompt reference '{prompt_ref}'.")

    reference = parse_prompt_reference(prompt_ref)
    qualified_ref = prompt_registry.qualify(reference.target, context_namespace=context_namespace)
    prompt_text = prompt_registry.resolve(qualified_ref, context_namespace=context_namespace)
    return str(prompt_text).strip(), [f"prompt:{qualified_ref}"]


def _resolve_prompt_path(
    *,
    base_dir: Path,
    prompt_file: str,
    fallback_dirs: Sequence[Path] = (),
) -> Path:
    prompt_path = Path(prompt_file)
    if prompt_path.is_absolute():
        return prompt_path.resolve()

    candidates = [(base_dir / prompt_file).resolve()]
    for fallback_dir in fallback_dirs:
        candidates.append((fallback_dir / prompt_file).resolve())
        candidates.append((fallback_dir.parent / prompt_file).resolve())

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    return candidates[0]


def coerce_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, (list, tuple)):
        result: List[str] = []
        for item in value:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    result.append(cleaned)
        return result
    return []


def load_prompt_markdown(
    base_dir: Path,
    prompt_file: str,
    _stack: set[str] | None = None,
    fallback_dirs: Sequence[Path] = (),
    prompt_registry: Any | None = None,
    context_namespace: str | None = None,
) -> Tuple[str, List[str]]:
    stack = _stack if _stack is not None else set()

    if is_prompt_reference(prompt_file):
        resolved_text, resolved_sources = resolve_prompt_reference(
            prompt_file,
            prompt_registry=prompt_registry,
            context_namespace=context_namespace,
        )
        normalized_ref = normalize_prompt_reference(prompt_file)
        stack_key = f"prompt:{normalized_ref}"
        if stack_key in stack:
            cycle = " -> ".join([*stack, stack_key])
            raise ValueError(f"Prompt include cycle detected: {cycle}")
        stack.add(stack_key)
        stack.remove(stack_key)
        return resolved_text, resolved_sources

    prompt_path = _resolve_prompt_path(
        base_dir=base_dir,
        prompt_file=prompt_file,
        fallback_dirs=fallback_dirs,
    )

    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    stack_key = f"file:{prompt_path}"
    if stack_key in stack:
        cycle = " -> ".join([*stack, stack_key])
        raise ValueError(f"Prompt include cycle detected: {cycle}")

    stack.add(stack_key)
    text = prompt_path.read_text(encoding="utf-8")
    expanded, sources = expand_prompt_markdown_text(
        text,
        base_dir=prompt_path.parent,
        source_path=prompt_path,
        _stack=stack,
        fallback_dirs=fallback_dirs,
        prompt_registry=prompt_registry,
        context_namespace=context_namespace,
    )
    stack.remove(stack_key)

    deduped_sources = list(dict.fromkeys(sources))
    return expanded.strip(), deduped_sources


def expand_prompt_markdown_text(
    markdown_text: str,
    *,
    base_dir: Path,
    source_path: Path | None = None,
    _stack: set[str] | None = None,
    fallback_dirs: Sequence[Path] = (),
    prompt_registry: Any | None = None,
    context_namespace: str | None = None,
) -> Tuple[str, List[str]]:
    stack = _stack if _stack is not None else set()
    resolved_source_path = source_path.resolve() if isinstance(source_path, Path) else None
    sources: List[str] = [str(resolved_source_path)] if resolved_source_path is not None else []

    def _replace_include(match: re.Match[str]) -> str:
        include_target = match.group(1).strip()
        included_text, included_sources = load_prompt_markdown(
            base_dir=base_dir,
            prompt_file=include_target,
            _stack=stack,
            fallback_dirs=fallback_dirs,
            prompt_registry=prompt_registry,
            context_namespace=context_namespace,
        )
        sources.extend(included_sources)
        return included_text

    expanded = _INCLUDE_RE.sub(_replace_include, markdown_text)
    return expanded, list(dict.fromkeys(sources))


def resolve_prompt_bundle(
    config: dict[str, Any],
    *,
    base_dir: Path,
    inline_keys: Sequence[str] = ("prompt",),
    file_keys: Sequence[str] = ("prompt_file",),
    files_key: str = "prompt_files",
    default_files: Iterable[str] | None = None,
    fallback_dirs: Sequence[Path] = (),
    prompt_registry: Any | None = None,
    context_namespace: str | None = None,
) -> Tuple[str, List[str]]:
    sections: List[str] = []
    sources: List[str] = []

    for key in inline_keys:
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            sections.append(value.strip())

    explicit_files: List[str] = []
    for key in file_keys:
        explicit_files.extend(coerce_str_list(config.get(key)))
    explicit_files.extend(coerce_str_list(config.get(files_key)))

    if not explicit_files and default_files:
        for candidate in default_files:
            candidate_path = _resolve_prompt_path(
                base_dir=base_dir,
                prompt_file=candidate,
                fallback_dirs=fallback_dirs,
            )
            if candidate_path.is_file():
                explicit_files.append(candidate)

    for prompt_file in explicit_files:
        loaded_text, loaded_sources = load_prompt_markdown(
            base_dir=base_dir,
            prompt_file=prompt_file,
            fallback_dirs=fallback_dirs,
            prompt_registry=prompt_registry,
            context_namespace=context_namespace,
        )
        if loaded_text:
            sections.append(loaded_text)
        sources.extend(loaded_sources)

    prompt_text = "\n\n".join(section for section in sections if section).strip()
    return prompt_text, list(dict.fromkeys(sources))
