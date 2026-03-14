from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from pocketcode.core.stackvm_driver import (
        CompiledStackVmProgram,
        StackVmStandaloneHostConfig,
        StandaloneStackVmRunResult,
    )


@dataclass(frozen=True)
class StackVmStandaloneRuntime:
    compiled: "CompiledStackVmProgram"
    workspace_root: Path
    agent_name: str = "__stackvm_standalone__"
    host_config: "StackVmStandaloneHostConfig | None" = None
    shared_store_seed: dict[str, Any] = field(default_factory=dict)

    def run(
        self,
        *,
        request: str = "",
        debug: bool = False,
        agent_name: str | None = None,
        host_config: "StackVmStandaloneHostConfig | None" = None,
        auto_confirm_tools: bool = False,
        interaction_handler: Any = None,
        runtime_event_handler: Any = None,
        llm_router: Any = None,
        tool_runtime: Any = None,
        llm_profile: str | None = None,
        system_prompt: str = "",
        tool_definitions: list[dict[str, Any]] | None = None,
        shared_store: dict[str, Any] | None = None,
    ) -> "StandaloneStackVmRunResult":
        from pocketcode.core.stackvm_driver import run_compiled_stackvm_program

        seeded_store = dict(self.shared_store_seed)
        if shared_store:
            seeded_store.update(shared_store)
        return run_compiled_stackvm_program(
            compiled=self.compiled,
            request=request,
            workspace_root=self.workspace_root,
            agent_name=agent_name or self.agent_name,
            debug=debug,
            host_config=host_config if host_config is not None else self.host_config,
            auto_confirm_tools=auto_confirm_tools,
            interaction_handler=interaction_handler,
            runtime_event_handler=runtime_event_handler,
            llm_router=llm_router,
            tool_runtime=tool_runtime,
            llm_profile=llm_profile,
            system_prompt=system_prompt,
            tool_definitions=tool_definitions,
            shared_store=seeded_store,
        )

    def create_session(
        self,
        *,
        session_id: str | None = None,
        title: str | None = None,
        shared_store_state: dict[str, Any] | None = None,
        transcript: list[dict[str, Any]] | None = None,
    ) -> "StackVmStandaloneSession":
        return StackVmStandaloneSession(
            runtime=self,
            session_id=str(session_id or uuid4().hex),
            title=str(title or self.agent_name or "StackVM Standalone Session"),
            shared_store_state=dict(shared_store_state or {}),
            transcript=[dict(item) for item in (transcript or []) if isinstance(item, dict)],
        )


