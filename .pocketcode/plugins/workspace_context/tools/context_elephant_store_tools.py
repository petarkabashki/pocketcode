from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from pocketcode.config.loader import load_settings
from pocketcode.core.context_elephant_store import ContextElephantStoreManager
from pocketcode.core.interfaces import BaseTool

logger = logging.getLogger(__name__)
_MANAGER_CACHE: Dict[str, ContextElephantStoreManager] = {}


class ContextElephantStoreToolError(Exception):
    """Base class for context elephant store tool errors."""


class ProjectNotFoundError(ContextElephantStoreToolError):
    """Raised when the specified project path is invalid or lacks a context elephant store."""


class InvalidContextElephantStoreFileNameError(ContextElephantStoreToolError):
    """Raised when an invalid context elephant store file name is provided."""


class ContextElephantStoreFileNotFoundError(ContextElephantStoreToolError):
    """Raised when a specified context elephant store file is not found."""


class WriteError(ContextElephantStoreToolError):
    """Raised for general file writing/appending errors."""


class ReadError(ContextElephantStoreToolError):
    """Raised for general file reading errors."""


class SummarizationError(ContextElephantStoreToolError):
    """Raised if summary generation fails."""


def _get_context_elephant_store_manager(project_path: Optional[str] = None) -> ContextElephantStoreManager:
    try:
        settings = load_settings()
        core_config = settings.get("core", {})
        default_project_root = os.getcwd()
    except Exception as exc:
        logger.error(f"Failed to load settings or determine default project root: {exc}")
        core_config = {
            "enable_context_elephant_store": False,
            "context_elephant_store_dir": "context_elephant_store",
            "context_elephant_store_files": [
                "productContext.md",
                "activeContext.md",
                "systemPatterns.md",
                "techContext.md",
                "progress.md",
            ],
        }
        default_project_root = os.getcwd()

    effective_project_root = project_path if project_path else default_project_root
    if not os.path.isdir(effective_project_root):
        raise ProjectNotFoundError(f"Effective project root is not a valid directory: {effective_project_root}")

    cache_key = os.path.abspath(effective_project_root)
    if cache_key in _MANAGER_CACHE:
        return _MANAGER_CACHE[cache_key]

    manager = ContextElephantStoreManager(core_config=core_config, project_root=effective_project_root)
    _MANAGER_CACHE[cache_key] = manager
    return manager


def _validate_file_name(manager: ContextElephantStoreManager, file_name: str) -> None:
    if file_name not in manager.required_files:
        raise InvalidContextElephantStoreFileNameError(
            f"Invalid context elephant store file name: '{file_name}'. Must be one of {manager.required_files}"
        )


def _get_full_path(manager: ContextElephantStoreManager, file_name: str) -> str:
    _validate_file_name(manager, file_name)
    return os.path.join(manager.get_context_elephant_store_path(), file_name)


def read_context_elephant_store_file(file_name: str, project_path: Optional[str] = None) -> str:
    logger.info(f"Reading context elephant store file '{file_name}' from project '{project_path or 'default'}'.")
    try:
        manager = _get_context_elephant_store_manager(project_path)
        full_path = _get_full_path(manager, file_name)
        if not os.path.exists(full_path):
            raise ContextElephantStoreFileNotFoundError(f"Context elephant store file not found: {full_path}")
        if not os.path.isfile(full_path):
            raise ContextElephantStoreFileNotFoundError(f"Path exists but is not a file: {full_path}")

        with open(full_path, "r", encoding="utf-8") as handle:
            content = handle.read()
        logger.info(f"Successfully read {len(content)} bytes from '{file_name}'.")
        return content
    except (InvalidContextElephantStoreFileNameError, ContextElephantStoreFileNotFoundError, ProjectNotFoundError) as exc:
        logger.error(f"Error reading context elephant store file '{file_name}': {exc}")
        raise exc
    except IOError as exc:
        logger.error(f"IOError reading file {file_name}: {exc}")
        raise ReadError(f"Failed to read file '{file_name}': {exc}") from exc
    except Exception as exc:
        logger.error(f"Unexpected error reading file {file_name}: {exc}")
        raise ReadError(f"An unexpected error occurred while reading '{file_name}': {exc}") from exc


