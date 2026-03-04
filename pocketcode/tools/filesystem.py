#%%
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

# Import BaseTool
from pocketcode.core.interfaces import BaseTool

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Existing Functions (kept for potential internal use or direct calls) ---

def read_file(path: str) -> Optional[str]:
    """
    Reads the content of a file.

    Args:
        path: Relative path to the file.

    Returns:
        The content of the file as a string, or None if the file is not found or an error occurs.
    """
    logger.info(f"Reading file: {path}")
    try:
        file_path = Path(path)
        if not file_path.is_file():
            logger.error(f"File not found or is not a regular file: {path}")
            return None
        content = file_path.read_text(encoding='utf-8')
        logger.info(f"Successfully read {len(content)} characters from {path}")
        return content
    except FileNotFoundError:
        logger.error(f"File not found: {path}")
        return None
    except Exception as e:
        logger.exception(f"An error occurred while reading file '{path}': {e}")
        return None

def write_file(path: str, content: str) -> bool:
    """
    Writes content to a file, overwriting or creating as needed.
    Ensures parent directories exist.

    Args:
        path: Relative path to the file.
        content: The content to write.

    Returns:
        True if the write was successful, False otherwise.
    """
    logger.info(f"Writing to file: {path} ({len(content)} characters)")
    try:
        file_path = Path(path)
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')
        logger.info(f"Successfully wrote to {path}")
        return True
    except Exception as e:
        logger.exception(f"An error occurred while writing to file '{path}': {e}")
        return False

def create_directory(path: str) -> bool:
    """
    Creates a directory, including parent directories if needed.

    Args:
        path: Relative path of the directory to create.

    Returns:
        True if the directory was created or already exists, False otherwise.
    """
    logger.info(f"Creating directory: {path}")
    try:
        dir_path = Path(path)
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Directory ensured: {path}")
        return True
    except Exception as e:
        logger.exception(f"An error occurred while creating directory '{path}': {e}")
        return False

def list_directory(path: str = '.', recursive: bool = False) -> Optional[List[str]]:
    """
    Lists files and directories within a path.

    Args:
        path: Relative path of the directory to list. Defaults to current directory.
        recursive: Whether to list recursively. Defaults to False.

    Returns:
        A list of relative string paths, or None if the path is invalid or an error occurs.
    """
    logger.info(f"Listing directory: {path} (Recursive: {recursive})")
    try:
        dir_path = Path(path)
        if not dir_path.is_dir():
            logger.error(f"Path is not a valid directory: {path}")
            return None

        if recursive:
            # Use rglob for recursive listing
            # Return paths relative to the original 'path' argument for consistency
            items = [str(p.relative_to(Path.cwd())) for p in dir_path.rglob('*')] # Adjust if relative to dir_path is needed
        else:
            # Use iterdir for non-recursive listing
            items = [str(p.name) for p in dir_path.iterdir()]

        logger.info(f"Found {len(items)} items in {path}")
        return items
    except Exception as e:
        logger.exception(f"An error occurred while listing directory '{path}': {e}")
        return None

