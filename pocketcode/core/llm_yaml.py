from __future__ import annotations

import re
from typing import Any, Dict

import yaml

_YAML_BLOCK_RE = re.compile(r"```(?:yaml)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_YAML_KEY_LINE_RE = re.compile(r"^\s*[\"']?[A-Za-z0-9_.-]+[\"']?\s*:")


def parse_llm_yaml_mapping(text: str) -> Dict[str, Any]:
    """Parse an LLM response into a YAML mapping.

    The parser accepts fenced YAML blocks and also tolerates leading prose such
    as "Here is the YAML:" before the first mapping key.
    """

    raw_text = str(text or "")
    candidate = _extract_yaml_candidate(raw_text)
    parse_candidates = [candidate]

    trimmed = _trim_to_first_yaml_key(candidate)
    if trimmed != candidate:
        parse_candidates.append(trimmed)

    last_error: yaml.YAMLError | None = None
    for item in parse_candidates:
        if not item.strip():
            continue
        try:
            parsed = yaml.safe_load(item)
        except yaml.YAMLError as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return parsed

    if last_error is not None:
        raise last_error
    raise ValueError("Expected YAML mapping from LLM response.")


def _extract_yaml_candidate(text: str) -> str:
    match = _YAML_BLOCK_RE.search(text)
    return (match.group(1) if match else text).strip()


def _trim_to_first_yaml_key(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if _YAML_KEY_LINE_RE.match(line):
            return "\n".join(lines[index:]).strip()
    return text.strip()