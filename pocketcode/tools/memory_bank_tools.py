# %%
# pocketcode/tools/memory_bank_tools.py
import os
import logging
from typing import List, Dict, Optional, Union, Any # Added Any

# Assuming MemoryBankManager is accessible, either via import and instantiation
# or passed through context. For now, we'll import and instantiate as needed.
# This might need adjustment based on the final tool execution framework.
from pocketcode.core.memory_bank import MemoryBankManager
# Assuming core_config and default project_root are somehow available in the execution context.
# This is a placeholder - the actual way to get config/root needs clarification.
from pocketcode.config.loader import load_settings # Example: How config might be loaded
# Import BaseTool for wrapper classes
from pocketcode.core.interfaces import BaseTool

logger = logging.getLogger(__name__)

# --- Custom Exceptions ---

class MemoryBankToolError(Exception):
    """Base class for memory bank tool errors."""
    pass

class ProjectNotFoundError(MemoryBankToolError):
    """Raised when the specified project path is invalid or lacks a memory bank."""
    pass

class InvalidMemoryBankFileNameError(MemoryBankToolError):
    """Raised when an invalid memory bank file name is provided."""
    pass

class MemoryBankFileNotFoundError(MemoryBankToolError):
    """Raised when a specified memory bank file is not found."""
    pass

class WriteError(MemoryBankToolError):
    """Raised for general file writing/appending errors."""
    pass

class ReadError(MemoryBankToolError):
    """Raised for general file reading errors."""
    pass

class SummarizationError(MemoryBankToolError):
    """Raised if summary generation fails."""
    pass


# --- Helper Function ---

def _get_memory_bank_manager(project_path: Optional[str] = None) -> MemoryBankManager:
    """
    Helper to get or create a MemoryBankManager instance.
    Handles resolving the project path and loading configuration.
    NOTE: This assumes a way to get the default project root and core config.
          This part might need significant refinement based on the actual execution context.
    """
    # Placeholder: Load settings to get core_config and default project root
    # In a real scenario, this might come from a global context or be passed differently.
    try:
        settings = load_settings() # Assumes settings.yaml is in CWD or discoverable
        core_config = settings.get('core', {})
        # Determine default project root (e.g., current working directory)
        default_project_root = os.getcwd() # Example: using CWD as default
    except Exception as e:
        logger.error(f"Failed to load settings or determine default project root: {e}")
        # Fallback to basic defaults if loading fails
        core_config = {'enable_memory_bank': True, 'memory_bank_dir': 'pocketcode_docs', 'memory_bank_files': ["productContext.md", "activeContext.md", "systemPatterns.md", "techContext.md", "progress.md"]}
        default_project_root = os.getcwd()

    effective_project_root = project_path if project_path else default_project_root

    # Basic validation of the effective project root
    if not os.path.isdir(effective_project_root):
         raise ProjectNotFoundError(f"Effective project root is not a valid directory: {effective_project_root}")

    manager = MemoryBankManager(core_config=core_config, project_root=effective_project_root)

    # Check if the memory bank directory exists within the effective root
    # Note: MemoryBankManager itself doesn't raise ProjectNotFoundError for the *directory*
    # It only uses the project_root to construct the path. We add a check here.
    if not os.path.isdir(manager.get_memory_bank_path()):
         # Only raise if the directory is *expected* but missing.
         # For write/append/create, the directory might be created later.
         # For read/summary/check, it should exist.
         # Let's refine this check within each tool function where needed.
         pass # Defer check to individual tools

    return manager

def _validate_file_name(manager: MemoryBankManager, file_name: str):
    """Checks if the file name is in the list of required/valid files."""
    if file_name not in manager.required_files:
        raise InvalidMemoryBankFileNameError(
            f"Invalid memory bank file name: '{file_name}'. Must be one of {manager.required_files}"
        )

def _get_full_path(manager: MemoryBankManager, file_name: str) -> str:
    """Gets the full, validated path for a memory bank file."""
    _validate_file_name(manager, file_name)
    return os.path.join(manager.get_memory_bank_path(), file_name)

# --- Tool Function Implementations ---

