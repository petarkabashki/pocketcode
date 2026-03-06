from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from pocketcode.cli.user_interaction import request_interaction_from_console
from pocketcode.core.interfaces import BaseTool
from pocketcode.core.user_interaction import normalize_interaction_request

logger = logging.getLogger(__name__)

_YES_VALUES = {"y", "yes", "true", "1", "on"}
_NO_VALUES = {"n", "no", "false", "0", "off"}


def _resolve_interaction_handler(shared_store: Dict[str, Any] | None) -> Callable[[Dict[str, Any]], Dict[str, Any]] | None:
    if not isinstance(shared_store, dict):
        return None
    handler = shared_store.get("interaction_handler")
    if callable(handler):
        return handler

    legacy_handler = shared_store.get("user_input_handler")
    if not callable(legacy_handler):
        return None

    def _wrapped(request: Dict[str, Any]) -> Dict[str, Any]:
        interaction = normalize_interaction_request(request)
        if interaction.kind != "text":
            raise RuntimeError("Legacy user_input_handler only supports free-form text prompts.")
        value = legacy_handler(interaction.prompt)
        return {"kind": "text", "value": value, "raw_input": value}

    return _wrapped


def _request_interaction(
    request: Dict[str, Any],
    *,
    shared_store: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    handler = _resolve_interaction_handler(shared_store)
    if handler is not None:
        return handler(request)
    return request_interaction_from_console(request)


def _selection_schema() -> Dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "anyOf": [
                {"type": "string"},
                {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                        "value": {},
                        "description": {"type": "string"},
                    },
                },
            ]
        },
    }


def ask_user_input(
    prompt: str,
    *,
    default: str = "",
    allow_empty: bool = False,
    shared_store: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    try:
        response = _request_interaction(
            {
                "kind": "text",
                "prompt": prompt.strip() or "Input",
                "default": default,
                "allow_empty": allow_empty,
            },
            shared_store=shared_store,
        )
    except EOFError:
        return {"success": False, "error": "Input stream closed while waiting for user input."}
    except KeyboardInterrupt:
        return {"success": False, "error": "Input interrupted by user."}
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    return {"success": True, "value": response.get("value", ""), "response": response}


def ask_user_confirmation(
    prompt: str,
    *,
    default: str = "no",
    shared_store: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_default = default.strip().lower()
    if normalized_default not in _YES_VALUES and normalized_default not in _NO_VALUES:
        normalized_default = "no"

    try:
        response = _request_interaction(
            {
                "kind": "buttons",
                "prompt": prompt.strip() or "Confirmation required",
                "default": normalized_default,
                "options": [
                    {"id": "yes", "label": "Yes", "value": "yes"},
                    {"id": "no", "label": "No", "value": "no"},
                ],
            },
            shared_store=shared_store,
        )
    except EOFError:
        return {"success": False, "error": "Input stream closed while waiting for user input."}
    except KeyboardInterrupt:
        return {"success": False, "error": "Input interrupted by user."}
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    value = str(response.get("value", "")).strip().lower()
    if value in _YES_VALUES:
        return {"success": True, "approved": True, "response": value, "interaction": response}
    if value in _NO_VALUES:
        return {"success": True, "approved": False, "response": value, "interaction": response}
    return {"success": False, "error": f"Unrecognized confirmation response: '{value}'."}


def ask_user_buttons(
    prompt: str,
    *,
    options: list[Any],
    default: str = "",
    shared_store: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    try:
        response = _request_interaction(
            {
                "kind": "buttons",
                "prompt": prompt.strip() or "Choose an action",
                "options": options,
                "default": default,
            },
            shared_store=shared_store,
        )
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    return {
        "success": True,
        "value": response.get("value"),
        "selected_options": response.get("selected_options", []),
        "response": response,
    }


def ask_user_radio_group(
    prompt: str,
    *,
    options: list[Any],
    default: str = "",
    shared_store: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    try:
        response = _request_interaction(
            {
                "kind": "radio",
                "prompt": prompt.strip() or "Choose one option",
                "options": options,
                "default": default,
            },
            shared_store=shared_store,
        )
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    return {
        "success": True,
        "value": response.get("value"),
        "selected_options": response.get("selected_options", []),
        "response": response,
    }


def ask_user_checklist(
    prompt: str,
    *,
    options: list[Any],
    default: list[Any] | None = None,
    min_selected: int | None = None,
    max_selected: int | None = None,
    shared_store: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    try:
        response = _request_interaction(
            {
                "kind": "checklist",
                "prompt": prompt.strip() or "Select one or more options",
                "options": options,
                "default": default or [],
                "min_selected": min_selected,
                "max_selected": max_selected,
            },
            shared_store=shared_store,
        )
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    values = response.get("values") or response.get("value") or []
    return {
        "success": True,
        "values": list(values),
        "selected_options": response.get("selected_options", []),
        "response": response,
    }


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


class AskUserButtonsTool(BaseTool):
    @property
    def name(self) -> str:
        return "ask_user_buttons"

    @property
    def description(self) -> str:
        return "Prompts the local CLI user with button-style choices."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Prompt shown to the user."},
                "options": _selection_schema(),
                "default": {"type": "string", "description": "Default option id, label, or value."},
            },
            "required": ["prompt", "options"],
        }

    def execute(self, **kwargs) -> Any:
        return ask_user_buttons(
            prompt=str(kwargs.get("prompt", "")),
            options=list(kwargs.get("options") or []),
            default=str(kwargs.get("default", "")),
            shared_store=kwargs.get("shared_store"),
        )


class AskUserRadioGroupTool(BaseTool):
    @property
    def name(self) -> str:
        return "ask_user_radio_group"

    @property
    def description(self) -> str:
        return "Prompts the local CLI user with a radio-group style single-choice selector."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Prompt shown to the user."},
                "options": _selection_schema(),
                "default": {"type": "string", "description": "Default option id, label, or value."},
            },
            "required": ["prompt", "options"],
        }

    def execute(self, **kwargs) -> Any:
        return ask_user_radio_group(
            prompt=str(kwargs.get("prompt", "")),
            options=list(kwargs.get("options") or []),
            default=str(kwargs.get("default", "")),
            shared_store=kwargs.get("shared_store"),
        )


class AskUserChecklistTool(BaseTool):
    @property
    def name(self) -> str:
        return "ask_user_checklist"

    @property
    def description(self) -> str:
        return "Prompts the local CLI user with a checklist for multi-select input."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Prompt shown to the user."},
                "options": _selection_schema(),
                "default": {"type": "array", "items": {"type": "string"}, "description": "Default selected option ids, labels, or values."},
                "min_selected": {"type": "integer", "description": "Minimum number of required selections."},
                "max_selected": {"type": "integer", "description": "Maximum number of allowed selections."},
            },
            "required": ["prompt", "options"],
        }

    def execute(self, **kwargs) -> Any:
        return ask_user_checklist(
            prompt=str(kwargs.get("prompt", "")),
            options=list(kwargs.get("options") or []),
            default=list(kwargs.get("default") or []),
            min_selected=kwargs.get("min_selected"),
            max_selected=kwargs.get("max_selected"),
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
