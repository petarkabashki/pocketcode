from __future__ import annotations

import logging
import shlex
from typing import Any, Dict

from pocketcode.core.interfaces import BaseTool
from pocketcode.core_tools.system import execute_shell_command

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _run_git_command(command: str) -> Dict[str, Any]:
    logger.info(f"Executing Git command: {command}")
    result = execute_shell_command(command)
    result["success"] = result.get("returncode") == 0

    if not result["success"] and result.get("returncode") is not None:
        error_message = result.get("stderr", "Unknown Git error").strip()
        if not error_message and result.get("error"):
            error_message = result["error"]
        logger.error(
            f"Git command failed: {command}\nReturn Code: {result.get('returncode')}\nError: {error_message}"
        )
        if "nothing to commit" in result.get("stdout", "") or \
           "nothing to commit" in result.get("stderr", "") or \
           "up-to-date" in result.get("stdout", "") or \
           "up-to-date" in result.get("stderr", ""):
            logger.info("Git command returned non-zero, but indicates a clean or up-to-date state.")
    elif result.get("stderr"):
        logger.info(f"Git command stderr (non-error): {result['stderr'].strip()}")

    result["stdout"] = result.get("stdout", "")
    result["stderr"] = result.get("stderr", "")
    return result


class GitStatusTool(BaseTool):
    @property
    def name(self) -> str:
        return "git_status"

    @property
    def description(self) -> str:
        return "Shows the git working tree status using the porcelain format for easier parsing."

    @property
    def schema(self) -> Dict:
        return {"type": "object", "properties": {}, "required": []}

    def execute(self, **kwargs) -> Dict[str, Any]:
        return _run_git_command("git status --porcelain")


class GitDiffTool(BaseTool):
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
                    "description": "Optional relative path to a specific file to diff.",
                },
                "staged": {
                    "type": "boolean",
                    "description": "Show staged changes instead of working directory changes.",
                    "default": False,
                },
            },
            "required": [],
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        file_path = kwargs.get("file_path")
        staged = kwargs.get("staged", False)
        command_parts = ["git", "diff"]
        if staged:
            command_parts.append("--staged")
        if file_path:
            command_parts.append("--")
            command_parts.append(file_path)
        return _run_git_command(shlex.join(command_parts))


class GitAddTool(BaseTool):
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
                    "items": {"type": "string"},
                    "description": "List of relative file paths to stage. Use '.' to stage all.",
                }
            },
            "required": ["files"],
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        files = kwargs.get("files")
        if not files:
            logger.error(f"{self.name}: Missing or empty required argument 'files'.")
            return {"success": False, "error": "Missing or empty required argument 'files'.", "stdout": "", "stderr": ""}
        if not isinstance(files, list):
            logger.error(f"{self.name}: Argument 'files' must be a list.")
            return {"success": False, "error": "Argument 'files' must be a list.", "stdout": "", "stderr": ""}

        return _run_git_command(shlex.join(["git", "add", "--", *files]))


class GitCommitTool(BaseTool):
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
                    "description": "The commit message.",
                }
            },
            "required": ["message"],
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        message = kwargs.get("message")
        if not message:
            logger.error(f"{self.name}: Missing or empty required argument 'message'.")
            return {"success": False, "error": "Missing or empty required argument 'message'.", "stdout": "", "stderr": ""}

        result = _run_git_command(shlex.join(["git", "commit", "-m", message]))
        if result.get("returncode") != 0 and (
            "nothing to commit" in result.get("stdout", "") or "nothing to commit" in result.get("stderr", "")
        ):
            logger.info("git_commit: Nothing to commit, working tree clean.")
            result["stdout"] += "\n(Nothing to commit)"
        return result


class GitPullTool(BaseTool):
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
                    "default": "origin",
                },
                "branch": {
                    "type": "string",
                    "description": "The branch name to pull. Defaults to the current branch's configured upstream.",
                },
            },
            "required": [],
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        remote = kwargs.get("remote", "origin")
        branch = kwargs.get("branch")
        command_parts = ["git", "pull", remote]
        if branch:
            command_parts.append(branch)
        return _run_git_command(shlex.join(command_parts))


class GitPushTool(BaseTool):
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
                    "default": "origin",
                },
                "branch": {
                    "type": "string",
                    "description": "The local branch name to push. Defaults to the current branch.",
                },
            },
            "required": [],
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        remote = kwargs.get("remote", "origin")
        branch = kwargs.get("branch")
        command_parts = ["git", "push", remote]
        if branch:
            command_parts.append(branch)
        return _run_git_command(shlex.join(command_parts))


TOOLS = {
    "git_status": GitStatusTool,
    "git_diff": GitDiffTool,
    "git_add": GitAddTool,
    "git_commit": GitCommitTool,
    "git_pull": GitPullTool,
    "git_push": GitPushTool,
}


__all__ = [
    "GitStatusTool",
    "GitDiffTool",
    "GitAddTool",
    "GitCommitTool",
    "GitPullTool",
    "GitPushTool",
    "_run_git_command",
]
