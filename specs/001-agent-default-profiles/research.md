# Research: Agent Default Profiles

**Feature**: `001-agent-default-profiles`
**Date**: 2026-03-06
**Status**: Complete — all NEEDS CLARIFICATION resolved

---

## Decision Log

### D-001: Where profiles are stored (workspace-local)
- **Decision**: `.pocketcode/agent-profiles/*.yaml` — one YAML file per agent profile
- **Rationale**: Consistent with existing workspace-local convention (`.pocketcode/plugins/`, `.pocketcode/prompts/`). Isolated from plugin source files. Git-trackable alongside the project.
- **Alternatives considered**: Inline in `pocketcode.yml` (too monolithic; limits per-file editing and git diffs), one big `profiles.yaml` file (same problem)

### D-002: Synthesised default profile naming
- **Decision**: Hybrid — if `default_agent_profile` block in plugin.yaml has a `name` field, use it; otherwise use the qualified agent identifier (e.g. `core::react`)
- **Rationale**: Predictable for end-users (qualified agent name always works as the default profile name), but allows plugin authors to choose a friendlier name when needed.
- **Alternatives considered**: Always use qualified agent name (simpler but inflexible), always require explicit name (breaks backward compatibility)

### D-003: `/agent-profile off` command
- **Decision**: Not implemented. No null-profile state exists. Agent always runs under a named agent profile.
- **Rationale**: FR-001 mandates a profile for every agent turn. A deactivation command would create a separate code path that bypasses profile tiers. To reset to default, users run `/agent-profile switch core::react`.
- **Alternatives considered**: Reset-to-default semantics (confusing naming — "off" implies deactivation), null state (contradicts always-a-profile requirement)

### D-004: `extra_prompts` path resolution
- **Decision**: Resolve relative to the agent profile YAML file's own directory first; fall back to the workspace `.pocketcode/` directory. Absolute paths are accepted but discouraged.
- **Rationale**: Profile-relative paths keep profiles self-contained and portable within their directory. `.pocketcode/` fallback allows shared prompt snippets across multiple profiles without path repetition.
- **Alternatives considered**: Workspace-root relative only (breaks when profile files live in subdirectories), profile-relative only (no shared prompt support without duplication)

### D-005: Cross-agent `/agent-profile switch` UX
- **Decision**: Auto-proceed with warning printed. No confirmation prompt required.
- **Rationale**: The user explicitly typed the command and the profile name; they intend the switch. Warning ensures they are informed about the agent change. Interactive y/n would slow power-user workflows.
- **Alternatives considered**: y/n with default "yes" (extra keystroke for no safety benefit), block the switch entirely if agent mismatch (overly restrictive)

### D-006: Tool confirmation profile tier placement
- **Decision**: Insert profile tier between "session agent-specific tool override" (tier 1) and "config agent-specific tool override" (tier 2) for per-tool overrides; insert between "session agent default" (tier 4) and "config agent default" (tier 5) for default policy.
- **Rationale**: Profile settings should be overridable by live session overrides (`/confirm`) but should override static config. This keeps `/confirm` as the highest-priority interactive escape hatch.
- **Alternatives considered**: Below all config tiers (would make profiles useless when any config is present), above session overrides (prevents `/confirm` from overriding profile during a session)

### D-007: LLM profile resolution tier placement
- **Decision**: Insert new profile tier between "dynamic per-agent override" (tier 4) and "agent definition llm_profile" (tier 5).
- **Rationale**: FR-012 requires profile LLM to be above the agent's built-in `llm_profile` but below CLI overrides (`/llm-agent` = tier 1, `/llm` = tier 3). Dynamic overrides (tier 4) are set by the LLM at runtime; profile should not override those.
- **Alternatives considered**: Between tier 1 and tier 2 (too high — would override config-level agent overrides), between tier 2 and tier 3 (would allow config to override profile, confusing)

---

## Technical Findings

### Existing LLM Resolution Chain (`agent_runtime.py`)

