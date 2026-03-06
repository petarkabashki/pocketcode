from __future__ import annotations

import importlib
import inspect
import logging
from typing import Any, Dict, List

from pocketcode.core.interfaces import BaseTool
from pocketcode.tools.user_input import ConfirmUserInputTool

logger = logging.getLogger(__name__)

VALID_CONFIRMATION_POLICIES = {"allow", "confirm", "deny"}


class ToolRuntime:
    def __init__(
        self,
        tools: Dict[str, Any],
        require_confirmation: bool = True,
        auto_approved_tools: List[str] | None = None,
        confirmation_config: Dict[str, Any] | None = None,
    ):
        self._tools = tools
        self._require_confirmation = require_confirmation
        self._auto_approved_tools = set(auto_approved_tools or [])
        self._confirmation_config = self._normalize_confirmation_config(
            config=confirmation_config or {},
            require_confirmation=require_confirmation,
            auto_approved_tools=self._auto_approved_tools,
        )
        self._confirm_tool = ConfirmUserInputTool()

    @property
    def tools(self) -> Dict[str, Any]:
        return self._tools

    def describe_tools(self, tool_names: List[str]) -> List[Dict[str, Any]]:
        descriptions: List[Dict[str, Any]] = []
        for tool_name in tool_names:
            descriptions.append(self.describe_tool(tool_name))
        return descriptions

    def describe_tool(self, tool_name: str) -> Dict[str, Any]:
        tool_impl = self._resolve_tool(tool_name)

        description = ""
        schema: Dict[str, Any] = {"type": "object", "properties": {}}

        if isinstance(tool_impl, type) and issubclass(tool_impl, BaseTool):
            instance = tool_impl()
            description = instance.description
            schema = instance.schema
        elif isinstance(tool_impl, BaseTool):
            description = tool_impl.description
            schema = tool_impl.schema
        elif callable(tool_impl):
            description = inspect.getdoc(tool_impl) or f"Callable tool '{tool_name}'."
            schema = self._schema_from_callable(tool_impl)
        else:
            description = f"Unsupported tool type: {type(tool_impl)}"

        return {
            "name": tool_name,
            "description": description.strip(),
            "schema": schema,
        }

    def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        shared_store: Dict[str, Any],
        auto_confirm: bool = False,
        agent_name: str | None = None,
    ) -> Any:
        # T019b: deny immediately if tool is not in the active profile's allowlist (FR-008 / FR-009).
        _ap = self._get_active_profile(shared_store, agent_name)
        if _ap is not None and _ap.tools is not None:
            if tool_name not in _ap.tools:
                return {
                    "success": False,
                    "error": f"Tool '{tool_name}' is not in the active agent profile's tool allowlist.",
                }

        policy = self._resolve_confirmation_policy(
            tool_name=tool_name,
            shared_store=shared_store,
            agent_name=agent_name,
            auto_confirm=auto_confirm,
        )
        if policy == "deny":
            return {
                "success": False,
                "error": f"Execution of tool '{tool_name}' denied by confirmation policy.",
            }
        if policy == "confirm":
            approved = self._request_tool_confirmation(
                tool_name=tool_name,
                arguments=arguments,
                shared_store=shared_store,
                agent_name=agent_name,
            )
            if not approved:
                return {
                    "success": False,
                    "error": f"Execution of tool '{tool_name}' denied by user confirmation.",
                }

        tool_impl = self._resolve_tool(tool_name)

        if isinstance(tool_impl, type) and issubclass(tool_impl, BaseTool):
            return tool_impl().execute(**arguments)
        if isinstance(tool_impl, BaseTool):
            return tool_impl.execute(**arguments)
        if callable(tool_impl):
            return self._call_callable_tool(tool_impl, arguments, shared_store)

        raise TypeError(f"Unsupported tool implementation type for '{tool_name}': {type(tool_impl)}")

    def _resolve_tool(self, tool_name: str) -> Any:
        if tool_name not in self._tools:
            # Check if it's a built-in tool that hasn't been registered yet?
            # Or if it's a dynamic path
            if "/" in tool_name or ".py:" in tool_name:
                 # Attempt dynamic load? Actually ToolRuntime should probably just use what's in self._tools
                 # which is populated by PluginManager.
                 pass
            raise KeyError(f"Tool '{tool_name}' is not registered.")

        tool_impl = self._tools[tool_name]

        if isinstance(tool_impl, str):
            if "." not in tool_impl and ":" not in tool_impl:
                raise ValueError(
                    f"String tool reference '{tool_impl}' for '{tool_name}' must be an import path or file:Object."
                )
            
            if ":" in tool_impl:
                # Handle path.py:ClassName if ToolRuntime is given raw strings (unlikely with current PluginManager)
                pass

            module_name, object_name = tool_impl.rsplit(".", 1)
            module = importlib.import_module(module_name)
            tool_impl = getattr(module, object_name)
            self._tools[tool_name] = tool_impl

        return tool_impl

    def _call_callable_tool(
        self,
        callable_tool: Any,
        arguments: Dict[str, Any],
        shared_store: Dict[str, Any],
    ) -> Any:
        signature = inspect.signature(callable_tool)
        params = signature.parameters

        kwargs = dict(arguments)
        if "shared_store" in params:
            kwargs["shared_store"] = shared_store

        return callable_tool(**kwargs)

    def _schema_from_callable(self, callable_tool: Any) -> Dict[str, Any]:
        signature = inspect.signature(callable_tool)
        properties: Dict[str, Dict[str, Any]] = {}
        required: List[str] = []

        for parameter_name, parameter in signature.parameters.items():
            if parameter_name in {"self", "shared_store"}:
                continue

            properties[parameter_name] = {
                "type": "string",
                "description": f"Argument '{parameter_name}'.",
            }

            if parameter.default is inspect._empty:
                required.append(parameter_name)

        schema: Dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required

        return schema

    def _normalize_confirmation_config(
        self,
        config: Dict[str, Any],
        require_confirmation: bool,
        auto_approved_tools: set[str],
    ) -> Dict[str, Any]:
        default_policy = str(config.get("default_policy", "")).strip().lower()
        if default_policy not in VALID_CONFIRMATION_POLICIES:
            default_policy = "confirm" if require_confirmation else "allow"

        tool_policies: Dict[str, str] = {}
        raw_tool_policies = config.get("tool_policies", {})
        if isinstance(raw_tool_policies, dict):
            for raw_tool_name, raw_policy in raw_tool_policies.items():
                policy = self._normalize_policy(raw_policy)
                if policy:
                    tool_policies[str(raw_tool_name)] = policy

        for tool_name in auto_approved_tools:
            tool_policies.setdefault(str(tool_name), "allow")

        agent_policies: Dict[str, Dict[str, Any]] = {}
        raw_agent_policies = config.get("agent_policies", {})
        if isinstance(raw_agent_policies, dict):
            for raw_agent_name, raw_agent_policy in raw_agent_policies.items():
                if not isinstance(raw_agent_policy, dict):
                    continue
                normalized_agent_default = self._normalize_policy(raw_agent_policy.get("default_policy"))
                normalized_agent_tool_policies: Dict[str, str] = {}
                raw_agent_tool_policies = raw_agent_policy.get("tool_policies", {})
                if isinstance(raw_agent_tool_policies, dict):
                    for raw_tool_name, raw_policy in raw_agent_tool_policies.items():
                        policy = self._normalize_policy(raw_policy)
                        if policy:
                            normalized_agent_tool_policies[str(raw_tool_name)] = policy
                agent_policies[str(raw_agent_name)] = {
                    "default_policy": normalized_agent_default,
                    "tool_policies": normalized_agent_tool_policies,
                }

        return {
            "default_policy": default_policy,
            "tool_policies": tool_policies,
            "agent_policies": agent_policies,
        }

    def _normalize_policy(self, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if normalized in VALID_CONFIRMATION_POLICIES:
            return normalized
        return None

    def _resolve_confirmation_policy(
        self,
        tool_name: str,
        shared_store: Dict[str, Any],
        agent_name: str | None,
        auto_confirm: bool,
    ) -> str:
        if auto_confirm:
            return "allow"

        session = shared_store.get("session_tool_confirmation", {})
        if not isinstance(session, dict):
            session = {}

        session_default = self._normalize_policy(session.get("default_policy"))
        session_tools = session.get("tool_policies", {})
        if not isinstance(session_tools, dict):
            session_tools = {}
        session_agents = session.get("agent_policies", {})
        if not isinstance(session_agents, dict):
            session_agents = {}

        agent_policy = self._confirmation_config["agent_policies"].get(agent_name or "", {})
        if not isinstance(agent_policy, dict):
            agent_policy = {}
        session_agent_policy = session_agents.get(agent_name or "", {})
        if not isinstance(session_agent_policy, dict):
            session_agent_policy = {}

        # T018/T019: gather profile tool_confirmation settings once.
        _ap_tc = self._get_active_profile(shared_store, agent_name)
        profile_tc: Dict[str, Any] = (_ap_tc.tool_confirmation if _ap_tc is not None else {}) or {}

        layers = [
            # Tier 1 – session per-agent per-tool
            self._normalize_policy(
                (session_agent_policy.get("tool_policies") or {}).get(tool_name)
                if isinstance(session_agent_policy.get("tool_policies"), dict)
                else None
            ),
            # Tier 1.5 (T018) – profile per-tool override
            self._normalize_policy(
                (profile_tc.get("overrides") or {}).get(tool_name)
                if isinstance(profile_tc.get("overrides"), dict)
                else None
            ),
            # Tier 2 – config per-agent per-tool
            self._normalize_policy(
                (agent_policy.get("tool_policies") or {}).get(tool_name)
                if isinstance(agent_policy.get("tool_policies"), dict)
                else None
            ),
            # Tier 3 – session global per-tool
            self._normalize_policy(session_tools.get(tool_name)),
            # Tier 4 – session per-agent default
            self._normalize_policy(session_agent_policy.get("default_policy")),
            # Tier 4.5 (T019) – profile default
            self._normalize_policy(profile_tc.get("default")),
            # Tier 5 – config per-agent default
            self._normalize_policy(agent_policy.get("default_policy")),
            # Tier 6 – config global per-tool
            self._normalize_policy(self._confirmation_config["tool_policies"].get(tool_name)),
            # Tier 7 – session global default
            session_default,
            # Tier 8 – config global default
            self._normalize_policy(self._confirmation_config.get("default_policy")),
        ]
        for policy in layers:
            if policy:
                return policy
        return "allow"

    def _get_active_profile(self, shared_store: Dict[str, Any], agent_name: str | None) -> Any:
        profile = shared_store.get("active_agent_profile")
        if profile is None:
            return None
        effective_agent = agent_name or shared_store.get("active_agent")
        if effective_agent and getattr(profile, "agent", None) != effective_agent:
            return None
        return profile

    def _request_tool_confirmation(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        shared_store: Dict[str, Any],
        agent_name: str | None,
    ) -> bool:
        question = f"Allow tool '{tool_name}'"
        if agent_name:
            question += f" from agent '{agent_name}'"
        question += f" with arguments {arguments!r}?"
        event_handler = shared_store.get("runtime_event_handler")
        if callable(event_handler):
            event_handler(
                "tool_confirmation_requested",
                tool=tool_name,
                agent=agent_name,
                arguments=arguments,
                prompt=question,
            )

        response = self._confirm_tool.execute(
            prompt=question,
            default="no",
            shared_store=shared_store,
        )
        if not isinstance(response, dict):
            return False
        if response.get("success") is False:
            logger.warning("Tool confirmation prompt failed for '%s': %s", tool_name, response.get("error"))
            return False
        return bool(response.get("approved", False))
