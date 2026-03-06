# Data Model: Agent Default Profiles

**Feature**: `001-agent-default-profiles`
**Date**: 2026-03-06

---

## Entities

### `AgentProfile` (new dataclass — `pocketcode/core/runtime_models.py`)

The core value object. Immutable once loaded.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Unique identifier. For synthesised defaults: qualified agent name (e.g. `core::react`). For explicit declarations: `name` field from YAML or qualified agent name if absent. |
| `agent` | `str` | Yes | Qualified agent reference this profile targets (e.g. `core::react`). |
| `description` | `str` | No | Human-readable description. Default: `""`. |
| `llm_profile` | `str \| None` | No | LLM configuration profile name. `None` means inherit from lower tiers. |
| `extra_prompts` | `List[str]` | No | Ordered list of file paths whose contents are appended to the system prompt each turn. Default: `[]`. |
| `tools` | `List[str] \| None` | No | Explicit tool allowlist (qualified names). `None` means inherit all tools from the agent definition. |
| `tool_confirmation` | `Dict[str, Any]` | No | `{"default": str \| None, "overrides": Dict[str, str]}`. `default` is the fallback policy; `overrides` maps qualified tool names to a policy. Absent keys mean "no opinion at this tier". Default: `{}`. |
| `source` | `str` | No | Provenance: `"synthesised"`, `"plugin"`, or `"workspace"`. Default: `"synthesised"`. |
| `source_path` | `Path \| None` | No | Absolute path to the YAML file for `"workspace"` profiles (for clone/save operations). `None` for synthesised and plugin profiles. |

**Validation rules**:
- `name` must be non-empty.
- `agent` must be non-empty and use `::` separator format or qualified dot notation.
- Valid `tool_confirmation.default` values: `"allow"`, `"confirm"`, `"deny"`, or `None`.
- Valid `tool_confirmation.overrides` values: same set.

---

### `AgentDefinition` (modified — `pocketcode/core/runtime_models.py`)

Two new fields added to the existing dataclass:

| New Field | Type | Default | Description |
|-----------|------|---------|-------------|
| `default_agent_profile` | `AgentProfile \| None` | `None` | The default agent profile for this agent. Set during plugin loading. At runtime, always resolved to a non-None value (synthesised if not explicitly declared). |

**No other changes to `AgentDefinition`.** The existing `llm_profile`, `tools`, and `prompt_sources` fields remain and serve as the canonical source data for synthesising a default profile when no explicit `default_agent_profile` block is declared.

---

### `AgentProfileManager` (new class — `pocketcode/core/agent_profile_manager.py`)

The runtime registry. Mutable (reloads on `/reload`).

**State**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `_profiles` | `Dict[str, AgentProfile]` | All loaded profiles indexed by `name`. Includes synthesised defaults + workspace-local files. |
| `_workspace_profiles_dir` | `Path` | Absolute path to `.pocketcode/agent-profiles/`. Created on first `clone()`/`save()` call. |
| `_agent_definitions` | `Dict[str, AgentDefinition]` | Agent definitions stored on each `load()` call; used by `clone()` to call `reload()` without requiring external parameters. |

**Operations**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `load(agent_definitions)` | `(Dict[str, AgentDefinition]) → None` | Stores `agent_definitions` internally. Clears `_profiles`. Synthesises defaults for all agents. Then loads `*.yaml` files from `_workspace_profiles_dir` (overrides/supplements). Emits warnings on name collisions. |
| `get(name)` | `(str) → AgentProfile \| None` | Lookup by name. |
| `list()` | `() → List[AgentProfile]` | All profiles sorted by name. |
| `clone(src_name, new_name)` | `(str, str) → AgentProfile` | Copies the source profile, assigns `new_name`, writes to `agent-profiles/<new_name>.yaml`, reloads. Raises `ValueError` if `src_name` not found or `new_name` already exists as a file. |
| `save(profile)` | `(AgentProfile) → None` | Serialises an `AgentProfile` to its `source_path` (workspace profiles dir). |
| `reload(agent_definitions)` | `(Dict[str, AgentDefinition]) → None` | Alias for `load()`. |

---

### `ActiveAgentProfile` (engine state — `pocketcode/core/engine.py`)

Not a separate class — held as `engine.active_agent_profile: AgentProfile | None`. Always non-None when an agent is active (set when `/agent` switches, set to the new profile when `/agent-profile switch` is called).

| Engine attribute | Type | Description |
|------------------|------|-------------|
| `active_agent_profile` | `AgentProfile \| None` | The currently applied agent profile. `None` only before the first agent is set. |

**Lifecycle**:
1. Engine starts: `active_agent_profile = None`.
2. `/agent core::react` called: `active_agent_profile = profile_manager.get("core::react")` (or the profile's declared default name).
3. `/agent-profile switch react-lite` called: `active_agent_profile = profile_manager.get("react-lite")`.
4. If `react-lite.agent != current_agent`: also switch `engine.current_agent`.

---

## State Transitions

```
Initial                 → (agent set)    → active_agent_profile = agent.default_agent_profile
Profile active          → /agent-profile switch <name>  → active_agent_profile = profiles[name]
Profile active          → /reload         → agent_profile_manager.reload(); re-apply active profile by name
Profile active          → /agent <other>  → active_agent_profile = other_agent.default_agent_profile
```

---

## Name Collision Precedence

When multiple sources declare a profile with the same name, the precedence (highest to lowest) is:

1. **Plugin-declared** (`default_agent_profile` block in `plugin.yaml` with an explicit `name` field) — plugin author intent takes highest precedence
2. **Workspace-local file** (`.pocketcode/agent-profiles/<name>.yaml`) — user customisation; wins only over synthesised defaults
3. **Synthesised default** (qualified agent name, no explicit `default_agent_profile` block) — lowest precedence, always a fallback

In all cases a `WARNING` log is emitted identifying both conflicting sources.

---

## Relationships

```
PluginManager
  └─ loads → AgentDefinition (one per registered agent)
               └─ has → AgentProfile (default_agent_profile, synthesised or explicit)

AgentProfileManager
  ├─ indexes → AgentProfile (all profiles by name)
  └─ loads from → .pocketcode/agent-profiles/*.yaml

Engine
  ├─ owns → AgentProfileManager
  └─ holds → active_agent_profile: AgentProfile

AgentRuntime
  └─ reads active_agent_profile from shared_store → applies llm_profile override + tool filtering + extra_prompts

ToolRuntime
  └─ reads active_agent_profile from shared_store → applies tool_confirmation tiers
```