| Tier | Source |
|------|--------|
| 1 | CLI per-agent session override (`/llm-agent`) |
| 2 | Config per-agent override (`runtime.llm_overrides.agents`) |
| 3 | Global CLI session override (`/llm`) |
| 4 | Dynamic per-agent override (set by agent at runtime) |
| **4.5 NEW** | **Active agent profile `llm_profile`** |
| 5 | `agent_definition.llm_profile` (from plugin.yaml) |
| 6 | Default LLM profile from engine config |
| 7 | `llm_router.default_profile_name` |

### Existing Tool Confirmation Chain (`tool_runtime.py`)

| Tier | Source |
|------|--------|
| 0 | `auto_confirm=True` → immediate `"allow"` |
| 1 | `session[agent][tool]` (session per-agent per-tool) |
| **1.5 NEW** | **Active agent profile `tool_confirmation.overrides[tool_name]`** |
| 2 | `config[agent][tool]` (config per-agent per-tool) |
| 3 | `session[tool]` (session global per-tool) |
| 4 | `session[agent].default` (session per-agent default) |
| **4.5 NEW** | **Active agent profile `tool_confirmation.default`** |
| 5 | `config[agent].default` (config per-agent default) |
| 6 | `config[tool]` (config global per-tool) |
| 7 | `session.default` |
| 8 | `config.default` |

### `AgentDefinition` current fields (runtime_models.py)

Already has `llm_profile: str | None = None`. Does NOT yet have any `default_agent_profile` or `tool_confirmation` field. New field `default_agent_profile_name: str | None = None` needed so the runtime can look up which profile is this agent's default.

### `manifest_loader.py`

`ParsedManifest.agents` is `Dict[str, Dict[str, Any]]`. The raw agent dict is passed through to `plugin_manager._register_agent_definition`. No new manifest-level parsing is needed — `_register_agent_definition` can directly read the `default_agent_profile` key from the raw dict.

### `plugin_manager._register_agent_definition`

Already reads: `module`, `entry_fn`, `description`, `llm_profile`, `tools`, `handoff_agents`, `execution_mode`, `deterministic_handler`, `composite_agents`, `system_prompt`/`prompt_sources`, `pre`/`steps`/`post` handlers, `handoff_policies`, `default_handoff_policy`.

**New key to read**: `default_agent_profile` → dict with optional fields `name`, `llm_profile`, `tools`, `extra_prompts`, `tool_confirmation`. This produces an `AgentProfile` object stored on `AgentDefinition.default_agent_profile` or in the `AgentProfileManager`.

### `engine.py` initialization pattern

Components are built in `__init__` in order: `PluginManager` → `LlmRouter` → `ToolRuntime` → `AgentRuntime`. New `AgentProfileManager` should be built **after** `PluginManager` (needs the registered agent definitions to synthesise defaults) and **before** `AgentRuntime` (runtime needs access to profiles).

### `command_handler.py` dispatch

Flat `if`/`elif` string dispatch. Adding `/agent-profile` requires a new `elif "agent-profile" in command` branch (or a new helper `_handle_agent_profile_command(parts, engine, cli_context)`). The `--agent-profile` flag on `/agent` requires parsing `parts` for `--agent-profile` before dispatching to the existing agent-set logic.

### `textual_app.py` status bar

Current format: `"Runtime flow: {runtime_flow} | Agent: {agent_display} | LLM: {current_llm_profile} ({current_llm_model})"`. Adding agent profile: insert `| Profile: {agent_profile_name}` after the Agent segment.

### Test patterns

- Unit tests use `tmp_path` fixture + `write_yaml()` helper
- `caplog` for log-level assertions
- Classes grouped by concern, all in `tests/unit/`
- Integration tests import engine and plugins directly, use real plugin dirs

---

## No Remaining Unknowns

All 5 clarification questions from the spec session are resolved and documented in `/specs/001-agent-default-profiles/spec.md#clarifications`. No NEEDS CLARIFICATION items remain.
