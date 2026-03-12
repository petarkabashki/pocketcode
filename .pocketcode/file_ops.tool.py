"""Workspace wrappers for shared file operation tools.

Workspace auto-registration requires module-local callables, so these wrappers
forward to the canonical core implementations.
"""

from pocketcode.core_tools.file_ops import (
    apply_staged_edit as _apply_staged_edit,
    cancel_staged_edit as _cancel_staged_edit,
    extract_text as _extract_text,
    select_filesystem_entry as _select_filesystem_entry,
    stage_text_replace as _stage_text_replace,
)


def select_filesystem_entry(**kwargs):
    return _select_filesystem_entry(**kwargs)


def extract_text(**kwargs):
    return _extract_text(**kwargs)


def stage_text_replace(**kwargs):
    return _stage_text_replace(**kwargs)


def apply_staged_edit(**kwargs):
    return _apply_staged_edit(**kwargs)


def cancel_staged_edit(**kwargs):
    return _cancel_staged_edit(**kwargs)


TOOLS = {
    "select_filesystem_entry": select_filesystem_entry,
    "extract_text": extract_text,
    "stage_text_replace": stage_text_replace,
    "apply_staged_edit": apply_staged_edit,
    "cancel_staged_edit": cancel_staged_edit,
}

__all__ = [
    "select_filesystem_entry",
    "extract_text",
    "stage_text_replace",
    "apply_staged_edit",
    "cancel_staged_edit",
    "TOOLS",
]