def write_context_elephant_store_file(file_name: str, content: str, project_path: Optional[str] = None) -> bool:
    logger.info(f"Writing to context elephant store file '{file_name}' in project '{project_path or 'default'}'.")
    try:
        manager = _get_context_elephant_store_manager(project_path)
        _validate_file_name(manager, file_name)
        context_elephant_store_dir = manager.get_context_elephant_store_path()
        full_path = os.path.join(context_elephant_store_dir, file_name)
        os.makedirs(context_elephant_store_dir, exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        logger.info(f"Successfully wrote {len(content)} bytes to '{file_name}'.")
        return True
    except (InvalidContextElephantStoreFileNameError, ProjectNotFoundError) as exc:
        logger.error(f"Error writing context elephant store file '{file_name}': {exc}")
        raise exc
    except OSError as exc:
        logger.error(f"OSError writing file {file_name}: {exc}")
        raise WriteError(f"Failed to write file '{file_name}': {exc}") from exc
    except Exception as exc:
        logger.error(f"Unexpected error writing file {file_name}: {exc}")
        raise WriteError(f"An unexpected error occurred while writing '{file_name}': {exc}") from exc


def append_to_context_elephant_store_file(file_name: str, content: str, project_path: Optional[str] = None) -> bool:
    logger.info(f"Appending to context elephant store file '{file_name}' in project '{project_path or 'default'}'.")
    try:
        manager = _get_context_elephant_store_manager(project_path)
        _validate_file_name(manager, file_name)
        context_elephant_store_dir = manager.get_context_elephant_store_path()
        full_path = os.path.join(context_elephant_store_dir, file_name)
        os.makedirs(context_elephant_store_dir, exist_ok=True)

        prefix = ""
        if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
            with open(full_path, "r", encoding="utf-8") as handle:
                handle.seek(0, os.SEEK_END)
                handle.seek(handle.tell() - 1, os.SEEK_SET)
                if handle.read(1) != "\n":
                    prefix = "\n"

        with open(full_path, "a", encoding="utf-8") as handle:
            handle.write(prefix + content)
        logger.info(f"Successfully appended {len(prefix + content)} bytes to '{file_name}'.")
        return True
    except (InvalidContextElephantStoreFileNameError, ProjectNotFoundError) as exc:
        logger.error(f"Error appending to context elephant store file '{file_name}': {exc}")
        raise exc
    except OSError as exc:
        logger.error(f"OSError appending to file {file_name}: {exc}")
        raise WriteError(f"Failed to append to file '{file_name}': {exc}") from exc
    except Exception as exc:
        logger.error(f"Unexpected error appending to file {file_name}: {exc}")
        raise WriteError(f"An unexpected error occurred while appending to '{file_name}': {exc}") from exc


def get_context_elephant_store_summary(
    file_names: Optional[List[str]] = None,
    topic: Optional[str] = None,
    project_path: Optional[str] = None,
) -> str:
    logger.info(
        f"Getting context elephant store summary for files: {file_names or 'all'}, topic: '{topic}', project: '{project_path or 'default'}'."
    )
    if topic:
        logger.warning("The 'topic' parameter is currently ignored in this basic summary implementation.")

    summary_parts = []
    try:
        manager = _get_context_elephant_store_manager(project_path)
        files_to_process = file_names if file_names is not None else manager.required_files
        if not files_to_process:
            return "No context elephant store files specified or configured to summarize."

        for file_name in files_to_process:
            try:
                content = read_context_elephant_store_file(file_name, project_path=project_path)
                summary_parts.append(f"--- Content from: {file_name} ---\n{content}\n")
            except ContextElephantStoreFileNotFoundError:
                logger.warning(f"Context elephant store file '{file_name}' not found during summary generation. Skipping.")
                summary_parts.append(f"--- Content from: {file_name} (Not Found) ---\n")
            except (InvalidContextElephantStoreFileNameError, ReadError, ProjectNotFoundError) as exc:
                raise exc

        if not summary_parts:
            return "No content found for the specified context elephant store files."
        return "\n".join(summary_parts).strip()
    except (InvalidContextElephantStoreFileNameError, ProjectNotFoundError, ReadError) as exc:
        logger.error(f"Error generating context elephant store summary: {exc}")
        raise exc
    except Exception as exc:
        logger.error(f"Unexpected error generating summary: {exc}")
        raise SummarizationError(f"An unexpected error occurred during summary generation: {exc}") from exc


def check_context_elephant_store_status(project_path: Optional[str] = None) -> Dict[str, str]:
    logger.info(f"Checking context elephant store status for project '{project_path or 'default'}'.")
    status: Dict[str, str] = {}
    try:
        manager = _get_context_elephant_store_manager(project_path)
        context_elephant_store_dir = manager.get_context_elephant_store_path()
        if not os.path.isdir(context_elephant_store_dir):
            logger.warning(
                f"Context elephant store directory not found at: {context_elephant_store_dir}. Reporting all files as MISSING."
            )
            for file_name in manager.required_files:
                status[file_name] = "MISSING"
            return status

        if not manager.required_files:
            logger.info("No required context elephant store files configured. Status check complete.")
            return {}

        for file_name in manager.required_files:
            full_path = os.path.join(context_elephant_store_dir, file_name)
            try:
                if not os.path.exists(full_path):
                    status[file_name] = "MISSING"
                elif not os.path.isfile(full_path):
                    status[file_name] = "ERROR"
                    logger.warning(f"Context elephant store path exists but is not a file: {full_path}")
                elif os.path.getsize(full_path) == 0:
                    status[file_name] = "EMPTY"
                else:
                    status[file_name] = "OK"
            except OSError as exc:
                logger.error(f"Error checking status for file {full_path}: {exc}")
                status[file_name] = "ERROR"

        logger.info(f"Context elephant store status check complete: {status}")
        return status
    except ProjectNotFoundError as exc:
        logger.error(f"Error checking context elephant store status: {exc}")
        raise exc
    except Exception as exc:
        logger.error(f"Unexpected error checking context elephant store status: {exc}")
        status["_GENERAL_ERROR_"] = str(exc)
        return status


class ReadContextElephantStoreFileTool(BaseTool):
    @property
    def name(self) -> str:
        return "read_context_elephant_store_file"

    @property
    def description(self) -> str:
        return "Reads the entire content of a specified Context Elephant Store file (e.g., productContext.md)."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_name": {"type": "string", "description": "The name of the Context Elephant Store file (e.g., 'productContext.md')."},
                "project_path": {"type": ["string", "null"], "description": "Absolute or relative path to the project root. Defaults to current project."},
            },
            "required": ["file_name"],
        }

    def execute(self, **kwargs) -> str:
        return read_context_elephant_store_file(
            file_name=kwargs.get("file_name"),
            project_path=kwargs.get("project_path"),
        )