def read_memory_bank_file(file_name: str, project_path: Optional[str] = None) -> str:
    """
    Reads the entire content of a specified Memory Bank file.

    Args:
        file_name: The name of the Memory Bank file (e.g., "productContext.md").
        project_path: Absolute or relative path to the project root. Defaults to current project.

    Returns:
        The content of the specified file.

    Raises:
        ProjectNotFoundError: If project_path is invalid.
        InvalidMemoryBankFileNameError: If file_name is not a valid Memory Bank file.
        MemoryBankFileNotFoundError: If the specified file does not exist.
        ReadError: For general file reading errors.
    """
    logger.info(f"Reading memory bank file '{file_name}' from project '{project_path or 'default'}'.")
    try:
        manager = _get_memory_bank_manager(project_path)
        full_path = _get_full_path(manager, file_name)

        if not os.path.exists(full_path):
            raise MemoryBankFileNotFoundError(f"Memory bank file not found: {full_path}")
        if not os.path.isfile(full_path):
             raise MemoryBankFileNotFoundError(f"Path exists but is not a file: {full_path}") # Treat as not found

        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        logger.info(f"Successfully read {len(content)} bytes from '{file_name}'.")
        return content
    except (InvalidMemoryBankFileNameError, MemoryBankFileNotFoundError, ProjectNotFoundError) as e:
        logger.error(f"Error reading memory bank file '{file_name}': {e}")
        raise e
    except IOError as e:
        logger.error(f"IOError reading file {file_name}: {e}")
        raise ReadError(f"Failed to read file '{file_name}': {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error reading file {file_name}: {e}")
        raise ReadError(f"An unexpected error occurred while reading '{file_name}': {e}") from e


def write_memory_bank_file(file_name: str, content: str, project_path: Optional[str] = None) -> bool:
    """
    Writes content to a specified Memory Bank file, overwriting existing content.
    Creates the directory and file if they don't exist.

    Args:
        file_name: The name of the Memory Bank file to write to.
        content: The new content to write.
        project_path: Path to the project root.

    Returns:
        True if the write operation was successful.

    Raises:
        ProjectNotFoundError: If project_path is invalid (but directory creation might fix it).
        InvalidMemoryBankFileNameError: If file_name is not valid.
        WriteError: For general file writing errors.
    """
    logger.info(f"Writing to memory bank file '{file_name}' in project '{project_path or 'default'}'.")
    try:
        manager = _get_memory_bank_manager(project_path)
        _validate_file_name(manager, file_name) # Check name before path ops
        memory_bank_dir = manager.get_memory_bank_path()
        full_path = os.path.join(memory_bank_dir, file_name)

        # Ensure directory exists
        os.makedirs(memory_bank_dir, exist_ok=True)

        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Successfully wrote {len(content)} bytes to '{file_name}'.")
        return True
    except (InvalidMemoryBankFileNameError, ProjectNotFoundError) as e:
         logger.error(f"Error writing memory bank file '{file_name}': {e}")
         raise e
    except OSError as e:
        logger.error(f"OSError writing file {file_name}: {e}")
        raise WriteError(f"Failed to write file '{file_name}': {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error writing file {file_name}: {e}")
        raise WriteError(f"An unexpected error occurred while writing '{file_name}': {e}") from e


def append_to_memory_bank_file(file_name: str, content: str, project_path: Optional[str] = None) -> bool:
    """
    Appends content to a specified Memory Bank file. Creates the file/directory if needed.
    Adds a newline before appending if the file exists and doesn't end with one.

    Args:
        file_name: The name of the Memory Bank file to append to.
        content: The content to append.
        project_path: Path to the project root.

    Returns:
        True if the append operation was successful.

    Raises:
        ProjectNotFoundError: If project_path is invalid.
        InvalidMemoryBankFileNameError: If file_name is not valid.
        WriteError: For general file writing/appending errors.
    """
    logger.info(f"Appending to memory bank file '{file_name}' in project '{project_path or 'default'}'.")
    try:
        manager = _get_memory_bank_manager(project_path)
        _validate_file_name(manager, file_name)
        memory_bank_dir = manager.get_memory_bank_path()
        full_path = os.path.join(memory_bank_dir, file_name)

        # Ensure directory exists
        os.makedirs(memory_bank_dir, exist_ok=True)

        prefix = ""
        if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
            # Check if file ends with a newline
            with open(full_path, 'r', encoding='utf-8') as f:
                f.seek(0, os.SEEK_END) # Go to end of file
                f.seek(f.tell() - 1, os.SEEK_SET) # Go to last character
                if f.read(1) != '\n':
                    prefix = '\n' # Add newline if last char isn't one

        with open(full_path, 'a', encoding='utf-8') as f:
            f.write(prefix + content)
        logger.info(f"Successfully appended {len(prefix + content)} bytes to '{file_name}'.")
        return True
    except (InvalidMemoryBankFileNameError, ProjectNotFoundError) as e:
         logger.error(f"Error appending to memory bank file '{file_name}': {e}")
         raise e
    except OSError as e:
        logger.error(f"OSError appending to file {file_name}: {e}")
        raise WriteError(f"Failed to append to file '{file_name}': {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error appending to file {file_name}: {e}")
        raise WriteError(f"An unexpected error occurred while appending to '{file_name}': {e}") from e


