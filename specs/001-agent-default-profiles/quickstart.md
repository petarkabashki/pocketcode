# Quickstart: Agent Default Profiles

**Feature**: `001-agent-default-profiles`
**Date**: 2026-03-06

This guide shows how to use agent profiles from day one, before any custom profiles exist, through to creating and cloning workspace profiles.

---

## Step 1: Use an agent — it already has a default profile

No configuration needed. Every agent automatically gets a default profile named after its qualified identifier.

```
/agent core::react
```

The status bar now shows:

```
Agent: core::react | Profile: core::react | LLM: gemini_default (gemini-2.0-pro)
```

The agent is running under its default agent profile (synthesised from the `react` agent's existing plugin.yaml declaration).

---

## Step 2: See all available agent profiles

```
/agent-profile list
```

Output example:

```
Agent Profiles:
  core::react          → agent: core::react  | llm: gemini_default        [default]
  core::coder          → agent: core::coder  | llm: gemini_default        [default]
  architect::architect → agent: architect::architect | llm: (inherited)   [default]
```

---

## Step 3: Inspect a profile

```
/agent-profile show core::react
```

Output example:

```
Profile: core::react
  Agent:   core::react
  Source:  synthesised
  LLM:     gemini_default
  Tools:   read_file, write_to_file, glob_files, search_files, run_shell_command, ...
  Prompts: (none)
  Confirmation:
    default: allow
    overrides: (none)
```

---

## Step 4: Clone it to create a custom workspace profile

```
/agent-profile clone core::react react-safe
```

Output:

```
Cloned 'core::react' → 'react-safe'
Saved to: .pocketcode/agent-profiles/react-safe.yaml
```

---

## Step 5: Edit the cloned profile

Open `.pocketcode/agent-profiles/react-safe.yaml` and customise it:

```yaml
name: react-safe
agent: core::react
description: "Read-only ReAct profile with write confirmation."

tools:
  - core::read_file
  - core::glob_files
  - core::search_files
  - core::write_to_file       # kept but with confirmation below

tool_confirmation:
  default: allow
  overrides:
    core::write_to_file: confirm
    core::delete_file: deny
    core::run_shell_command: deny
```

---

## Step 6: Reload and switch to the new profile

```
/reload
/agent-profile switch react-safe
```

Status bar:

```
Agent: core::react | Profile: react-safe | LLM: gemini_default (gemini-2.0-pro)
```

Now, any call to `write_to_file` will prompt for confirmation. Calls to `delete_file` or `run_shell_command` will be denied outright.

---

## Step 7: Switch agent and profile in one command

```
/agent core::coder --agent-profile react-safe
```

This switches the active agent to `core::coder` and simultaneously activates the `react-safe` profile. Because `react-safe.agent = core::react`, a warning is printed:

```
WARNING: Profile 'react-safe' targets agent 'core::react' but switching to 'core::coder'.
Proceeding with switch.
```

---

## Step 8: Revert to the agent's default profile

```
/agent-profile switch core::react
```

This activates the synthesised default profile for `core::react`, restoring the full tool set with no confirmation overrides.

---

## Declare a built-in default profile in plugin.yaml

Plugin authors can declare a custom default profile inside their agent block:

```yaml
agents:
  react:
    module: agents/react_agent.py
    entry_fn: create_flow
    llm_profile: gemini_default

    default_agent_profile:
      name: react-default
      description: "Standard ReAct profile."
      llm_profile: gemini_default
      tool_confirmation:
        default: allow
        overrides:
          core::delete_file: deny
```

This profile will appear in `/agent-profile list` as `react-default` instead of `core::react`, and will be activated when `/agent core::react` is called.

---

## Environment

- Python `>=3.10`, `pytest` for tests
- `.pocketcode/agent-profiles/` created automatically on first clone/save
- Profile files are plain YAML — no anchors or special syntax needed
