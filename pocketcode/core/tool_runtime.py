from __future__ import annotations

import importlib
import inspect
import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

from pocketcode.core.interfaces import BaseTool
from pocketcode.core.reference_syntax import normalize_registry_reference
from pocketcode.plugins.core.tools import ConfirmUserInputTool

logger = logging.getLogger(__name__)

VALID_CONFIRMATION_POLICIES = {"allow", "confirm", "deny"}
VALID_APPROVAL_SCOPES = {"once", "session", "always", "deny"}
VALID_EXECUTION_MODES = {"inline", "managed_subprocess"}


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
        self._auto_approved_tools = {
            normalized
            for tool_name in (auto_approved_tools or [])
            if (normalized := self._normalize_tool_name(tool_name))
        }
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
        tool_instance = self._instantiate_tool(tool_impl)

        description = ""
        schema: Dict[str, Any] = {"type": "object", "properties": {}}

        if tool_instance is not None:
            description = tool_instance.description
            schema = tool_instance.schema
        elif callable(tool_impl):
            description = inspect.getdoc(tool_impl) or f"Callable tool '{tool_name}'."
            schema = self._schema_from_callable(tool_impl)
        else:
            description = f"Unsupported tool type: {type(tool_impl)}"

        source_path = self._tool_source_path(tool_impl, tool_instance)
        group_path = self._tool_group_path(tool_name, source_path)

        return {
            "name": tool_name,
            "description": description.strip(),
            "schema": schema,
            "group_path": list(group_path),
            "source_path": str(source_path) if source_path is not None else None,
        }

    def _tool_source_path(
        self,
        tool_impl: Any,
        tool_instance: BaseTool | None,
    ) -> Path | None:
        target = tool_instance.__class__ if tool_instance is not None else tool_impl
        try:
            source_file = inspect.getsourcefile(target) or inspect.getfile(target)
        except (OSError, TypeError):
            return None
        if not source_file:
            return None
        return Path(source_file).resolve()

    def _tool_group_path(self, tool_name: str, source_path: Path | None) -> tuple[str, ...]:
        qualified = self._normalize_tool_name(tool_name)
        namespace = qualified.split(".", 1)[0] if qualified and "." in qualified else (qualified or "other")
        source_parts = self._tool_source_group_parts(source_path)
        if not source_parts:
            return (namespace,)
        return (namespace, *source_parts)

    def _normalize_tool_name(self, tool_name: Any) -> str:
        cleaned = str(tool_name or "").strip()
        if not cleaned:
            return ""
        try:
            return normalize_registry_reference(cleaned, allowed_kinds={"tool"})
        except ValueError:
            return cleaned.replace("::", ".")

    def _registered_tool_name(self, tool_name: str) -> str:
        raw_name = str(tool_name or "").strip()
        normalized_name = self._normalize_tool_name(raw_name)
        for candidate in dict.fromkeys([raw_name, normalized_name]):
            if candidate in self._tools:
                return candidate
        return normalized_name or raw_name

    def _normalized_tool_set(self, tool_names: Any) -> set[str]:
        if not isinstance(tool_names, list):
            return set()
        normalized_names: set[str] = set()
        for tool_name in tool_names:
            normalized = self._normalize_tool_name(tool_name)
            if normalized:
                normalized_names.add(normalized)
        return normalized_names

    def _tool_policy_value(self, policies: Any, tool_name: str) -> Any:
        if not isinstance(policies, dict):
            return None
        raw_name = str(tool_name or "").strip()
        normalized_name = self._normalize_tool_name(raw_name)
        for candidate in dict.fromkeys([raw_name, normalized_name]):
            if candidate in policies:
                return policies.get(candidate)
        return None

    def _tool_source_group_parts(self, source_path: Path | None) -> tuple[str, ...]:
        if source_path is None:
            return ()
        stemmed = source_path.with_suffix("")
        parts = stemmed.parts
        if "tools" in parts:
            tools_index = max(index for index, part in enumerate(parts) if part == "tools")
            relative_parts = tuple(part for part in parts[tools_index + 1:] if part and part != "__init__")
            if relative_parts:
                return relative_parts
        if stemmed.stem and stemmed.stem != "__init__":
            return (stemmed.stem,)
        return ()

    def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        shared_store: Dict[str, Any],
        auto_confirm: bool = False,
        agent_name: str | None = None,
    ) -> Any:
        normalized_tool_name = self._registered_tool_name(tool_name)

        # T019b: deny immediately if tool is not in the active per-turn allowlist.
        active_allowed_tools = shared_store.get("active_allowed_tools")
        if isinstance(active_allowed_tools, list):
            if normalized_tool_name not in self._normalized_tool_set(active_allowed_tools):
                return {
                    "success": False,
                    "error": f"Tool '{normalized_tool_name}' is not in the active tool allowlist.",
                }

        # Fallback for callers that only pass the active profile.
        if not isinstance(active_allowed_tools, list):
            _ap = self._get_active_profile(shared_store, agent_name)
            if _ap is not None and _ap.tools is not None:
                if normalized_tool_name not in self._normalized_tool_set(_ap.tools):
                    return {
                        "success": False,
                        "error": f"Tool '{normalized_tool_name}' is not in the active agent profile's tool allowlist.",
                    }

        policy = self._resolve_confirmation_policy(
            tool_name=normalized_tool_name,
            shared_store=shared_store,
            agent_name=agent_name,
            auto_confirm=auto_confirm,
        )
        if policy == "deny":
            return {
                "success": False,
                "error": f"Execution of tool '{normalized_tool_name}' denied by confirmation policy.",
            }
        if policy == "confirm":
            approved, approval_scope = self._request_tool_confirmation(
                tool_name=normalized_tool_name,
                arguments=arguments,
                shared_store=shared_store,
                agent_name=agent_name,
            )
            if not approved:
                return {
                    "success": False,
                    "error": f"Execution of tool '{normalized_tool_name}' denied by user confirmation.",
                }
            self._apply_confirmation_response(
                tool_name=normalized_tool_name,
                shared_store=shared_store,
                approval_scope=approval_scope,
                agent_name=agent_name,
            )

        tool_impl = self._resolve_tool(normalized_tool_name)
        tool_instance = self._instantiate_tool(tool_impl)
        execution_mode = self._resolve_execution_mode(tool_impl, tool_instance)

        if execution_mode == "managed_subprocess":
            if tool_instance is None:
                raise TypeError(
                    f"Tool '{normalized_tool_name}' uses execution_mode='managed_subprocess' but is not a BaseTool implementation."
                )
            return self._execute_managed_subprocess_tool(
                tool=tool_instance,
                tool_name=normalized_tool_name,
                arguments=arguments,
                shared_store=shared_store,
                agent_name=agent_name,
            )

        if tool_instance is not None:
            return self._call_tool_instance(tool_instance, arguments, shared_store)
        if callable(tool_impl):
            return self._call_callable_tool(tool_impl, arguments, shared_store)

        raise TypeError(f"Unsupported tool implementation type for '{normalized_tool_name}': {type(tool_impl)}")

    def _resolve_tool(self, tool_name: str) -> Any:
        registered_tool_name = self._registered_tool_name(tool_name)
        if registered_tool_name not in self._tools:
            # Check if it's a built-in tool that hasn't been registered yet?
            # Or if it's a dynamic path
            if "/" in registered_tool_name or ".py:" in registered_tool_name:
                 # Attempt dynamic load? Actually ToolRuntime should probably just use what's in self._tools
                 # which is populated by PluginManager.
                 pass
            raise KeyError(f"Tool '{registered_tool_name}' is not registered.")

        tool_impl = self._tools[registered_tool_name]

        if isinstance(tool_impl, str):
            if "." not in tool_impl and ":" not in tool_impl:
                raise ValueError(
                    f"String tool reference '{tool_impl}' for '{registered_tool_name}' must be an import path or file:Object."
                )
            
            if ":" in tool_impl:
                # Handle path.py:ClassName if ToolRuntime is given raw strings (unlikely with current PluginManager)
                pass

            module_name, object_name = tool_impl.rsplit(".", 1)
            module = importlib.import_module(module_name)
            tool_impl = getattr(module, object_name)
            self._tools[registered_tool_name] = tool_impl

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

    def _call_tool_instance(
        self,
        tool_instance: BaseTool,
        arguments: Dict[str, Any],
        shared_store: Dict[str, Any],
    ) -> Any:
        signature = inspect.signature(tool_instance.execute)
        params = signature.parameters

        kwargs = dict(arguments)
        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in params.values()
        )
        if accepts_kwargs or "shared_store" in params:
            kwargs["shared_store"] = shared_store

        return tool_instance.execute(**kwargs)

    def _instantiate_tool(self, tool_impl: Any) -> BaseTool | None:
        if isinstance(tool_impl, type) and issubclass(tool_impl, BaseTool):
            return tool_impl()
        if isinstance(tool_impl, BaseTool):
            return tool_impl
        return None

    def _resolve_execution_mode(self, tool_impl: Any, tool_instance: BaseTool | None) -> str:
        if tool_instance is not None:
            mode = getattr(tool_instance, "execution_mode", "inline")
        else:
            mode = getattr(tool_impl, "execution_mode", "inline")

        normalized = str(mode or "inline").strip().lower()
        if normalized not in VALID_EXECUTION_MODES:
            logger.warning("Unknown execution mode '%s'. Falling back to inline execution.", normalized)
            return "inline"
        return normalized

    def _execute_managed_subprocess_tool(
        self,
        *,
        tool: BaseTool,
        tool_name: str,
        arguments: Dict[str, Any],
        shared_store: Dict[str, Any],
        agent_name: str | None,
    ) -> Any:
        event_handler = shared_store.get("runtime_event_handler")
        process = tool.spawn_subprocess(**arguments)
        timeout_seconds = tool.timeout_seconds
        started_at = time.monotonic()
        shared_store["active_tool_execution"] = {
            "tool": tool_name,
            "mode": "managed_subprocess",
            "pid": process.pid,
            "started_at": started_at,
        }

        if callable(event_handler):
            event_handler(
                "tool_subprocess_started",
                tool=tool_name,
                agent=agent_name,
                pid=process.pid,
            )

        try:
            while process.poll() is None:
                if self._is_cancel_requested(shared_store):
                    self._stop_subprocess(process)
                    if callable(event_handler):
                        event_handler(
                            "tool_subprocess_terminated",
                            tool=tool_name,
                            agent=agent_name,
                            pid=process.pid,
                            reason="cancelled",
                        )
                    return {
                        "success": False,
                        "error": f"Tool '{tool_name}' was terminated by cancellation.",
                        "cancelled": True,
                    }

                if timeout_seconds is not None and (time.monotonic() - started_at) > float(timeout_seconds):
                    self._stop_subprocess(process)
                    if callable(event_handler):
                        event_handler(
                            "tool_timeout",
                            tool=tool_name,
                            agent=agent_name,
                            pid=process.pid,
                            timeout_seconds=float(timeout_seconds),
                        )
                    return {
                        "success": False,
                        "error": f"Tool '{tool_name}' exceeded timeout ({float(timeout_seconds)}s).",
                        "timed_out": True,
                    }

                time.sleep(0.05)

            stdout, stderr = process.communicate()
            return tool.handle_subprocess_result(
                returncode=int(process.returncode or 0),
                stdout=stdout,
                stderr=stderr,
                **arguments,
            )
        finally:
            shared_store.pop("active_tool_execution", None)

    def _stop_subprocess(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return

        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
        else:
            process.terminate()

        try:
            process.wait(timeout=1.0)
            return
        except subprocess.TimeoutExpired:
            pass

        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
        else:
            process.kill()
        process.wait(timeout=1.0)

    def _is_cancel_requested(self, shared_store: Dict[str, Any]) -> bool:
        value = shared_store.get("run_cancel_requested")
        if callable(value):
            return bool(value())
        return bool(value)

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
                    normalized_tool_name = self._normalize_tool_name(raw_tool_name)
                    if normalized_tool_name:
                        tool_policies[normalized_tool_name] = policy

        for tool_name in auto_approved_tools:
            normalized_tool_name = self._normalize_tool_name(tool_name)
            if normalized_tool_name:
                tool_policies.setdefault(normalized_tool_name, "allow")

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
                            normalized_tool_name = self._normalize_tool_name(raw_tool_name)
                            if normalized_tool_name:
                                normalized_agent_tool_policies[normalized_tool_name] = policy
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
                self._tool_policy_value(session_agent_policy.get("tool_policies"), tool_name)
            ),
            # Tier 1.5 (T018) – profile per-tool override
            self._normalize_policy(
                self._tool_policy_value(profile_tc.get("overrides"), tool_name)
            ),
            # Tier 2 – config per-agent per-tool
            self._normalize_policy(
                self._tool_policy_value(agent_policy.get("tool_policies"), tool_name)
            ),
            # Tier 3 – session global per-tool
            self._normalize_policy(self._tool_policy_value(session_tools, tool_name)),
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

    def _normalize_approval_scope(self, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in VALID_APPROVAL_SCOPES:
            return normalized
        return "deny"

    def _apply_confirmation_response(
        self,
        *,
        tool_name: str,
        shared_store: Dict[str, Any],
        approval_scope: str,
        agent_name: str | None,
    ) -> None:
        normalized_scope = self._normalize_approval_scope(approval_scope)
        if normalized_scope == "once" or normalized_scope == "deny":
            return

        if normalized_scope == "session":
            session = shared_store.setdefault(
                "session_tool_confirmation",
                {"default_policy": None, "tool_policies": {}, "agent_policies": {}},
            )
            if not isinstance(session, dict):
                return
            tool_policies = session.setdefault("tool_policies", {})
            if not isinstance(tool_policies, dict):
                tool_policies = {}
                session["tool_policies"] = tool_policies
            tool_policies[tool_name] = "allow"
            replacer = shared_store.get("replace_session_confirmation_overrides")
            if callable(replacer):
                replacer(session)
            profile = shared_store.get("active_agent_profile")
            profile_name = getattr(profile, "name", None)
            granter = shared_store.get("grant_session_profile_tool_access")
            if callable(granter) and isinstance(profile_name, str) and profile_name:
                refreshed_profile = granter(profile_name, tool_name)
                if refreshed_profile is not None:
                    shared_store["active_agent_profile"] = refreshed_profile
            return

        if normalized_scope == "always":
            persister = shared_store.get("persist_tool_confirmation")
            if callable(persister):
                persister(tool_name, "allow")

    def _request_tool_confirmation(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        shared_store: Dict[str, Any],
        agent_name: str | None,
    ) -> tuple[bool, str]:
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
            default="deny",
            shared_store=shared_store,
        )
        if not isinstance(response, dict):
            return False, "deny"
        if response.get("success") is False:
            logger.warning("Tool confirmation prompt failed for '%s': %s", tool_name, response.get("error"))
            return False, "deny"
        scope = self._normalize_approval_scope(
            response.get("approval_scope")
            or ("once" if response.get("approved", False) else "deny")
        )
        return bool(response.get("approved", False)), scope
