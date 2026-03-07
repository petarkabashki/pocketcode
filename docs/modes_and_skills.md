# Modes and Skills

Pocketcode now supports two Markdown-authored session overlays on top of the
existing `flow + agent` runtime:

- `mode`: one active session preset
- `skill`: zero or more active capability packs

Neither introduces a second runtime. Both resolve into the existing agent
runtime controls: prompt text, LLM override, tool scope, and tool confirmation.

## Modes

Modes live under `.pocketcode/modes/*.md`.

Discovery controls:

- Rename a mode file or parent folder to include `.disabled`.
- Add workspace-owned rules in `<workspace>/.pocketcode/.pocketcodeignore`, for example `modes/archive/`.

Each mode uses YAML front matter plus a Markdown body:

```md
---
name: review
description: Review mode
flow: core::react
llm_profile: gemini_default
tool_confirmation:
  default: confirm
---
Focus on bugs, regressions, unsafe assumptions, and missing tests.
```

Supported front matter keys:

- `name`
- `description`
- `flow`
- `agent`
- `llm_profile`
- `tools`
- `extra_prompts`
- `tool_confirmation`

Resolution rules:

- if `agent` is set, the mode inherits from that agent profile first
- else if `flow` is set, the mode inherits from the flow's default profile
- the Markdown body becomes inline system prompt text for an ephemeral active profile
- `extra_prompts` are resolved relative to the mode file first, then workspace prompt roots

CLI:

- `/mode list`
- `/mode show [name]`
- `/mode switch <name>`
- `/mode clear`

## Skills

Skills live under `.pocketcode/skills/<skill_name>/`.

Expected layout:

```text
.pocketcode/skills/python-testing/
├── SKILL.md
├── tools/
├── scripts/
├── references/
└── assets/
```

Example `SKILL.md`:

```md
---
name: python-testing
description: Pytest workflow
tools:
  - core.read_file
extra_prompts:
  - references/style.md
---
Reproduce failures first, then patch minimally.
```

Skill behavior:

- the Markdown body is appended to the active system prompt while enabled
- `extra_prompts` are resolved relative to the skill directory first
- tool references listed in front matter are added to the effective tool surface
- Python modules under `tools/*.py` are loaded when the skill is enabled
- skill-owned tools are registered under `skill.<skill_name>.*`

Discovery controls:

- Rename a skill directory, `SKILL.md`, or any nested asset/tool folder so one path component contains `.disabled`.
- Add workspace-owned rules in `<workspace>/.pocketcode/.pocketcodeignore`.
- Rules are evaluated relative to `.pocketcode/` and support `!` re-includes.

Example:

```gitignore
skills/*/tools/*.py
!skills/python-testing/tools/run_pytest.py
skills/legacy/
```

CLI:

- `/skill list` (grouped by top-level skill name prefix; for example `pocketcode` and `pocketflow`)
- `/skill show <name>`
- `/skill enable <name>`
- `/skill disable <name>`

Textual UI:

- `F6` opens the `Control Center`, which drills into agent, mode, LLM, skills, tools, tool policies, selection presets, session confirmation, and system settings
- `F3` opens the edit selector for agent, mode, LLM, tools, and tool policies
- `F4` opens the clone selector for agent, mode, and LLM configs
- the right-hand inspector includes a `Skills` selection list for the same runtime toggles
- skill selection supports both individual skills and top-level skill groups
- tool selection nests groups from the tool source path under `tools/`; separate files such as `tools/filesystem.py` and `tools/user_input.py` appear as separate groups, and nested folders create nested groups
- mode, active profile, global LLM override, skills, session confirmation, auto-confirm, and per-profile tool/policy overrides are persisted as last-used state and restored on startup
- the Textual console starts empty; startup status is shown in the header and control panels rather than injected into the output log
- when launching the Textual UI, startup/plugin logs are written to `pocketcode.log` instead of the terminal stream to keep the screen clean
- grouped or individual tool selection and tool policy editing use `Apply` for persisted last-used state, `Reset` to clear last-used overrides, and `Save as Default` to write the current selection into the default config
- editing a plugin/synthesised agent or LLM config from the Textual UI prompts for a workspace clone first, then opens the editor against that new workspace-backed copy
- the control center supports editing, cloning, and deleting the current workspace-backed mode, agent, and LLM configs
- named selection presets save and reload the whole current runtime selection snapshot, including the active mode/profile, LLM override, skills, confirmation default, auto-confirm flag, and persisted per-profile tool/policy overrides
- searchable selection popups support `Ctrl+Down` to jump into the list, `Ctrl+Up` to return to search, and `Space` to toggle the highlighted item without losing the current row
- the control center also exposes a `System Settings` form that saves theme, workspace mode, and default agent/LLM values to `pocketcode.yml`

This repo ships a workspace-builder skill pack under `.pocketcode/skills/`:

- `pocketcode-workspace-builder`: umbrella skill for the workspace builder agent
- `pocketflow-graph-authoring`: PocketFlow node/flow authoring
- `pocketcode-plugin-authoring`: plugin manifests and flow registration
- `pocketcode-profiles-prompts`: composite agents, modes, skills, and prompt includes
- `pocketcode-tools-runtime`: tools and runtime execution behavior
- `pocketcode-workspace-assets`: shared `.pocketcode/` assets and portability rules

## Runtime precedence

Prompt and tool behavior resolve in this order:

`flow defaults -> agent -> active mode -> enabled skills -> session overrides`
