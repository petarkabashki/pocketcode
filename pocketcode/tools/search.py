#%%
import logging
import json
import shutil
from typing import Optional, Dict, Any

# Import BaseTool
from pocketcode.core.interfaces import BaseTool
# Assuming system.py is in the same directory
from .system import execute_shell_command

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cache the result of checking for rg
_RG_PATH = shutil.which('rg')

def is_ripgrep_installed() -> bool:
    """Checks if ripgrep (rg) is installed and executable."""
    if _RG_PATH:
        logger.info(f"ripgrep found at: {_RG_PATH}")
        return True
    else:
        logger.error("ripgrep (rg) command not found in PATH. Please install ripgrep.")
        return False

# --- Existing Function ---

def search_code_func( # Renamed slightly to avoid conflict with class name if needed later
    query: str,
    path: str = '.',
    file_pattern: Optional[str] = None,
    case_sensitive: bool = False,
    context_lines: int = 2
) -> Optional[str]:
    """
    Searches code using ripgrep (rg). Requires 'rg' to be installed.

    Args:
        query: The regex pattern to search for.
        path: The directory or file path to search within. Defaults to '.'.
        file_pattern: Glob pattern to filter files (e.g., '*.py'). Optional.
        case_sensitive: Perform a case-sensitive search. Defaults to False.
        context_lines: Number of context lines to show before/after matches. Defaults to 2.

    Returns:
        The raw JSON output string from ripgrep if successful (even if no matches),
        or a JSON string representing an error if ripgrep is not installed or a
        significant error occurs during execution.
        Note: An empty result set from rg is considered success and will return a string
        representing empty JSON output or similar, not None.
    """
    logger.info(f"Searching for query '{query}' in path '{path}' (Pattern: {file_pattern}, CaseSensitive: {case_sensitive}, Context: {context_lines})")

    if not is_ripgrep_installed():
        # Return a structured error if rg is not found
        return json.dumps({"success": False, "error": "ripgrep (rg) command not found in PATH."})


    # Construct the rg command
    # Use --json for structured output
    # Use --heading to include filenames in the output structure
    # Use --line-number for line numbers
    # Use --stats to get summary statistics if needed (optional)
    command_parts = [
        _RG_PATH, # Use the cached full path
        "--json",
        "--heading",
        "--line-number",
        f"-C {context_lines}"
    ]

    if file_pattern:
        # Basic sanitization for glob pattern
        safe_file_pattern = file_pattern.replace("'", "\\'")
        command_parts.append(f"-g '{safe_file_pattern}'") # Use -g for glob pattern

    if case_sensitive:
        command_parts.append("-s") # Case-sensitive search
    else:
        command_parts.append("-i") # Case-insensitive search (default often, but explicit)

    # Add query and path - ensure they are properly handled by shell execution
    # Basic sanitization for query and path
    safe_query = query.replace("'", "'\\''") # Escape single quotes for shell
    safe_path = path.replace("'", "'\\''")
    command_parts.append(f"'{safe_query}'")
    command_parts.append(f"'{safe_path}'")

    command = " ".join(command_parts)

    result = execute_shell_command(command)

    # Check for execution errors first
    if result["returncode"] is None or result["error"]:
        error_msg = f"Failed to execute ripgrep command. Error: {result.get('error', 'Unknown execution error')}"
        logger.error(error_msg)
        # Return structured error
        return json.dumps({"success": False, "error": error_msg})


    # Check ripgrep's return code
    # 0 = Matches found
    # 1 = No matches found (this is considered success in terms of execution)
    # >1 = Error occurred within ripgrep
    if result["returncode"] > 1:
        error_msg = f"ripgrep command failed with return code {result['returncode']}. Stderr: {result.get('stderr', '').strip()}"
        logger.error(error_msg)
        # Return structured error
        return json.dumps({"success": False, "error": error_msg, "stderr": result.get('stderr', '')})


    # If return code is 0 or 1, the command executed successfully (or found no matches)
    # Return the raw stdout which should contain the JSON output (or be empty/minimal if no matches)
    logger.info(f"ripgrep command finished with return code {result['returncode']}.")
    # Return raw JSON string output from rg
    return result.get("stdout", "")


# --- Tool Class ---