class WriteContextElephantStoreFileTool(BaseTool):
    @property
    def name(self) -> str:
        return "write_context_elephant_store_file"

    @property
    def description(self) -> str:
        return "Writes content to a specified Context Elephant Store file, overwriting existing content. Creates the directory/file if needed."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_name": {"type": "string", "description": "The name of the Context Elephant Store file to write to."},
                "content": {"type": "string", "description": "The new content to write."},
                "project_path": {"type": ["string", "null"], "description": "Path to the project root."},
            },
            "required": ["file_name", "content"],
        }

    def execute(self, **kwargs) -> bool:
        return write_context_elephant_store_file(
            file_name=kwargs.get("file_name"),
            content=kwargs.get("content"),
            project_path=kwargs.get("project_path"),
        )


class AppendToContextElephantStoreFileTool(BaseTool):
    @property
    def name(self) -> str:
        return "append_to_context_elephant_store_file"

    @property
    def description(self) -> str:
        return "Appends content to a specified Context Elephant Store file. Creates the file/directory if needed. Adds a newline before appending if necessary."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_name": {"type": "string", "description": "The name of the Context Elephant Store file to append to."},
                "content": {"type": "string", "description": "The content to append."},
                "project_path": {"type": ["string", "null"], "description": "Path to the project root."},
            },
            "required": ["file_name", "content"],
        }

    def execute(self, **kwargs) -> bool:
        return append_to_context_elephant_store_file(
            file_name=kwargs.get("file_name"),
            content=kwargs.get("content"),
            project_path=kwargs.get("project_path"),
        )


class GetContextElephantStoreSummaryTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_context_elephant_store_summary"

    @property
    def description(self) -> str:
        return "Retrieves a concise summary by concatenating the content of specified Context Elephant Store files."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_names": {"type": ["array", "null"], "items": {"type": "string"}, "description": "List of Context Elephant Store file names to include. Defaults to all if null."},
                "topic": {"type": ["string", "null"], "description": "Specific topic (currently ignored)."},
                "project_path": {"type": ["string", "null"], "description": "Path to the project root."},
            },
            "required": [],
        }

    def execute(self, **kwargs) -> str:
        return get_context_elephant_store_summary(
            file_names=kwargs.get("file_names"),
            topic=kwargs.get("topic"),
            project_path=kwargs.get("project_path"),
        )


class CheckContextElephantStoreStatusTool(BaseTool):
    @property
    def name(self) -> str:
        return "check_context_elephant_store_status"

    @property
    def description(self) -> str:
        return "Verifies the existence and basic validity (non-empty) of standard Context Elephant Store files."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_path": {"type": ["string", "null"], "description": "Path to the project root."}
            },
            "required": [],
        }

    def execute(self, **kwargs) -> Dict[str, str]:
        return check_context_elephant_store_status(project_path=kwargs.get("project_path"))


__all__ = [
    "ReadContextElephantStoreFileTool",
    "WriteContextElephantStoreFileTool",
    "AppendToContextElephantStoreFileTool",
    "GetContextElephantStoreSummaryTool",
    "CheckContextElephantStoreStatusTool",
    "ContextElephantStoreToolError",
    "ProjectNotFoundError",
    "InvalidContextElephantStoreFileNameError",
    "ContextElephantStoreFileNotFoundError",
    "WriteError",
    "ReadError",
    "SummarizationError",
    "read_context_elephant_store_file",
    "write_context_elephant_store_file",
    "append_to_context_elephant_store_file",
    "get_context_elephant_store_summary",
    "check_context_elephant_store_status",
]