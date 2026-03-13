from __future__ import annotations

from pathlib import Path
from typing import Iterable


TOOL_MODULE_SUFFIX = ".tool.py"


def iter_tool_module_files(root: Path) -> list[Path]:
    resolved_root = Path(root).resolve()
    return sorted(
        path
        for path in resolved_root.rglob(f"*{TOOL_MODULE_SUFFIX}")
        if path.is_file()
    )


def iter_convention_tool_files(root: Path) -> Iterable[Path]:
    resolved_root = Path(root).resolve()
    for path in sorted(resolved_root.rglob(f"*{TOOL_MODULE_SUFFIX}")):
        if path.is_file():
            yield path
