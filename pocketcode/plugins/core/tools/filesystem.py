from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pocketcode.core.interfaces import BaseTool

logger = logging.getLogger(__name__)

__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "WriteToFileTool",
    "ListFilesTool",
    "CreateDirectoryTool",
    "GlobFilesTool",
    "read_file",
    "write_file",
    "create_directory",
    "list_directory",
    "glob_files",
]


def _coerce_path(path: str) -> Path:
    return Path(path).expanduser()


def read_file(path: str) -> Optional[str]:
    """Read a UTF-8 text file and return its content."""
    logger.info("Reading file: %s", path)
    try:
        file_path = _coerce_path(path)
        if not file_path.is_file():
            logger.error("File not found or is not a regular file: %s", path)
            return None
        content = file_path.read_text(encoding="utf-8")
        logger.info("Successfully read %s characters from %s", len(content), path)
        return content
    except FileNotFoundError:
        logger.error("File not found: %s", path)
        return None
    except Exception:
        logger.exception("An error occurred while reading file '%s'", path)
        return None


def write_file(path: str, content: str) -> bool:
    """Write UTF-8 text to a file, creating parent directories as needed."""
    logger.info("Writing to file: %s (%s characters)", path, len(content))
    try:
        file_path = _coerce_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        logger.info("Successfully wrote to %s", path)
        return True
    except Exception:
        logger.exception("An error occurred while writing file '%s'", path)
        return False


def create_directory(path: str) -> bool:
    """Create a directory and any missing parents."""
    logger.info("Creating directory: %s", path)
    try:
        dir_path = _coerce_path(path)
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.info("Directory ensured: %s", path)
        return True
    except Exception:
        logger.exception("An error occurred while creating directory '%s'", path)
        return False


def list_directory(path: str = ".", recursive: bool = False) -> Optional[List[str]]:
    """List directory entries, returning stable relative paths."""
    logger.info("Listing directory: %s (recursive=%s)", path, recursive)
    try:
        dir_path = _coerce_path(path)
        if not dir_path.is_dir():
            logger.error("Path is not a valid directory: %s", path)
            return None

        if recursive:
            items = [
                str(entry.relative_to(dir_path))
                for entry in sorted(dir_path.rglob("*"))
            ]
        else:
            items = [entry.name for entry in sorted(dir_path.iterdir(), key=lambda item: item.name)]

        logger.info("Found %s items in %s", len(items), path)
        return items
    except Exception:
        logger.exception("An error occurred while listing directory '%s'", path)
        return None


def glob_files(pattern: str, base_path: str = ".") -> Optional[List[str]]:
    """Return glob matches relative to the requested base directory."""
    logger.info("Globbing pattern '%s' in base path '%s'", pattern, base_path)
    try:
        base = _coerce_path(base_path)
        if not base.is_dir():
            logger.error("Base path is not a valid directory: %s", base_path)
            return None

        matches = [
            str(match.relative_to(base))
            for match in sorted(base.glob(pattern))
        ]
        logger.info("Found %s matches for pattern '%s' in '%s'", len(matches), pattern, base_path)
        return matches
    except Exception:
        logger.exception("An error occurred while globbing pattern '%s' in '%s'", pattern, base_path)
        return None


# --- Tool Classes ---
# --- Tool Class Definitions ---

class ReadFileTool(BaseTool):
    """Tool to read the content of a file."""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Reads the entire content of a specified file."

    @property
    def schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path of the file to read."}
            },
            "required": ["path"]
        }

    def execute(self, **kwargs) -> Any:
        path = kwargs.get("path")
        if path is None:
            logger.error(f"{self.name}: Missing required argument 'path'.")
            return {"success": False, "error": "Missing required argument 'path'."}

        content = read_file(path=path)

        if content is not None:
            return {"success": True, "content": content}
        else:
            # Error logged within read_file function
            return {"success": False, "error": f"Failed to read file '{path}'."}


class WriteToFileTool(BaseTool):
    """Tool to write content to a file."""

    @property
    def name(self) -> str:
        return "write_to_file"

    @property
    def description(self) -> str:
        return "Writes content to a file, overwriting if it exists or creating it if it doesn't. Creates parent directories if needed."

    @property
    def schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path of the file to write to."},
                "content": {"type": "string", "description": "The content to write into the file."}
            },
            "required": ["path", "content"]
        }

    def execute(self, **kwargs) -> Any:
        path = kwargs.get("path")
        content = kwargs.get("content")
        if path is None or content is None:
            logger.error(f"{self.name}: Missing required arguments 'path' or 'content'.")
            return {"success": False, "error": "Missing required arguments 'path' or 'content'."}

        success = write_file(path=path, content=content)
        if success:
            return {"success": True, "message": f"Successfully wrote to {path}."}
        else:
            # Error logged within write_file function
            return {"success": False, "error": f"Failed to write to file '{path}'."}


class WriteFileTool(WriteToFileTool):
    """Backward-compatible alias for older manifests importing WriteFileTool."""


class ListFilesTool(BaseTool):
    """Tool to list files and directories."""

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return "Lists files and directories within a specified path. Can list recursively."

    @property
    def schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path of the directory to list.", "default": "."},
                "recursive": {"type": "boolean", "description": "Whether to list files recursively.", "default": False}
            },
            "required": [] # path defaults to '.'
        }

    def execute(self, **kwargs) -> Any:
        path = kwargs.get("path", ".") # Default to current directory
        recursive = kwargs.get("recursive", False) # Default to non-recursive

        items = list_directory(path=path, recursive=recursive)

        if items is not None:
            return {"success": True, "items": items}
        else:
            # Error logged within list_directory function
            return {"success": False, "error": f"Failed to list directory '{path}'."}


class CreateDirectoryTool(BaseTool):
    """Tool to create a directory."""

    @property
    def name(self) -> str:
        return "create_directory"

    @property
    def description(self) -> str:
        return "Creates a directory, including parent directories if needed."

    @property
    def schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path of the directory to create."}
            },
            "required": ["path"]
        }

    def execute(self, **kwargs) -> Any:
        path = kwargs.get("path")
        if path is None:
            logger.error(f"{self.name}: Missing required argument 'path'.")
            return {"success": False, "error": "Missing required argument 'path'."}

        success = create_directory(path=path)
        if success:
            return {"success": True, "message": f"Directory ensured: {path}."}
        else:
            # Error logged within create_directory function
            return {"success": False, "error": f"Failed to create directory '{path}'."}


class GlobFilesTool(BaseTool):
    """Tool to find files/directories matching a glob pattern."""

    @property
    def name(self) -> str:
        return "glob_files"

    @property
    def description(self) -> str:
        return "Finds files and directories matching a glob pattern."

    @property
    def schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g. '*.py', 'src/**/*.md')."},
                "base_path": {"type": "string", "description": "Base directory for the search.", "default": "."}
            },
            "required": ["pattern"]
        }

    def execute(self, **kwargs) -> Any:
        pattern = kwargs.get("pattern")
        base_path = kwargs.get("base_path", ".") # Default to current directory

        if pattern is None:
            logger.error(f"{self.name}: Missing required argument 'pattern'.")
            return {"success": False, "error": "Missing required argument 'pattern'."}

        matches = glob_files(pattern=pattern, base_path=base_path)

        if matches is not None:
            return {"success": True, "matches": matches}
        else:
            # Error logged within glob_files function
            return {"success": False, "error": f"Failed to glob pattern '{pattern}' in '{base_path}'."}