def get_memory_bank_summary(file_names: Optional[List[str]] = None, topic: Optional[str] = None, project_path: Optional[str] = None) -> str:
    """
    Retrieves a concise summary by concatenating the content of specified Memory Bank files.

    Args:
        file_names: List of Memory Bank file names to include. Defaults to all if None.
        topic: Specific topic (currently ignored in this basic implementation).
        project_path: Path to the project root.

    Returns:
        The generated summary (concatenated content).

    Raises:
        ProjectNotFoundError: If project_path is invalid.
        InvalidMemoryBankFileNameError: If any file_name is not valid.
        MemoryBankFileNotFoundError: If any specified file does not exist.
        SummarizationError: For general errors during summary generation.
        ReadError: If reading a file fails.
    """
    logger.info(f"Getting memory bank summary for files: {file_names or 'all'}, topic: '{topic}', project: '{project_path or 'default'}'.")
    if topic:
        logger.warning("The 'topic' parameter is currently ignored in this basic summary implementation.")

    summary_parts = []
    try:
        manager = _get_memory_bank_manager(project_path)
        files_to_process = file_names if file_names is not None else manager.required_files

        if not files_to_process:
             return "No memory bank files specified or configured to summarize."

        for file_name in files_to_process:
            # Validate and get path implicitly via read_memory_bank_file
            try:
                content = read_memory_bank_file(file_name, project_path=project_path) # Reuse read logic
                summary_parts.append(f"--- Content from: {file_name} ---\n{content}\n")
            except MemoryBankFileNotFoundError:
                 # Allow summarization to proceed even if some files are missing, but log it.
                 logger.warning(f"Memory bank file '{file_name}' not found during summary generation. Skipping.")
                 summary_parts.append(f"--- Content from: {file_name} (Not Found) ---\n")
            except (InvalidMemoryBankFileNameError, ReadError, ProjectNotFoundError) as e:
                 # Propagate critical errors
                 raise e

        if not summary_parts:
             # Should only happen if all files were missing and none were required
             return "No content found for the specified memory bank files."

        return "\n".join(summary_parts).strip()

    except (InvalidMemoryBankFileNameError, ProjectNotFoundError, ReadError) as e:
        logger.error(f"Error generating memory bank summary: {e}")
        # Re-raise specific errors caught from read_memory_bank_file
        raise e
    except Exception as e:
        logger.error(f"Unexpected error generating summary: {e}")
        raise SummarizationError(f"An unexpected error occurred during summary generation: {e}") from e


def check_memory_bank_status(project_path: Optional[str] = None) -> Dict[str, str]:
    """
    Verifies the existence and basic validity (non-empty) of standard Memory Bank files.

    Args:
        project_path: Path to the project root.

    Returns:
        A dictionary reporting the status of each standard file (e.g.,
        {"productContext.md": "OK", "activeContext.md": "MISSING"}).
        Statuses: "OK", "MISSING", "EMPTY", "ERROR".

    Raises:
        ProjectNotFoundError: If the resolved project path or memory bank directory is invalid/inaccessible.
    """
    logger.info(f"Checking memory bank status for project '{project_path or 'default'}'.")
    status: Dict[str, str] = {}
    try:
        manager = _get_memory_bank_manager(project_path)
        memory_bank_dir = manager.get_memory_bank_path()

        # Check if the memory bank directory itself exists first
        if not os.path.isdir(memory_bank_dir):
             logger.warning(f"Memory bank directory not found at: {memory_bank_dir}. Reporting all files as MISSING.")
             # If dir is missing, all required files are effectively missing
             for file_name in manager.required_files:
                 status[file_name] = "MISSING"
             # Raise ProjectNotFoundError if the *base* project path was likely okay,
             # but the expected subdir is missing. Or just return the MISSING statuses?
             # Design doc implies ProjectNotFoundError only if project_path itself is bad.
             # Let's return the statuses.
             return status
             # Alternative: raise ProjectNotFoundError(f"Memory bank directory not found: {memory_bank_dir}")

        if not manager.required_files:
            logger.info("No required memory bank files configured. Status check complete.")
            return {} # No files to check

        for file_name in manager.required_files:
            # No need to call _validate_file_name as we iterate the valid list
            full_path = os.path.join(memory_bank_dir, file_name)
            try:
                if not os.path.exists(full_path):
                    status[file_name] = "MISSING"
                elif not os.path.isfile(full_path):
                     status[file_name] = "ERROR" # Path exists but isn't a file
                     logger.warning(f"Memory bank path exists but is not a file: {full_path}")
                elif os.path.getsize(full_path) == 0:
                    status[file_name] = "EMPTY"
                else:
                    status[file_name] = "OK"
            except OSError as e:
                logger.error(f"Error checking status for file {full_path}: {e}")
                status[file_name] = "ERROR"

        logger.info(f"Memory bank status check complete: {status}")
        return status
    except ProjectNotFoundError as e:
         # Raised by _get_memory_bank_manager if the base project path is bad
         logger.error(f"Error checking memory bank status: {e}")
         raise e
    except Exception as e:
        # Catch unexpected errors during the process
        logger.error(f"Unexpected error checking memory bank status: {e}")
        # We might not know which file caused it, maybe return a general error?
        # Or return partial results? Let's return what we have + an error marker.
        status["_GENERAL_ERROR_"] = str(e)
        return status


