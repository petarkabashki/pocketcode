import json
import logging
import shutil
import subprocess
from typing import Optional, Dict, Any

from pocketcode.core.interfaces import BaseTool

logger = logging.getLogger(__name__)

_RG_PATH = shutil.which("rg")


def is_ripgrep_installed() -> bool:
    return _RG_PATH is not None


def search_code_func(
    query: str,
    path: str = ".",
    file_pattern: Optional[str] = None,
    case_sensitive: bool = False,
    context_lines: int = 2,
) -> Optional[str]:
    logger.info(
        "Searching for query '%s' in path '%s' (pattern=%s, case_sensitive=%s, context=%s)",
        query,
        path,
        file_pattern,
        case_sensitive,
        context_lines,
    )

    if not is_ripgrep_installed():
        return json.dumps({"success": False, "error": "ripgrep (rg) command not found in PATH."})

    args = [
        _RG_PATH,
        "--json",
        "--heading",
        "--line-number",
        "-C",
        str(context_lines),
    ]

    if file_pattern:
        args.extend(["-g", file_pattern])

    args.append("-s" if case_sensitive else "-i")
    args.extend([query, path])

    try:
        process = subprocess.run(args, capture_output=True, text=True, shell=False, check=False)
    except Exception as e:
        error_msg = f"Failed to execute ripgrep command: {e}"
        logger.error(error_msg)
        return json.dumps({"success": False, "error": error_msg})

    if process.returncode > 1:
        error_msg = (
            f"ripgrep command failed with return code {process.returncode}. "
            f"Stderr: {process.stderr.strip()}"
        )
        logger.error(error_msg)
        return json.dumps({"success": False, "error": error_msg, "stderr": process.stderr})

    return process.stdout


class SearchCodeTool(BaseTool):
    @property
    def name(self) -> str:
        return "search_code"

    @property
    def description(self) -> str:
        return "Searches code using ripgrep (rg) for a regex pattern. Returns newline-delimited JSON."

    @property
    def schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The regex pattern to search for."},
                "path": {"type": "string", "description": "Directory or file path to search within.", "default": "."},
                "file_pattern": {"type": "string", "description": "Glob pattern to filter files (e.g., '*.py')."},
                "case_sensitive": {"type": "boolean", "description": "Perform case-sensitive search.", "default": False},
                "context_lines": {"type": "integer", "description": "Number of context lines around matches.", "default": 2},
            },
            "required": ["query"],
        }

    def execute(self, **kwargs) -> Any:
        query = kwargs.get("query")
        if query is None:
            return {"success": False, "error": "Missing required argument 'query'."}

        json_output_str = search_code_func(
            query=query,
            path=kwargs.get("path", "."),
            file_pattern=kwargs.get("file_pattern"),
            case_sensitive=kwargs.get("case_sensitive", False),
            context_lines=kwargs.get("context_lines", 2),
        )

        try:
            if not json_output_str and isinstance(json_output_str, str):
                return {"success": True, "results": [], "message": "No matches found."}

            results = []
            for line in json_output_str.strip().split("\n"):
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError as json_err:
                    logger.warning("Failed to decode JSON line from rg output: %s", json_err)

            if results and isinstance(results[0], dict) and results[0].get("success") is False:
                return results[0]

            return {"success": True, "results": results}
        except Exception as e:
            logger.exception("Unexpected error processing search results: %s", e)
            return {"success": False, "error": f"An unexpected error occurred: {e}"}
