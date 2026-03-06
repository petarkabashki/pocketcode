# Contract: Agent Profile YAML Schema

**Feature**: `001-agent-default-profiles`
**Date**: 2026-03-06
**Schema version**: 1

This document defines the two YAML surfaces introduced by agent profiles:

1. **The `default_agent_profile` block** inside `plugin.yaml` — declares an agent's built-in default profile inline.
2. **Workspace agent profile files** in `.pocketcode/agent-profiles/*.yaml` — user-defined profiles stored per workspace.

---

## 1. `default_agent_profile` block inside `plugin.yaml`

Placed as a sibling key to `module`, `entry_fn`, `llm_profile`, and `tools` inside an agent entry.

```yaml
agents:
  react:
    description: General-purpose ReAct agent.
    module: agents/react_agent.py
    entry_fn: create_flow
    llm_profile: gemini_default        # existing top-level key; still valid as fallback

    default_agent_profile:             # NEW — optional block
      name: react-default              # optional; if absent, defaults to "core::react"
      description: "Default ReAct profile using the standard Gemini model."
      llm_profile: gemini_default      # overrides top-level llm_profile at profile tier
      tools:                           # optional; if absent, inherits all agent tools
        - read_file
        - write_to_file
        - glob_files
        - search_files
        - run_shell_command
      extra_prompts: []                # optional; list of paths relative to this file or .pocketcode/
      tool_confirmation:               # optional
        default: allow                 # allow | confirm | deny
        overrides:
          core::write_to_file: confirm
          core::delete_file: deny
```

### Field rules

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | No | Profile name. If absent, the qualified agent name (e.g. `core::react`) is used. |
| `description` | string | No | Human-readable description. |
| `llm_profile` | string | No | LLM config profile name. If absent, no profile-tier LLM override is applied. |
| `tools` | list of strings | No | Tool allowlist (local or qualified names). If absent, agent's full tool set is inherited. |
| `extra_prompts` | list of strings | No | File paths appended to system prompt each turn. |
| `tool_confirmation.default` | `allow`\|`confirm`\|`deny` | No | Default policy for all tools not covered by overrides. |
| `tool_confirmation.overrides` | map of tool name → policy | No | Per-tool policy. Tool names use qualified format (`plugin::tool_name`). |

**Backward compatibility**: If `default_agent_profile` is absent entirely, the system synthesises a default profile from the agent's existing top-level fields (`llm_profile`, `tools`, `prompts`). Existing plugin.yaml files are fully compatible with no changes required.

---

## 2. Workspace agent profile file (`.pocketcode/agent-profiles/<name>.yaml`)

One file per profile. The filename does not need to match the `name` field (though it is recommended).

```yaml
name: react-safe                        # required; must be unique across all profiles
agent: core::react                      # required; qualified agent reference
description: "ReAct profile restricted to read-only tools with confirmation on writes."

llm_profile: gemini_flash               # optional

tools:                                  # optional; absent = inherit all agent tools
  - core::read_file
  - core::glob_files
  - core::search_files

extra_prompts:                          # optional
  - prompts/safe-mode-instructions.md  # relative to this file first, then .pocketcode/

tool_confirmation:                      # optional
  default: confirm
  overrides:
    core::write_to_file: confirm
    core::delete_file: deny
    core::run_shell_command: deny
```

### Field rules

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | Yes | Profile name. Must be unique. Collision → warning + last-loaded (alphabetical) wins. |
| `agent` | string | Yes | Qualified agent reference. Format: `plugin::agent` or `plugin.agent`. |
| `description` | string | No | Human-readable description. |
| `llm_profile` | string | No | LLM config profile name. |
| `tools` | list of strings | No | Tool allowlist. Absent = no restriction. |
| `extra_prompts` | list of strings | No | Paths resolved: (1) relative to this YAML file, (2) relative to `.pocketcode/`. |
| `tool_confirmation.default` | `allow`\|`confirm`\|`deny` | No | Fallback policy. |
| `tool_confirmation.overrides` | map | No | Per-tool policy overrides. |

### Load order & collision rules

- Files are loaded alphabetically by filename.
- If a workspace file's `name` matches a synthesised default name (a qualified agent name, i.e. the plugin provided no explicit `name` field in `default_agent_profile`), the workspace file takes precedence, overriding the synthesised default. A `WARNING` is logged.
- If a workspace file's `name` matches a plugin-declared `default_agent_profile` name (where the plugin author provided an explicit `name` field), the **plugin declaration takes precedence** over the workspace file. A `WARNING` is logged identifying both sources.
- Two workspace files with the same `name`: last-loaded (alphabetically) wins. `WARNING` logged.

---

## 3. CLI command reference

| Command | Effect |
|---------|--------|
| `/agent-profile list` | List all loaded agent profiles (name, target agent, LLM) |
| `/agent-profile show <name>` | Display full profile configuration |
| `/agent-profile switch <name>` | Activate named profile; switches active agent if needed (with warning) |
| `/agent-profile clone <src> <new>` | Clone profile to `.pocketcode/agent-profiles/<new>.yaml` |
| `/agent <name> --agent-profile <profile>` | Switch agent and activate profile atomically |

---

## 4. Status display

When an agent is active, the CLI status bar shows:

```
Runtime flow: <flow> | Agent: <agent> | Profile: <profile-name> | LLM: <llm-profile> (<model>)
```

The `engine.status()` dict gains a new key `active_agent_profile: str | None` with the name of the currently active profile.
