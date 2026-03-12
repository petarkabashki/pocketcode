from __future__ import annotations

import difflib
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable

from pocketcode.core.interfaces import BaseTool
from pocketcode.core_tools.filesystem import _resolve_scoped_path, read_file, write_file
from pocketcode.core_tools.user_input import (
    ask_user_checklist,
    ask_user_radio_group,
)

logger = logging.getLogger(__name__)

_PENDING_FILE_EDITS_KEY = "pending_file_edits"

__all__ = [
    "SelectFilesystemEntryTool",
    "ExtractTextTool",
    "StageTextReplaceTool",
    "ApplyStagedEditTool",
    "CancelStagedEditTool",
    "select_filesystem_entry",
    "extract_text",
    "stage_text_replace",
    "apply_staged_edit",
    "cancel_staged_edit",
]


def _coerce_path(path: str) -> Path:
    return Path(path).expanduser()


def _iter_candidates(
    *,
    base_path: Path,
    recursive: bool,
    selection_mode: str,
    include_hidden: bool,
    glob_pattern: str | None,
) -> Iterable[Path]:
    iterator = base_path.rglob("*") if recursive else base_path.iterdir()
    for entry in sorted(iterator):
        name = entry.name
        if not include_hidden and name.startswith("."):
            continue
        if selection_mode == "file" and not entry.is_file():
            continue
        if selection_mode == "directory" and not entry.is_dir():
            continue
        if glob_pattern and not entry.match(glob_pattern):
            continue
        yield entry


def _normalize_selection_mode(selection_mode: str) -> str:
    normalized = str(selection_mode or "any").strip().lower()
    if normalized not in {"any", "file", "directory"}:
        raise ValueError("selection_mode must be one of: any, file, directory")
    return normalized


def _resolve_content(
    path: str | None,
    text: str | None,
    *,
    shared_store: Dict[str, Any] | None = None,
    root_path: str | Path | None = None,
) -> tuple[str, str | None]:
    if path:
        resolved_path = _resolve_scoped_path(path, shared_store=shared_store, root_path=root_path)
        content = read_file(path, shared_store=shared_store, root_path=root_path)
        if content is None:
            raise ValueError(f"Failed to read file '{path}'.")
        return content, str(resolved_path)
    if text is None:
        raise ValueError("Either 'path' or 'text' is required.")
    return text, None


def _find_pattern_line(
    lines: list[str],
    *,
    pattern: str,
    regex: bool,
    occurrence: int,
    start_index: int = 0,
) -> int:
    if occurrence < 1:
        raise ValueError("occurrence must be >= 1")

    count = 0
    for index in range(start_index, len(lines)):
        line = lines[index]
        matched = bool(re.search(pattern, line)) if regex else pattern in line
        if matched:
            count += 1
            if count == occurrence:
                return index
    raise ValueError(f"Pattern not found: '{pattern}'")


def _line_bounds_from_spec(
    content: str,
    *,
    start_line: int | None = None,
    end_line: int | None = None,
    start_pattern: str | None = None,
    end_pattern: str | None = None,
    include_boundaries: bool = True,
    occurrence: int = 1,
    regex: bool = False,
) -> tuple[int, int]:
    lines = content.splitlines(keepends=True)
    if not lines:
        raise ValueError("Cannot resolve a line range from empty text.")

    start_index = 0 if start_line is None else start_line - 1
    if start_line is not None and start_line < 1:
        raise ValueError("start_line must be >= 1")
    if end_line is not None and end_line < 1:
        raise ValueError("end_line must be >= 1")

    if start_pattern:
        start_index = _find_pattern_line(
            lines,
            pattern=start_pattern,
            regex=regex,
            occurrence=occurrence,
        )
        if not include_boundaries:
            start_index += 1

    if start_index > len(lines):
        raise ValueError("start_line is outside the text range.")

    end_index = len(lines) - 1 if end_line is None else end_line - 1
    if end_pattern:
        search_start = max(start_index, 0)
        end_index = _find_pattern_line(
            lines,
            pattern=end_pattern,
            regex=regex,
            occurrence=occurrence,
            start_index=search_start,
        )
        if not include_boundaries:
            end_index -= 1

    if end_index < start_index:
        raise ValueError("Resolved range is empty or inverted.")
    if end_index >= len(lines):
        raise ValueError("end_line is outside the text range.")
    return start_index, end_index


