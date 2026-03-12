#%%
import os
import subprocess
import logging
from typing import Dict, Any

# Import BaseTool
from pocketcode.core.interfaces import BaseTool

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Existing Function ---

def execute_shell_command(command: str) -> Dict[str, Any]:
    """
    Executes a shell command and returns its stdout, stderr, and return code.

    Args:
        command: The shell command to execute.

    Returns:
        A dictionary containing:
        - 'stdout': The standard output of the command (decoded string).
        - 'stderr': The standard error of the command (decoded string).
        - 'returncode': The exit code of the command.
        - 'error': An error message if the command execution failed, None otherwise.
    """
    logger.info(f"Executing shell command: {command}")
    result = {
        "stdout": "",
        "stderr": "",
        "returncode": None,
        "error": None
    }
    try:
        # Using shell=True can be a security risk if the command string is constructed
        # from external input. Ensure the command is safe or properly sanitized.
        # For internal tools like git wrappers, it's generally acceptable if inputs are controlled.
        process = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=False # Don't raise exception on non-zero exit code, capture it instead
        )
        result["stdout"] = process.stdout
        result["stderr"] = process.stderr
        result["returncode"] = process.returncode
        if process.returncode != 0:
            logger.warning(f"Command '{command}' exited with non-zero status {process.returncode}")
            logger.warning(f"Stderr: {process.stderr.strip()}")
        else:
            logger.info(f"Command '{command}' executed successfully.")

    except FileNotFoundError:
        err_msg = f"Error: Command or shell not found for executing: {command}"
        logger.error(err_msg)
        result["stderr"] = err_msg
        result["error"] = err_msg
        result["returncode"] = -1 # Indicate execution failure
    except Exception as e:
        err_msg = f"An unexpected error occurred while executing command '{command}': {e}"
        logger.exception(err_msg) # Log full traceback
        result["stderr"] = str(e)
        result["error"] = err_msg
        result["returncode"] = -1 # Indicate execution failure

    return result

# --- Tool Class ---

class ExecuteCommandTool(BaseTool):
    """Tool to execute shell commands."""

    @property
    def name(self) -> str:
        return "execute_command"

    @property
    def description(self) -> str:
        return "Executes a shell command and returns its output (stdout, stderr) and return code."

    @property
    def execution_mode(self) -> str:
        return "managed_subprocess"

    @property
    def schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute."}
                # Add 'cwd' or other options if needed later
            },
            "required": ["command"]
        }

    def spawn_subprocess(self, **kwargs) -> Any:
        command = kwargs.get("command")
        if command is None:
            raise ValueError("Missing required argument 'command'.")

        return subprocess.Popen(
            str(command),
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=os.name != "nt",
        )

    def handle_subprocess_result(self, *, returncode: int, stdout: str, stderr: str, **kwargs) -> Any:
        result = {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
            "error": None,
            "success": returncode == 0,
        }
        if returncode != 0:
            result["error"] = stderr.strip() or f"Command exited with status {returncode}."
        return result

    def execute(self, **kwargs) -> Any:
        command = kwargs.get("command")
        if command is None:
            logger.error(f"{self.name}: Missing required argument 'command'.")
            return {"success": False, "error": "Missing required argument 'command'."}

        # The execute_shell_command function already returns a dictionary
        # with stdout, stderr, returncode, and error.
        # We can return this directly, perhaps adding a 'success' flag based on returncode.
        result = execute_shell_command(command=command)

        # Add a simple success flag for convenience
        result["success"] = result["returncode"] == 0

        return result


TOOLS = {
    "execute_command": ExecuteCommandTool,
}


# --- Example Usage (kept for potential testing) ---
if __name__ == '__main__':
    print("--- Testing System Tools (Function & Class) ---")

    # Test execute_shell_command function
    print("\n1. Testing execute_shell_command function (ls -la):")
    ls_result = execute_shell_command("ls -la")
    print(f"Function Result: {ls_result}")

    # Test ExecuteCommandTool class
    print("\n2. Testing ExecuteCommandTool class (echo Hello):")
    cmd_tool = ExecuteCommandTool()
    echo_result = cmd_tool.execute(command="echo Hello Tool")
    print(f"Tool Result: {echo_result}")

    # Test ExecuteCommandTool class (non-zero exit)
    print("\n3. Testing ExecuteCommandTool class (ls non_existent_file):")
    ls_invalid_result = cmd_tool.execute(command="ls non_existent_file")
    print(f"Tool Result (non-zero): {ls_invalid_result}")

    # Test ExecuteCommandTool class (command not found)
    print("\n4. Testing ExecuteCommandTool class (invalidcommand):")
    invalid_cmd_result = cmd_tool.execute(command="invalidcommandthatdoesnotexist")
    print(f"Tool Result (not found): {invalid_cmd_result}")

    print("\n--- System Tools Test Complete ---")
