from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, List, Sequence, Tuple

_INCLUDE_RE = re.compile(r"\{\{\s*include\s*:\s*([^}]+?)\s*\}\}")


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
    _stack: set[Path] | None = None,
    fallback_dirs: Sequence[Path] = (),
) -> Tuple[str, List[str]]:
    stack = _stack if _stack is not None else set()

    prompt_path = _resolve_prompt_path(
        base_dir=base_dir,
        prompt_file=prompt_file,
        fallback_dirs=fallback_dirs,
    )

    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    if prompt_path in stack:
        cycle = " -> ".join([*map(str, stack), str(prompt_path)])
        raise ValueError(f"Prompt include cycle detected: {cycle}")

    stack.add(prompt_path)
    text = prompt_path.read_text(encoding="utf-8")
    sources: List[str] = [str(prompt_path)]

    def _replace_include(match: re.Match[str]) -> str:
        include_target = match.group(1).strip()
        included_text, included_sources = load_prompt_markdown(
            base_dir=prompt_path.parent,
            prompt_file=include_target,
            _stack=stack,
            fallback_dirs=fallback_dirs,
        )
        sources.extend(included_sources)
        return included_text

    expanded = _INCLUDE_RE.sub(_replace_include, text)
    stack.remove(prompt_path)

    deduped_sources = list(dict.fromkeys(sources))
    return expanded.strip(), deduped_sources


def resolve_prompt_bundle(
    config: dict[str, Any],
    *,
    base_dir: Path,
    inline_keys: Sequence[str] = ("prompt",),
    file_keys: Sequence[str] = ("prompt_file",),
    files_key: str = "prompt_files",
    default_files: Iterable[str] | None = None,
    fallback_dirs: Sequence[Path] = (),
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
        )
        if loaded_text:
            sections.append(loaded_text)
        sources.extend(loaded_sources)

    prompt_text = "\n\n".join(section for section in sections if section).strip()
    return prompt_text, list(dict.fromkeys(sources))