@dataclass
class StackVmStandaloneSession:
    runtime: StackVmStandaloneRuntime
    session_id: str = field(default_factory=lambda: uuid4().hex)
    title: str = "StackVM Standalone Session"
    shared_store_state: dict[str, Any] = field(default_factory=dict)
    transcript: list[dict[str, Any]] = field(default_factory=list)

    def append_transcript_entry(
        self,
        *,
        role: str,
        content: str,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "entry_id": uuid4().hex,
            "role": str(role or "system"),
            "content": str(content or ""),
            "run_id": str(run_id) if run_id else None,
            "metadata": dict(metadata or {}),
        }
        self.transcript.append(entry)
        return dict(entry)

    def snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "workspace_root": str(self.runtime.workspace_root),
            "agent_name": self.runtime.agent_name,
            "shared_store_state": dict(self.shared_store_state),
            "transcript": [dict(item) for item in self.transcript],
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        if not isinstance(snapshot, dict):
            raise TypeError("Standalone session snapshot must be a mapping.")
        self.session_id = str(snapshot.get("session_id") or self.session_id)
        self.title = str(snapshot.get("title") or self.title)
        self.shared_store_state = dict(snapshot.get("shared_store_state") or {})
        self.transcript = [dict(item) for item in snapshot.get("transcript") or [] if isinstance(item, dict)]

    def clear(self) -> None:
        self.shared_store_state.clear()
        self.transcript.clear()

    def run(
        self,
        *,
        request: str = "",
        debug: bool = False,
        agent_name: str | None = None,
        host_config: "StackVmStandaloneHostConfig | None" = None,
        auto_confirm_tools: bool = False,
        interaction_handler: Any = None,
        runtime_event_handler: Any = None,
        llm_router: Any = None,
        tool_runtime: Any = None,
        llm_profile: str | None = None,
        system_prompt: str = "",
        tool_definitions: list[dict[str, Any]] | None = None,
        shared_store: dict[str, Any] | None = None,
        persist_transcript: bool = True,
    ) -> "StandaloneStackVmRunResult":
        session_store = dict(self.shared_store_state)
        session_store["standalone_session_id"] = self.session_id
        session_store["standalone_session_title"] = self.title
        session_store["standalone_session_persistent_keys"] = sorted(
            str(key)
            for key in self.shared_store_state.keys()
            if str(key)
            not in {
                "standalone_session_id",
                "standalone_session_title",
                "standalone_transcript",
                "standalone_transcript_text",
                "standalone_session_persistent_keys",
            }
        )
        if persist_transcript:
            session_store["standalone_transcript"] = [dict(item) for item in self.transcript]
            session_store["standalone_transcript_text"] = _format_transcript_text(self.transcript)
        if shared_store:
            session_store.update(shared_store)

        if persist_transcript and str(request or "").strip():
            self.append_transcript_entry(role="user", content=str(request or ""))
            session_store["standalone_transcript"] = [dict(item) for item in self.transcript]
            session_store["standalone_transcript_text"] = _format_transcript_text(self.transcript)

        result = self.runtime.run(
            request=request,
            debug=debug,
            agent_name=agent_name,
            host_config=host_config,
            auto_confirm_tools=auto_confirm_tools,
            interaction_handler=interaction_handler,
            runtime_event_handler=runtime_event_handler,
            llm_router=llm_router,
            tool_runtime=tool_runtime,
            llm_profile=llm_profile,
            system_prompt=system_prompt,
            tool_definitions=tool_definitions,
            shared_store=session_store,
        )

        run_id = str(result.shared_store.get("run_id") or "")
        if persist_transcript:
            if result.final_answer is not None and str(result.final_answer).strip():
                self.append_transcript_entry(
                    role="assistant",
                    content=str(result.final_answer),
                    run_id=run_id or None,
                )
            elif result.error_message is not None and str(result.error_message).strip():
                self.append_transcript_entry(
                    role="system",
                    content=f"Run failed: {result.error_message}",
                    run_id=run_id or None,
                )

        self.shared_store_state = _extract_persistent_session_store(result.shared_store)
        self.shared_store_state["standalone_session_id"] = self.session_id
        self.shared_store_state["standalone_session_title"] = self.title
        self.shared_store_state["standalone_session_persistent_keys"] = sorted(
            str(key)
            for key in self.shared_store_state.keys()
            if str(key)
            not in {
                "standalone_session_id",
                "standalone_session_title",
                "standalone_transcript",
                "standalone_transcript_text",
                "standalone_session_persistent_keys",
            }
        )
        if persist_transcript:
            self.shared_store_state["standalone_transcript"] = [dict(item) for item in self.transcript]
            self.shared_store_state["standalone_transcript_text"] = _format_transcript_text(self.transcript)

        return result


def create_stackvm_standalone_runtime(
    *,
    compiled: "CompiledStackVmProgram",
    workspace_root: str | Path | None = None,
    agent_name: str = "__stackvm_standalone__",
    host_config: "StackVmStandaloneHostConfig | None" = None,
    shared_store_seed: dict[str, Any] | None = None,
) -> StackVmStandaloneRuntime:
    resolved_workspace_root = Path(workspace_root).resolve() if workspace_root is not None else Path.cwd().resolve()
    return StackVmStandaloneRuntime(
        compiled=compiled,
        workspace_root=resolved_workspace_root,
        agent_name=str(agent_name),
        host_config=host_config,
        shared_store_seed=dict(shared_store_seed or {}),
    )


def create_stackvm_standalone_runtime_target(
    *,
    vm_source: str | None = None,
    vm_entry: str | None = None,
    vm_module: str | None = None,
    vm_modules: list[str] | tuple[str, ...] | None = None,
    vm_module_prefixes: dict[str, str] | None = None,
    vm_file: str | None = None,
    vm_files: list[str] | tuple[str, ...] | None = None,
    base_dir: str | Path | None = None,
    search_roots: list[str | Path] | tuple[str | Path, ...] = (),
    workspace_root: str | Path | None = None,
    agent_name: str = "__stackvm_standalone__",
    host_config: "StackVmStandaloneHostConfig | None" = None,
    shared_store_seed: dict[str, Any] | None = None,
) -> StackVmStandaloneRuntime:
    from pocketcode.core.stackvm_driver import compile_stackvm_program_target

    compiled = compile_stackvm_program_target(
        vm_source=vm_source,
        vm_entry=vm_entry,
        vm_module=vm_module,
        vm_modules=vm_modules,
        vm_module_prefixes=vm_module_prefixes,
        vm_file=vm_file,
        vm_files=vm_files,
        base_dir=base_dir,
        search_roots=search_roots,
    )
    return create_stackvm_standalone_runtime(
        compiled=compiled,
        workspace_root=workspace_root,
        agent_name=agent_name,
        host_config=host_config,
        shared_store_seed=shared_store_seed,
    )


def create_stackvm_standalone_session(
    *,
    runtime: StackVmStandaloneRuntime,
    session_id: str | None = None,
    title: str | None = None,
    shared_store_state: dict[str, Any] | None = None,
    transcript: list[dict[str, Any]] | None = None,
) -> StackVmStandaloneSession:
    return runtime.create_session(
        session_id=session_id,
        title=title,
        shared_store_state=shared_store_state,
        transcript=transcript,
    )


