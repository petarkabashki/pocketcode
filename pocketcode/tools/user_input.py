from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from pocketcode.core.interfaces import BaseTool

logger = logging.getLogger(__name__)

_YES_VALUES = {"y", "yes", "true", "1", "on"}
_NO_VALUES = {"n", "no", "false", "0", "off"}


def _resolve_user_input_handler(shared_store: Dict[str, Any] | None) -> Callable[[str], str] | None:
    if not isinstance(shared_store, dict):
        return None
    handler = shared_store.get("user_input_handler")
    return handler if callable(handler) else None


def ask_user_input(
    prompt: str,
    *,
    default: str = "",
    allow_empty: bool = False,
    shared_store: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    handler = _resolve_user_input_handler(shared_store)
    prompt_text = prompt.strip() or "Input"
    suffix = f" [{default}]" if default else ""

    while True:
        try:
            if handler:
                raw = handler(f"{prompt_text}{suffix}: ")
            else:
                raw = input(f"{prompt_text}{suffix}: ")
        except EOFError:
            return {"success": False, "error": "Input stream closed while waiting for user input."}
        except KeyboardInterrupt:
            return {"success": False, "error": "Input interrupted by user."}

        value = raw.strip()
        if value:
            return {"success": True, "value": value}

        if default:
            return {"success": True, "value": default}

        if allow_empty:
            return {"success": True, "value": ""}

        logger.info("Input cannot be empty. Prompting again.")


def ask_user_confirmation(
    prompt: str,
    *,
    default: str = "no",
    shared_store: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_default = default.strip().lower()
    if normalized_default not in _YES_VALUES and normalized_default not in _NO_VALUES:
        normalized_default = "no"

    default_hint = "Y/n" if normalized_default in _YES_VALUES else "y/N"
    response = ask_user_input(
        f"{prompt.strip()} ({default_hint})",
        default=normalized_default,
        allow_empty=False,
        shared_store=shared_store,
    )
    if not response.get("success"):
        return response

    value = str(response.get("value", "")).strip().lower()
    if value in _YES_VALUES:
        return {"success": True, "approved": True, "response": value}
    if value in _NO_VALUES:
        return {"success": True, "approved": False, "response": value}
    return {"success": False, "error": f"Unrecognized confirmation response: '{value}'."}


class AskUserInputTool(BaseTool):
    @property
    def name(self) -> str:
        return "ask_user_input"

    @property
    def description(self) -> str:
        return "Prompts the local CLI user for free-form input."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Prompt shown to the user."},
                "default": {"type": "string", "description": "Default value for empty responses."},
                "allow_empty": {"type": "boolean", "description": "Allow empty responses.", "default": False},
            },
            "required": ["prompt"],
        }

    def execute(self, **kwargs) -> Any:
        return ask_user_input(
            prompt=str(kwargs.get("prompt", "")),
            default=str(kwargs.get("default", "")),
            allow_empty=bool(kwargs.get("allow_empty", False)),
            shared_store=kwargs.get("shared_store"),
        )


class ConfirmUserInputTool(BaseTool):
    @property
    def name(self) -> str:
        return "confirm_user_input"

    @property
    def description(self) -> str:
        return "Prompts the local CLI user for yes/no confirmation."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Confirmation question shown to the user."},
                "default": {"type": "string", "description": "Default answer for empty input: yes or no.", "default": "no"},
            },
            "required": ["prompt"],
        }

    def execute(self, **kwargs) -> Any:
        return ask_user_confirmation(
            prompt=str(kwargs.get("prompt", "")),
            default=str(kwargs.get("default", "no")),
            shared_store=kwargs.get("shared_store"),
        )