def _line_range_to_offsets(content: str, start_index: int, end_index: int) -> tuple[int, int]:
    lines = content.splitlines(keepends=True)
    start_offset = sum(len(line) for line in lines[:start_index])
    end_offset = sum(len(line) for line in lines[: end_index + 1])
    return start_offset, end_offset


def _build_unified_diff(before: str, after: str, *, path: str | None = None) -> str:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    from_label = f"{path or 'before'}"
    to_label = f"{path or 'after'}"
    return "\n".join(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=from_label,
            tofile=to_label,
            lineterm="",
        )
    )


def select_filesystem_entry(
    *,
    base_path: str = ".",
    selection_mode: str = "any",
    recursive: bool = False,
    include_hidden: bool = False,
    glob_pattern: str | None = None,
    prompt: str = "Select a filesystem entry",
    multi: bool = False,
    limit: int = 100,
    shared_store: Dict[str, Any] | None = None,
    root_path: str | Path | None = None,
) -> Dict[str, Any]:
    try:
        normalized_mode = _normalize_selection_mode(selection_mode)
        root = _resolve_scoped_path(base_path, shared_store=shared_store, root_path=root_path)
        if not root.is_dir():
            return {"success": False, "error": f"Base path '{base_path}' is not a directory."}

        candidates = list(
            _iter_candidates(
                base_path=root,
                recursive=recursive,
                selection_mode=normalized_mode,
                include_hidden=include_hidden,
                glob_pattern=glob_pattern,
            )
        )
        if not candidates:
            return {"success": False, "error": "No matching files or folders found."}

        limited = candidates[: max(1, int(limit))]
        options = [
            {
                "id": str(candidate.relative_to(root)),
                "label": str(candidate.relative_to(root)),
                "value": str(candidate.relative_to(root)),
                "description": "directory" if candidate.is_dir() else "file",
            }
            for candidate in limited
        ]

        if multi:
            result = ask_user_checklist(
                prompt=prompt,
                options=options,
                shared_store=shared_store,
            )
            if not result.get("success"):
                return result
            values = list(result.get("values") or [])
            return {
                "success": True,
                "selected": values,
                "items": [opt["value"] for opt in options],
                "truncated": len(candidates) > len(limited),
            }

        result = ask_user_radio_group(
            prompt=prompt,
            options=options,
            shared_store=shared_store,
        )
        if not result.get("success"):
            return result
        return {
            "success": True,
            "selected": result.get("value"),
            "items": [opt["value"] for opt in options],
            "truncated": len(candidates) > len(limited),
        }
    except Exception as exc:
        logger.exception("Failed to select filesystem entry")
        return {"success": False, "error": str(exc)}


