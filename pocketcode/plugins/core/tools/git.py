#%%
import logging
import shlex # Use shlex for safer command construction
from typing import List, Optional, Dict, Any

# Canonical import — uses the core/tools implementation directly, not the shim
from pocketcode.plugins.core.tools.system import execute_shell_command

# Import BaseTool
from pocketcode.core.interfaces import BaseTool

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _run_git_command(command: str) -> Dict[str, Any]:
    """Helper function to run a git command and handle common errors."""
    logger.info(f"Executing Git command: {command}")
    # Use execute_shell_command which should handle execution and capture
    result = execute_shell_command(command)

    # Add a success flag based on return code for convenience
    result["success"] = result.get("returncode") == 0

    if not result["success"] and result.get("returncode") is not None:
        error_message = result.get("stderr", "Unknown Git error").strip()
        if not error_message and result.get("error"):
             error_message = result["error"] # Use execution error if stderr is empty
        logger.error(f"Git command failed: {command}\nReturn Code: {result.get('returncode')}\nError: {error_message}")
        # Specific git non-zero exits that might be informational
        if "nothing to commit" in result.get("stdout", "") or \
           "nothing to commit" in result.get("stderr", "") or \
           "up-to-date" in result.get("stdout", "") or \
           "up-to-date" in result.get("stderr", ""):
             logger.info("Git command returned non-zero, but indicates a clean or up-to-date state.")
             # Consider overriding success=True in these specific cases if needed by the caller
             # For now, keep success=False as returncode was non-zero
    elif result.get("stderr"):
         # Log stderr even on success, as git sometimes uses it for info messages (e.g., pull/push)
         logger.info(f"Git command stderr (non-error): {result['stderr'].strip()}")

    # Ensure stdout and stderr are present, default to empty string if None
    result["stdout"] = result.get("stdout", "")
    result["stderr"] = result.get("stderr", "")

    return result

# --- Specific Git Tool Classes ---

class GitStatusTool(BaseTool):
    """Tool to show the git working tree status."""

    @property
    def name(self) -> str:
        return "git_status"

    @property
    def description(self) -> str:
        return "Shows the git working tree status using the porcelain format for easier parsing."

    @property
    def schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {}, # No parameters needed
            "required": []
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        command = "git status --porcelain"
        result = _run_git_command(command)
        # Return the full result dictionary
        return result

class GitDiffTool(BaseTool):
    """Tool to show git changes (diff)."""

    @property
    def name(self) -> str:
        return "git_diff"

    @property
    def description(self) -> str:
        return "Shows git changes (diff). Can show staged changes or diff a specific file."

    @property
    def schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Optional relative path to a specific file to diff."
                },
                "staged": {
                    "type": "boolean",
                    "description": "Show staged changes instead of working directory changes.",
                    "default": False
                }
            },
            "required": []
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        file_path = kwargs.get("file_path")
        staged = kwargs.get("staged", False)

        command_parts = ["git", "diff"]
        if staged:
            command_parts.append("--staged")
        if file_path:
            # Add '--' to prevent misinterpretation of file paths starting with '-'
            command_parts.append("--")
            command_parts.append(file_path) # shlex.quote will handle spaces/special chars

        command = shlex.join(command_parts)
        result = _run_git_command(command)
        return result

class GitAddTool(BaseTool):
    """Tool to stage changes in specified files for the next commit."""

    @property
    def name(self) -> str:
        return "git_add"

    @property
    def description(self) -> str:
        return "Stages changes in specified files for the next commit. Use '.' to stage all changes."

    @property
    def schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "List of relative file paths to stage. Use '.' to stage all."
                }
            },
            "required": ["files"]
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        files = kwargs.get("files")
        if not files:
            logger.error(f"{self.name}: Missing or empty required argument 'files'.")
            return {"success": False, "error": "Missing or empty required argument 'files'.", "stdout": "", "stderr": ""}

        # Ensure files is a list
        if not isinstance(files, list):
             logger.error(f"{self.name}: Argument 'files' must be a list.")
             return {"success": False, "error": "Argument 'files' must be a list.", "stdout": "", "stderr": ""}

        command_parts = ["git", "add", "--"] # Use '--' to separate file paths
        command_parts.extend(files) # shlex.join will handle quoting

        command = shlex.join(command_parts)
        result = _run_git_command(command)
        return result

class GitCommitTool(BaseTool):
    """Tool to commit staged changes to the git repository."""

    @property
    def name(self) -> str:
        return "git_commit"

    @property
    def description(self) -> str:
        return "Commits staged changes to the git repository with the provided message."

    @property
    def schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The commit message."
                }
            },
            "required": ["message"]
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        message = kwargs.get("message")
        if not message:
            logger.error(f"{self.name}: Missing or empty required argument 'message'.")
            return {"success": False, "error": "Missing or empty required argument 'message'.", "stdout": "", "stderr": ""}

        # Use -m for the message. shlex.join handles quoting.
        command_parts = ["git", "commit", "-m", message]
        command = shlex.join(command_parts)

        result = _run_git_command(command)

        # Check for "nothing to commit" specifically, as it returns non-zero but isn't a failure
        if result.get("returncode") != 0 and \
           ("nothing to commit" in result.get("stdout", "") or \
            "nothing to commit" in result.get("stderr", "")):
            logger.info("git_commit: Nothing to commit, working tree clean.")
            result["stdout"] += "\n(Nothing to commit)" # Add clarification

        return result


class GitPullTool(BaseTool):
    """Tool to fetch from and integrate with another repository or a local branch."""

    @property
    def name(self) -> str:
        return "git_pull"

    @property
    def description(self) -> str:
        return "Fetches from and integrates with another repository or a local branch (e.g., 'git pull origin main')."

    @property
    def schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "remote": {
                    "type": "string",
                    "description": "The remote repository name.",
                    "default": "origin"
                },
                "branch": {
                    "type": "string",
                    "description": "The branch name to pull. Defaults to the current branch's configured upstream."
                }
            },
            "required": [] # remote defaults, branch is optional
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        remote = kwargs.get("remote", "origin")
        branch = kwargs.get("branch")

        command_parts = ["git", "pull", remote]
        if branch:
            command_parts.append(branch)

        command = shlex.join(command_parts)
        result = _run_git_command(command)
        # Pull often prints info to stderr, _run_git_command logs it but doesn't treat as error
        return result

class GitPushTool(BaseTool):
    """Tool to update remote refs using local refs."""

    @property
    def name(self) -> str:
        return "git_push"

    @property
    def description(self) -> str:
        return "Updates remote refs using local refs (e.g., 'git push origin main')."

    @property
    def schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "remote": {
                    "type": "string",
                    "description": "The remote repository name.",
                    "default": "origin"
                },
                "branch": {
                    "type": "string",
                    "description": "The local branch name to push. Defaults to the current branch."
                }
            },
            "required": [] # remote defaults, branch is optional (pushes current)
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        remote = kwargs.get("remote", "origin")
        branch = kwargs.get("branch")

        command_parts = ["git", "push", remote]
        if branch:
            command_parts.append(branch)

        command = shlex.join(command_parts)
        result = _run_git_command(command)
        return result