def create_stackvm_standalone_session_target(
    *,
    vm_source: str | None = None,
    vm_entry: str | None = None,
    vm_module: str | None = None,
    vm_modules: list[str] | tuple[str, ...] | None = None,
    vm_module_prefixes: dict[str, str] | None = None,
    vm_file: str | None = None,
    vm_files: list[str] | tuple[str, ...] | None = None,
    base_dir: str | Path | None = None,
    search_roots: list[str | Path] | tuple[str | Path, ...] = (),
    workspace_root: str | Path | None = None,
    agent_name: str = "__stackvm_standalone__",
    host_config: "StackVmStandaloneHostConfig | None" = None,
    shared_store_seed: dict[str, Any] | None = None,
    session_id: str | None = None,
    title: str | None = None,
    shared_store_state: dict[str, Any] | None = None,
    transcript: list[dict[str, Any]] | None = None,
) -> StackVmStandaloneSession:
    runtime = create_stackvm_standalone_runtime_target(
        vm_source=vm_source,
        vm_entry=vm_entry,
        vm_module=vm_module,
        vm_modules=vm_modules,
        vm_module_prefixes=vm_module_prefixes,
        vm_file=vm_file,
        vm_files=vm_files,
        base_dir=base_dir,
        search_roots=search_roots,
        workspace_root=workspace_root,
        agent_name=agent_name,
        host_config=host_config,
        shared_store_seed=shared_store_seed,
    )
    return create_stackvm_standalone_session(
        runtime=runtime,
        session_id=session_id,
        title=title,
        shared_store_state=shared_store_state,
        transcript=transcript,
    )


def restore_stackvm_standalone_session(
    *,
    runtime: StackVmStandaloneRuntime,
    snapshot: dict[str, Any],
) -> StackVmStandaloneSession:
    session = create_stackvm_standalone_session(runtime=runtime)
    session.restore(snapshot)
    return session


def restore_stackvm_standalone_session_target(
    *,
    snapshot: dict[str, Any],
    vm_source: str | None = None,
    vm_entry: str | None = None,
    vm_module: str | None = None,
    vm_modules: list[str] | tuple[str, ...] | None = None,
    vm_module_prefixes: dict[str, str] | None = None,
    vm_file: str | None = None,
    vm_files: list[str] | tuple[str, ...] | None = None,
    base_dir: str | Path | None = None,
    search_roots: list[str | Path] | tuple[str | Path, ...] = (),
    workspace_root: str | Path | None = None,
    agent_name: str = "__stackvm_standalone__",
    host_config: "StackVmStandaloneHostConfig | None" = None,
    shared_store_seed: dict[str, Any] | None = None,
) -> StackVmStandaloneSession:
    runtime = create_stackvm_standalone_runtime_target(
        vm_source=vm_source,
        vm_entry=vm_entry,
        vm_module=vm_module,
        vm_modules=vm_modules,
        vm_module_prefixes=vm_module_prefixes,
        vm_file=vm_file,
        vm_files=vm_files,
        base_dir=base_dir,
        search_roots=search_roots,
        workspace_root=workspace_root,
        agent_name=agent_name,
        host_config=host_config,
        shared_store_seed=shared_store_seed,
    )
    return restore_stackvm_standalone_session(runtime=runtime, snapshot=snapshot)


_SESSION_EPHEMERAL_KEYS = {
    "standalone_session_persistent_keys",
    "run_id",
    "initial_request",
    "workspace_root",
    "filesystem_root",
    "cli_context",
    "formatted_cli_context",
    "active_agent",
    "active_flow",
    "stackvm_trace_enabled",
    "auto_confirm_tools",
    "last_vm_sources",
    "last_vm_source",
    "last_vm_expanded_source",
    "last_vm_expansion_metadata",
    "last_vm_validation_warnings",
    "last_vm_analysis",
    "last_vm_diagnostics",
    "runtime_event_handler",
    "interaction_handler",
    "final_output",
    "vm_trace",
    "vm_trace_scope_summaries",
    "vm_trace_decisions",
}


def _extract_persistent_session_store(shared_store: dict[str, Any]) -> dict[str, Any]:
    persisted: dict[str, Any] = {}
    for key, value in shared_store.items():
        if key in _SESSION_EPHEMERAL_KEYS:
            continue
        persisted[key] = value
    return persisted


def _format_transcript_text(entries: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for entry in entries:
        role = str(entry.get("role") or "system").strip().lower()
        content = " ".join(str(entry.get("content") or "").split())
        if not content:
            continue
        if role == "user":
            label = "User"
        elif role == "assistant":
            label = "Assistant"
        else:
            label = "System"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)