def extract_text(
    *,
    path: str | None = None,
    text: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    start_pattern: str | None = None,
    end_pattern: str | None = None,
    include_boundaries: bool = True,
    occurrence: int = 1,
    regex: bool = False,
    shared_store: Dict[str, Any] | None = None,
    root_path: str | Path | None = None,
) -> Dict[str, Any]:
    try:
        content, resolved_path = _resolve_content(
            path,
            text,
            shared_store=shared_store,
            root_path=root_path,
        )
        start_index, end_index = _line_bounds_from_spec(
            content,
            start_line=start_line,
            end_line=end_line,
            start_pattern=start_pattern,
            end_pattern=end_pattern,
            include_boundaries=include_boundaries,
            occurrence=occurrence,
            regex=regex,
        )
        lines = content.splitlines()
        extracted = "\n".join(lines[start_index : end_index + 1])
        return {
            "success": True,
            "content": extracted,
            "path": resolved_path,
            "start_line": start_index + 1,
            "end_line": end_index + 1,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _replace_by_match(
    content: str,
    *,
    replacement: str,
    match_text: str | None = None,
    match_pattern: str | None = None,
    regex: bool = False,
    count: int = 1,
) -> tuple[str, int]:
    if match_text:
        replaced = content.replace(match_text, replacement, count if count > 0 else -1)
        changes = 0 if replaced == content else min(content.count(match_text), count if count > 0 else content.count(match_text))
        return replaced, changes

    if not match_pattern:
        raise ValueError("Either match_text, match_pattern, or a line/pattern range is required.")

    replaced, changes = re.subn(
        match_pattern,
        replacement,
        content,
        count=0 if count <= 0 else count,
    ) if regex else re.subn(
        re.escape(match_pattern),
        replacement,
        content,
        count=0 if count <= 0 else count,
    )
    return replaced, changes


def stage_text_replace(
    *,
    replacement: str,
    path: str | None = None,
    text: str | None = None,
    match_text: str | None = None,
    match_pattern: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    start_pattern: str | None = None,
    end_pattern: str | None = None,
    include_boundaries: bool = True,
    occurrence: int = 1,
    regex: bool = False,
    count: int = 1,
    shared_store: Dict[str, Any] | None = None,
    root_path: str | Path | None = None,
) -> Dict[str, Any]:
    try:
        content, resolved_path = _resolve_content(
            path,
            text,
            shared_store=shared_store,
            root_path=root_path,
        )
        updated = content
        changed = 0
        change_start_line: int | None = None
        change_end_line: int | None = None

        if any(
            value is not None
            for value in (start_line, end_line, start_pattern, end_pattern)
        ):
            start_index, end_index = _line_bounds_from_spec(
                content,
                start_line=start_line,
                end_line=end_line,
                start_pattern=start_pattern,
                end_pattern=end_pattern,
                include_boundaries=include_boundaries,
                occurrence=occurrence,
                regex=regex,
            )
            start_offset, end_offset = _line_range_to_offsets(content, start_index, end_index)
            updated = content[:start_offset] + replacement + content[end_offset:]
            changed = 1
            change_start_line = start_index + 1
            change_end_line = end_index + 1
        else:
            updated, changed = _replace_by_match(
                content,
                replacement=replacement,
                match_text=match_text,
                match_pattern=match_pattern,
                regex=regex,
                count=count,
            )

        if updated == content:
            return {"success": False, "error": "No changes were staged."}

        diff = _build_unified_diff(content, updated, path=resolved_path)
        result: Dict[str, Any] = {
            "success": True,
            "path": resolved_path,
            "original_text": content,
            "updated_text": updated,
            "diff": diff,
            "changes": changed,
        }
        if change_start_line is not None:
            result["start_line"] = change_start_line
            result["end_line"] = change_end_line

        if shared_store is not None and resolved_path is not None:
            edit_id = f"edit_{uuid.uuid4().hex[:12]}"
            pending = shared_store.setdefault(_PENDING_FILE_EDITS_KEY, {})
            pending[edit_id] = {
                "path": resolved_path,
                "original_text": content,
                "updated_text": updated,
                "diff": diff,
            }
            result["edit_id"] = edit_id

        return result
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def apply_staged_edit(
    *,
    edit_id: str,
    shared_store: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    pending = (shared_store or {}).get(_PENDING_FILE_EDITS_KEY, {})
    if not isinstance(pending, dict) or edit_id not in pending:
        return {"success": False, "error": f"Unknown staged edit '{edit_id}'."}

    edit = pending[edit_id]
    path = str(edit["path"])
    updated_text = str(edit["updated_text"])
    try:
        _resolve_scoped_path(path, shared_store=shared_store)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    if not write_file(path, updated_text, shared_store=shared_store):
        return {"success": False, "error": f"Failed to write staged edit to '{path}'."}

    pending.pop(edit_id, None)
    return {
        "success": True,
        "path": path,
        "edit_id": edit_id,
        "message": f"Applied staged edit to '{path}'.",
    }


def cancel_staged_edit(
    *,
    edit_id: str | None = None,
    clear_all: bool = False,
    shared_store: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    pending = (shared_store or {}).setdefault(_PENDING_FILE_EDITS_KEY, {})
    if not isinstance(pending, dict):
        return {"success": False, "error": "Pending edit store is unavailable."}

    if clear_all:
        cleared = len(pending)
        pending.clear()
        return {"success": True, "cleared": cleared}

    if not edit_id:
        return {"success": False, "error": "Either 'edit_id' or 'clear_all=true' is required."}
    if edit_id not in pending:
        return {"success": False, "error": f"Unknown staged edit '{edit_id}'."}

    pending.pop(edit_id, None)
    return {"success": True, "edit_id": edit_id, "message": "Cancelled staged edit."}


class SelectFilesystemEntryTool(BaseTool):
    @property
    def name(self) -> str:
        return "select_filesystem_entry"

    @property
    def description(self) -> str:
        return "Prompts the CLI user to select one or more files or folders from the filesystem."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "base_path": {"type": "string", "default": "."},
                "selection_mode": {"type": "string", "enum": ["any", "file", "directory"], "default": "any"},
                "recursive": {"type": "boolean", "default": False},
                "include_hidden": {"type": "boolean", "default": False},
                "glob_pattern": {"type": "string"},
                "prompt": {"type": "string"},
                "multi": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 100},
            },
            "required": [],
        }

    def execute(self, **kwargs) -> Any:
        return select_filesystem_entry(
            base_path=str(kwargs.get("base_path", ".")),
            selection_mode=str(kwargs.get("selection_mode", "any")),
            recursive=bool(kwargs.get("recursive", False)),
            include_hidden=bool(kwargs.get("include_hidden", False)),
            glob_pattern=kwargs.get("glob_pattern"),
            prompt=str(kwargs.get("prompt", "Select a filesystem entry")),
            multi=bool(kwargs.get("multi", False)),
            limit=int(kwargs.get("limit", 100)),
            shared_store=kwargs.get("shared_store"),
        )


