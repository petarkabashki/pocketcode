# Backward-compatibility re-export shim.
# Canonical implementation: pocketcode/plugins/core/tools/search.py
from pocketcode.plugins.core.tools.search import (  # noqa: F401
    SearchCodeTool,
    search_code_func,
    is_ripgrep_installed,
)

__all__ = [
    "SearchCodeTool",
    "search_code_func",
    "is_ripgrep_installed",
]