def glob_files(pattern: str, base_path: str = '.') -> Optional[List[str]]:
    """
    Finds files/directories matching a glob pattern within a base path.

    Args:
        pattern: The glob pattern (e.g., '*.py', '**/*.txt').
        base_path: The base directory to search within. Defaults to current directory.

    Returns:
        A list of relative string paths matching the pattern, or None if an error occurs.
    """
    logger.info(f"Globbing pattern '{pattern}' in base path '{base_path}'")
    try:
        base = Path(base_path)
        if not base.is_dir():
            logger.error(f"Base path is not a valid directory: {base_path}")
            return None

        # Decide between glob and rglob based on pattern
        if '**' in pattern:
            matches = [str(p.relative_to(base)) for p in base.rglob(pattern)]
        else:
            matches = [str(p.relative_to(base)) for p in base.glob(pattern)]

        logger.info(f"Found {len(matches)} matches for pattern '{pattern}' in '{base_path}'")
        return matches
    except Exception as e:
        logger.exception(f"An error occurred while globbing pattern '{pattern}' in '{base_path}': {e}")
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
# --- Example Usage (kept for potential testing) ---
if __name__ == '__main__':
    TEST_DIR = Path("./_test_fs_tools")
    TEST_FILE = TEST_DIR / "test.txt"
    TEST_SUBDIR = TEST_DIR / "subdir"
    TEST_SUBFILE = TEST_SUBDIR / "subtest.log"

    print("--- Testing Filesystem Tools (Functions & Classes) ---")

    # Clean up previous test run if necessary
    import shutil
    if TEST_DIR.exists():
        print(f"Removing existing test directory: {TEST_DIR}")
        shutil.rmtree(TEST_DIR)

    # Test create_directory (function)
    print(f"\n1. Testing create_directory function: {TEST_SUBDIR}")
    success = create_directory(str(TEST_SUBDIR))
    print(f"Create directory success: {success}, Exists: {TEST_SUBDIR.exists()}")

    # Test WriteToFileTool (class)
    print(f"\n2. Testing WriteToFileTool class: {TEST_FILE}")
    write_tool = WriteToFileTool()
    content_to_write = "Hello from WriteToFileTool!\nLine 2."
    result = write_tool.execute(path=str(TEST_FILE), content=content_to_write)
    print(f"Write tool result: {result}, Exists: {TEST_FILE.exists()}")

    print(f"\n3. Testing WriteToFileTool class (subdir): {TEST_SUBFILE}")
    sub_content = "Log entry via tool."
    result = write_tool.execute(path=str(TEST_SUBFILE), content=sub_content)
    print(f"Write subfile tool result: {result}, Exists: {TEST_SUBFILE.exists()}")

    # Test ReadFileTool (class)
    print(f"\n4. Testing ReadFileTool class: {TEST_FILE}")
    read_tool = ReadFileTool()
    result_read = read_tool.execute(path=str(TEST_FILE))
    print(f"Read tool result: {result_read}")
    if result_read.get("success"):
        print(f"Content matches: {result_read.get('content') == content_to_write}")

    # Test ReadFileTool (class, non-existent)
    print(f"\n5. Testing ReadFileTool class (non-existent): non_existent.txt")
    result_read_fail = read_tool.execute(path="non_existent.txt")
    print(f"Read non-existent tool result: {result_read_fail}") # Should show success: False

    # Test ListFilesTool (class, non-recursive)
    print(f"\n6. Testing ListFilesTool class (non-recursive): {TEST_DIR}")
    list_tool = ListFilesTool()
    result_list = list_tool.execute(path=str(TEST_DIR))
    print(f"List tool result: {result_list}")
    if result_list.get("success"):
        print(f"Items: {result_list.get('items')}") # Should contain 'test.txt' and 'subdir'

    # Test ListFilesTool (class, recursive)
    print(f"\n7. Testing ListFilesTool class (recursive): {TEST_DIR}")
    result_rec = list_tool.execute(path=str(TEST_DIR), recursive=True)
    print(f"List recursive tool result: {result_rec}")
    if result_rec.get("success"):
        print(f"Recursive Items: {result_rec.get('items')}") # Should contain paths like 'test.txt', 'subdir/subtest.log'

    # Test glob_files (function)
    print(f"\n8. Testing glob_files function ('**/*.log'): {TEST_DIR}")
    log_files = glob_files("**/*.log", str(TEST_DIR))
    print(f"Glob success: {log_files is not None}")
    if log_files is not None:
        print(f"**/*.log matches: {log_files}")

    print("\n--- Filesystem Tools Test Complete ---")
    # Optional: Clean up test directory
    # print(f"Cleaning up test directory: {TEST_DIR}")
    # shutil.rmtree(TEST_DIR)