class ExtractTextTool(BaseTool):
    @property
    def name(self) -> str:
        return "extract_text"

    @property
    def description(self) -> str:
        return "Extracts a text range from a file or inline text using line numbers or boundary patterns."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "text": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
                "start_pattern": {"type": "string"},
                "end_pattern": {"type": "string"},
                "include_boundaries": {"type": "boolean", "default": True},
                "occurrence": {"type": "integer", "default": 1},
                "regex": {"type": "boolean", "default": False},
            },
            "required": [],
        }

    def execute(self, **kwargs) -> Any:
        return extract_text(
            path=kwargs.get("path"),
            text=kwargs.get("text"),
            start_line=kwargs.get("start_line"),
            end_line=kwargs.get("end_line"),
            start_pattern=kwargs.get("start_pattern"),
            end_pattern=kwargs.get("end_pattern"),
            include_boundaries=bool(kwargs.get("include_boundaries", True)),
            occurrence=int(kwargs.get("occurrence", 1)),
            regex=bool(kwargs.get("regex", False)),
            shared_store=kwargs.get("shared_store"),
        )


class StageTextReplaceTool(BaseTool):
    @property
    def name(self) -> str:
        return "stage_text_replace"

    @property
    def description(self) -> str:
        return "Builds a preview diff for a file/text replacement and stages file edits for later apply/cancel."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "replacement": {"type": "string"},
                "path": {"type": "string"},
                "text": {"type": "string"},
                "match_text": {"type": "string"},
                "match_pattern": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
                "start_pattern": {"type": "string"},
                "end_pattern": {"type": "string"},
                "include_boundaries": {"type": "boolean", "default": True},
                "occurrence": {"type": "integer", "default": 1},
                "regex": {"type": "boolean", "default": False},
                "count": {"type": "integer", "default": 1},
            },
            "required": ["replacement"],
        }

    def execute(self, **kwargs) -> Any:
        return stage_text_replace(
            replacement=str(kwargs.get("replacement", "")),
            path=kwargs.get("path"),
            text=kwargs.get("text"),
            match_text=kwargs.get("match_text"),
            match_pattern=kwargs.get("match_pattern"),
            start_line=kwargs.get("start_line"),
            end_line=kwargs.get("end_line"),
            start_pattern=kwargs.get("start_pattern"),
            end_pattern=kwargs.get("end_pattern"),
            include_boundaries=bool(kwargs.get("include_boundaries", True)),
            occurrence=int(kwargs.get("occurrence", 1)),
            regex=bool(kwargs.get("regex", False)),
            count=int(kwargs.get("count", 1)),
            shared_store=kwargs.get("shared_store"),
        )


class ApplyStagedEditTool(BaseTool):
    @property
    def name(self) -> str:
        return "apply_staged_edit"

    @property
    def description(self) -> str:
        return "Applies a previously staged file edit."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "edit_id": {"type": "string"},
            },
            "required": ["edit_id"],
        }

    def execute(self, **kwargs) -> Any:
        return apply_staged_edit(
            edit_id=str(kwargs.get("edit_id", "")),
            shared_store=kwargs.get("shared_store"),
        )


class CancelStagedEditTool(BaseTool):
    @property
    def name(self) -> str:
        return "cancel_staged_edit"

    @property
    def description(self) -> str:
        return "Cancels one staged edit or clears all pending staged edits."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "edit_id": {"type": "string"},
                "clear_all": {"type": "boolean", "default": False},
            },
            "required": [],
        }

    def execute(self, **kwargs) -> Any:
        return cancel_staged_edit(
            edit_id=kwargs.get("edit_id"),
            clear_all=bool(kwargs.get("clear_all", False)),
            shared_store=kwargs.get("shared_store"),
        )