# --- Tool Wrapper Classes ---

class ReadMemoryBankFileTool(BaseTool):
    """Tool wrapper for reading a Memory Bank file."""
    name = "read_memory_bank_file"
    description = "Reads the entire content of a specified Memory Bank file (e.g., productContext.md)."
    # Define args based on the function signature
    args_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "file_name": {"type": "string", "description": "The name of the Memory Bank file (e.g., 'productContext.md')."},
            "project_path": {"type": ["string", "null"], "description": "Absolute or relative path to the project root. Defaults to current project."}
        },
        "required": ["file_name"]
    }

    def run(self, file_name: str, project_path: Optional[str] = None) -> str:
        try:
            return read_memory_bank_file(file_name=file_name, project_path=project_path)
        except MemoryBankToolError as e:
            logger.error(f"Error executing {self.name}: {e}")
            # Re-raise or return an error message string? For now, re-raise.
            raise e # Or return f"Error: {e}"

class WriteMemoryBankFileTool(BaseTool):
    """Tool wrapper for writing to a Memory Bank file (overwrites)."""
    name = "write_memory_bank_file"
    description = "Writes content to a specified Memory Bank file, overwriting existing content. Creates the directory/file if needed."
    args_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "file_name": {"type": "string", "description": "The name of the Memory Bank file to write to."},
            "content": {"type": "string", "description": "The new content to write."},
            "project_path": {"type": ["string", "null"], "description": "Path to the project root."}
        },
        "required": ["file_name", "content"]
    }

    def run(self, file_name: str, content: str, project_path: Optional[str] = None) -> bool:
        try:
            return write_memory_bank_file(file_name=file_name, content=content, project_path=project_path)
        except MemoryBankToolError as e:
            logger.error(f"Error executing {self.name}: {e}")
            raise e # Or return False / error message

class AppendToMemoryBankFileTool(BaseTool):
    """Tool wrapper for appending to a Memory Bank file."""
    name = "append_to_memory_bank_file"
    description = "Appends content to a specified Memory Bank file. Creates the file/directory if needed. Adds a newline before appending if necessary."
    args_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "file_name": {"type": "string", "description": "The name of the Memory Bank file to append to."},
            "content": {"type": "string", "description": "The content to append."},
            "project_path": {"type": ["string", "null"], "description": "Path to the project root."}
        },
        "required": ["file_name", "content"]
    }

    def run(self, file_name: str, content: str, project_path: Optional[str] = None) -> bool:
        try:
            return append_to_memory_bank_file(file_name=file_name, content=content, project_path=project_path)
        except MemoryBankToolError as e:
            logger.error(f"Error executing {self.name}: {e}")
            raise e # Or return False / error message

class GetMemoryBankSummaryTool(BaseTool):
    """Tool wrapper for getting a summary (concatenation) of Memory Bank files."""
    name = "get_memory_bank_summary"
    description = "Retrieves a concise summary by concatenating the content of specified Memory Bank files."
    args_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "file_names": {"type": ["array", "null"], "items": {"type": "string"}, "description": "List of Memory Bank file names to include. Defaults to all if null."},
            "topic": {"type": ["string", "null"], "description": "Specific topic (currently ignored)."},
            "project_path": {"type": ["string", "null"], "description": "Path to the project root."}
        },
        "required": [] # All args are optional
    }

    def run(self, file_names: Optional[List[str]] = None, topic: Optional[str] = None, project_path: Optional[str] = None) -> str:
        try:
            return get_memory_bank_summary(file_names=file_names, topic=topic, project_path=project_path)
        except MemoryBankToolError as e:
            logger.error(f"Error executing {self.name}: {e}")
            raise e # Or return f"Error: {e}"

class CheckMemoryBankStatusTool(BaseTool):
    """Tool wrapper for checking the status of Memory Bank files."""
    name = "check_memory_bank_status"
    description = "Verifies the existence and basic validity (non-empty) of standard Memory Bank files."
    args_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "project_path": {"type": ["string", "null"], "description": "Path to the project root."}
        },
        "required": [] # Optional arg
    }

    def run(self, project_path: Optional[str] = None) -> Dict[str, str]:
        try:
            return check_memory_bank_status(project_path=project_path)
        except MemoryBankToolError as e:
            logger.error(f"Error executing {self.name}: {e}")
            raise e # Or return {"_ERROR_": str(e)}