class SearchCodeTool(BaseTool): # Renamed class
    """Tool to search for text/regex patterns in files using ripgrep."""

    @property
    def name(self) -> str:
        return "search_code" # Updated name

    @property
    def description(self) -> str:
        # Updated description slightly to reflect the name change and JSON focus
        return "Searches code using ripgrep (rg) for a regex pattern. Requires 'rg' to be installed. Returns results as newline-delimited JSON."

    @property
    def schema(self) -> Dict:
        # Schema matches the plan and previous implementation
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The regex pattern to search for."},
                "path": {"type": "string", "description": "Directory or file path to search within.", "default": "."},
                "file_pattern": {"type": "string", "description": "Glob pattern to filter files (e.g., '*.py')."},
                "case_sensitive": {"type": "boolean", "description": "Perform case-sensitive search.", "default": False},
                "context_lines": {"type": "integer", "description": "Number of context lines around matches.", "default": 2}
            },
            "required": ["query"]
        }

    def execute(self, **kwargs) -> Any:
        query = kwargs.get("query")
        if query is None:
            logger.error(f"{self.name}: Missing required argument 'query'.")
            return {"success": False, "error": "Missing required argument 'query'."}

        path = kwargs.get("path", ".")
        file_pattern = kwargs.get("file_pattern") # Optional
        case_sensitive = kwargs.get("case_sensitive", False)
        context_lines = kwargs.get("context_lines", 2)

        # Call the search function
        json_output_str = search_code_func( # Use renamed function
            query=query,
            path=path,
            file_pattern=file_pattern,
            case_sensitive=case_sensitive,
            context_lines=context_lines
        )

        # Attempt to parse the JSON output from search_code_func
        try:
            # Handle potentially empty string for no matches (rg return code 1)
            if not json_output_str and isinstance(json_output_str, str):
                 # Return success with empty results if rg found nothing (return code 1)
                 # Check if rg is installed first, as that's a different failure case
                 if not is_ripgrep_installed():
                      return {"success": False, "error": "ripgrep (rg) command not found in PATH."}
                 else:
                      return {"success": True, "results": [], "message": "No matches found."}

            # Process the JSON lines (rg --json outputs JSON objects separated by newlines)
            results = []
            for line in json_output_str.strip().split('\n'):
                if line: # Avoid empty lines
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError as json_err:
                        logger.warning(f"Failed to decode JSON line from rg output: {json_err}. Line: '{line}'")
                        # Decide whether to return partial results or fail
                        # For now, log warning and continue processing other lines

            # Check if the first result indicates an error reported by search_code_func itself
            # This handles cases like rg not found or execution errors returned as JSON
            if results and isinstance(results[0], dict) and results[0].get("success") is False:
                return results[0] # Return the error structure from search_code_func

            return {"success": True, "results": results}

        except json.JSONDecodeError as e:
            # This case might happen if rg output is not valid JSON for some reason
            # (though search_code_func tries to return valid JSON errors)
            logger.error(f"Failed to parse the JSON output from ripgrep: {e}")
            logger.debug(f"Raw rg output:\n{json_output_str}")
            return {"success": False, "error": "Failed to parse ripgrep JSON output.", "raw_output": json_output_str}
        except Exception as e:
            logger.exception(f"An unexpected error occurred processing search results: {e}")
            return {"success": False, "error": f"An unexpected error occurred: {e}"}


# --- Example Usage (kept for potential testing) ---
if __name__ == '__main__':
    from pathlib import Path
    import shutil

    TEST_SEARCH_DIR = Path("./_test_search_tools")
    TEST_FILE_PY = TEST_SEARCH_DIR / "test_script.py"
    TEST_FILE_TXT = TEST_SEARCH_DIR / "notes.txt"
    SUBDIR = TEST_SEARCH_DIR / "subdir"
    TEST_SUBFILE_PY = SUBDIR / "sub_script.py"

    print("--- Testing Search Tool (Function & Class) ---")

    # Setup test directory
    if TEST_SEARCH_DIR.exists():
        shutil.rmtree(TEST_SEARCH_DIR)
    SUBDIR.mkdir(parents=True, exist_ok=True)
    TEST_FILE_PY.write_text("def hello_world():\n    print('Hello, Python world!')\n\nclass MyClass:\n    pass\n")
    TEST_FILE_TXT.write_text("Some important notes.\nAnother line about Python.\nCase matters here: python vs Python.")
    TEST_SUBFILE_PY.write_text("import os\ndef process_data():\n    # TODO: Implement data processing\n    data = 'sample'\n    return data\n")

    if is_ripgrep_installed():
        print("\n1. Testing SearchCodeTool class (simple case-insensitive): 'python'")
        search_tool = SearchCodeTool() # Use new class name
        result1 = search_tool.execute(query="python", path=str(TEST_SEARCH_DIR))
        print(f"Tool Result 1: {json.dumps(result1, indent=2)}")

        print("\n2. Testing SearchCodeTool class (case-sensitive): 'Python'")
        result2 = search_tool.execute(query="Python", path=str(TEST_SEARCH_DIR), case_sensitive=True)
        print(f"Tool Result 2: {json.dumps(result2, indent=2)}")

        print("\n3. Testing SearchCodeTool class (file pattern): '*.py', query 'class'")
        result3 = search_tool.execute(query="class", path=str(TEST_SEARCH_DIR), file_pattern="*.py")
        print(f"Tool Result 3: {json.dumps(result3, indent=2)}")

        print("\n4. Testing SearchCodeTool class (no matches): 'nonexistentquery'")
        result4 = search_tool.execute(query="nonexistentquery", path=str(TEST_SEARCH_DIR))
        print(f"Tool Result 4: {json.dumps(result4, indent=2)}") # Should show success: True, results: []

        print("\n5. Testing SearchCodeTool class (specific file): 'TODO', path=subdir/sub_script.py")
        result5 = search_tool.execute(query="TODO", path=str(TEST_SUBFILE_PY))
        print(f"Tool Result 5: {json.dumps(result5, indent=2)}")

    else:
        print("\nSkipping tests because ripgrep (rg) is not installed or not found in PATH.")

    print("\n--- Search Tool Test Complete ---")
    # Optional: Clean up test directory
    # print(f"Cleaning up test directory: {TEST_SEARCH_DIR}")
    # shutil.rmtree(TEST_SEARCH_DIR)