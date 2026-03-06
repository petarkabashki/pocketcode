# Feature Specification: Agent Default Profiles

**Feature Branch**: `001-agent-default-profiles`
**Created**: 2026-03-06
**Status**: Draft
**Input**: User description: "agents should have a default profile with their definition. the CLI when using an agent should do so via a profile."

## Background & Original Requirements

This feature originated from a broader request to introduce **agent profiles** as a first-class concept in PocketCoder. The original requirements were:

1. **Varying LLM selection per profile** — each profile can target a different LLM configuration (provider, model, parameters), allowing the same agent to be run against a fast model for quick tasks and a stronger model for complex ones.

2. **Varying prompt content per profile** — each profile can augment or replace the agent's default system prompt, enabling different behavioural personas or instruction sets without modifying plugin source files.

3. **Varying tool selection per profile** — each profile can restrict the agent's available tool set to a named subset, enabling narrower, safer, or faster configurations tailored to specific tasks.

4. **CLI support for managing agent profiles** — the CLI must allow users to list available agent profiles, inspect an agent profile, switch the active agent profile, and clone an existing agent profile to create a customised variant, all without restarting.

5. **Tool confirmation policies on agent profiles** — each agent profile can embed confirmation policies (`allow`, `confirm`, `deny`) at both a default level and per individual tool, giving operators fine-grained control over which tool calls require human approval.

The feature was subsequently refined to establish that **every agent must have a default agent profile** (explicitly declared in `plugin.yaml` or synthesised from existing agent fields), and that **the CLI activates agents through their agent profiles** rather than directly — making the agent profile the single, unified entry point for agent runtime configuration.

---

## Clarifications

### Session 2026-03-06

- Q: What name does a synthesised default profile receive? → A: The qualified agent name (e.g. `core::react`).
- Q: What does `/agent-profile off` do — reset to default or create a null-profile state? → A: `/agent-profile off` is removed entirely. Users always switch to an explicit agent profile name; the agent's default agent profile (named after the qualified agent) is pre-selected at agent activation and can be restored by running `/agent-profile switch <agent-name>`.
- Q: How are `extra_prompts` file paths resolved? → A: Relative to the agent profile YAML file's own directory first; if not found there, resolved relative to the workspace `.pocketcode/` directory as a convenience base.
- Q: Can a plugin author give the inline `default_agent_profile` a custom name, or is it always the qualified agent name? → A: Hybrid — if the plugin author declares a `name` field inside `default_agent_profile`, that name is used; if absent, the system falls back to the qualified agent name (e.g. `core::react`).
- Q: When `/agent-profile switch` targets an agent profile for a different agent, should the CLI require confirmation or auto-proceed? → A: Auto-proceed — the CLI prints a warning that the active agent is changing and switches immediately; no y/n prompt is required.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Use an Agent Through Its Default Profile (Priority: P1)

As a developer using PocketCoder, when I switch to an agent in the CLI, the system automatically activates that agent's default agent profile — which specifies the LLM to use, the set of tools available, and the tool confirmation policies — so that the agent behaves consistently and predictably without requiring manual LLM or tool configuration every session.

**Why this priority**: This is the core behavioral change. Every agent activation now goes through an agent profile, establishing agent profiles as the fundamental unit of agent runtime configuration. All other stories depend on this foundation.

**Independent Test**: Can be fully tested by switching to any agent (e.g., `/agent core::react`) and confirming that the active agent profile shown in status matches the agent's declared default agent profile, with the correct LLM, tools, and confirmation policies applied.

**Acceptance Scenarios**:

1. **Given** a `plugin.yaml` declares `agents.react` with a `default_agent_profile` block specifying `llm_profile`, `tools`, and `tool_confirmation`, **When** the user runs `/agent core::react`, **Then** the CLI activates the agent's default agent profile and displays it as the active agent profile in the status area.
2. **Given** an agent is active via its default agent profile, **When** the user invokes a tool, **Then** the tool confirmation policy defined in the agent profile (allow/confirm/deny) is honoured for that tool call.
3. **Given** an agent is active via its default agent profile, **When** the LLM is resolved for a turn, **Then** the agent profile's `llm_profile` is used at a precedence level above the agent definition's global default but below an explicit CLI override.
4. **Given** an agent has no explicit `default_agent_profile` declared in `plugin.yaml`, **When** the user activates that agent, **Then** the system synthesises an implicit default agent profile from the agent's existing top-level fields (`llm_profile`, `tools`, `prompts`) so every agent has an agent profile without requiring migration.

---

### User Story 2 - View, Switch, and Clone Profiles from the CLI (Priority: P2)

As a developer, I want to list available agent profiles, inspect an agent profile's full configuration, switch the active agent profile, and clone an existing agent profile to create a customised variant — all without leaving the CLI session.

**Why this priority**: Agent profiles are only useful if they are discoverable and manageable interactively. This story delivers the full agent profile management surface on which customisation depends.

**Independent Test**: Can be fully tested by creating an agent profile file in `.pocketcode/agent-profiles/`, running `/agent-profile list` to see it, `/agent-profile show <name>` to inspect it, and `/agent-profile switch <name>` to activate it — all independently of any other feature story.

**Acceptance Scenarios**:

1. **Given** agent profiles exist (built-in agent defaults and workspace-local files), **When** the user runs `/agent-profile list`, **Then** all available agent profiles are displayed with their name, target agent, and LLM selection.
2. **Given** an agent profile `react-lite` exists, **When** the user runs `/agent-profile show react-lite`, **Then** the full agent profile configuration is displayed (LLM, tool list, confirmation policies, prompt sources).
3. **Given** the agent `core::react` is active, **When** the user runs `/agent-profile switch react-lite` where `react-lite` targets `core::react`, **Then** the CLI activates the `react-lite` agent profile and the status area reflects the new active agent profile name.
4. **Given** an agent profile `react-default` exists, **When** the user runs `/agent-profile clone react-default react-lite`, **Then** a new file `.pocketcode/agent-profiles/react-lite.yaml` is created as a copy of `react-default` and a confirmation message shows the file path.
5. **Given** the user has switched to a custom agent profile `react-lite` and wants to revert, **When** the user runs `/agent-profile switch core::react`, **Then** the CLI activates the agent's default agent profile and the status area reflects the default agent profile name.
6. **Given** the user runs `/agent core::react --agent-profile react-lite`, **Then** the agent switches to `core::react` and immediately activates the `react-lite` agent profile in a single command.

---

### User Story 3 - Define a Custom Workspace Profile (Priority: P3)

As a developer, I want to create a custom agent profile YAML file in `.pocketcode/agent-profiles/` that overrides a specific agent's LLM, restricts its available tools, and sets fine-grained tool confirmation policies — so I can tailor agent behaviour to my project without modifying any plugin source files.

**Why this priority**: This is the customisation payoff. A developer who understands the system can tune agent profiles to project-specific needs. It depends on stories 1 and 2 being functional.

**Independent Test**: Can be fully tested by manually creating `.pocketcode/agent-profiles/react-safe.yaml`, running `/reload`, switching to it, and confirming that only the declared tools are available and the write tool prompts for confirmation.

**Acceptance Scenarios**:

1. **Given** a user creates `.pocketcode/agent-profiles/react-safe.yaml` with a `tools` list and `tool_confirmation.overrides`, **When** the user runs `/reload` then `/agent-profile switch react-safe`, **Then** only the tools declared in the agent profile are offered and the confirmation overrides are enforced on invocation.
2. **Given** an agent profile specifies `tool_confirmation.default: confirm`, **When** any tool is called under that agent profile, **Then** the user is prompted to confirm even when no specific per-tool override exists.
3. **Given** an agent profile specifies `tool_confirmation.overrides.core::delete_file: deny`, **When** the agent attempts to invoke `core::delete_file`, **Then** the tool is rejected without prompting the user.
4. **Given** an agent profile specifies `extra_prompts: [.pocketcode/prompts/safe-mode.md]`, **When** the agent starts a turn, **Then** the content of that file is appended to the system prompt for that turn.
5. **Given** an agent profile omits the `tools` key entirely, **When** the agent profile is active, **Then** the agent inherits its full registered tool set with no restriction.

---

### Edge Cases

- What happens when `/agent-profile switch` targets an agent profile whose `agent` field does not match the currently active agent? The CLI prints a warning message stating which agent will become active, then switches both the active agent and the active agent profile automatically. No confirmation input is required from the user.
- What happens when a profile file contains invalid YAML or missing required fields? The profile is skipped at load time with a warning message; the rest of the system starts normally.
- What happens when two profile files declare the same `name` value? The last-loaded one (alphabetical file order) takes precedence and a warning is emitted identifying both files.
- What happens when a workspace-local agent profile file declares a `name` that matches a synthesised default agent profile name (i.e. equals a qualified agent name such as `core::react`)? The workspace-local file takes precedence over the synthesised default, effectively replacing it. A warning is emitted so the user is aware the agent's built-in default agent profile has been overridden.
- What happens when a plugin author declares a custom `name` inside `default_agent_profile` that collides with another agent profile's name from a different plugin or workspace file? A warning is emitted naming both sources. Plugin declaration order determines precedence (last-loaded plugin wins over earlier-loaded; workspace-local files have the lowest precedence of all).
- What happens when an agent's default profile references an LLM profile name that does not exist in the LLM registry? The system falls through to the next tier in the LLM resolution chain and logs a warning; the agent still runs.
- What happens when `/agent-profile clone` is called with a `new_name` that already exists as a file? The command fails with an explicit error message and does not overwrite the existing file.
- What happens if the user attempts to run `/agent-profile off`? The command is not recognised; the CLI returns a helpful error explaining that agent profiles cannot be deactivated and suggests `/agent-profile switch <agent-name>` to revert to the default.
- What happens when an `extra_prompts` path cannot be resolved relative to either the profile file's directory or `.pocketcode/`? The missing file is skipped with a warning; the remaining entries are still appended and the agent turn continues normally.
- What happens when the active profile restricts tools to a subset that excludes a tool the agent's internal flow expects? The tool is blocked (treated as denied), the agent receives an error result for that call, and execution continues — consistent with existing denied-tool behaviour.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every `AgentDefinition` MUST carry a default agent profile that bundles LLM selection, tool list, extra prompt sources, and tool confirmation policies. For agents that do not declare one explicitly in `plugin.yaml`, the system MUST synthesise an implicit default agent profile from the agent's existing top-level fields at load time. The name of the default agent profile follows a hybrid rule: if the plugin author provides a `name` field inside the `default_agent_profile` block, that name is used; if absent (including for all synthesised defaults), the system assigns the qualified agent identifier as the name (e.g. `core::react`). In all cases the resulting name MUST be referenceable in all CLI `/agent-profile` commands.
- **FR-002**: The CLI MUST activate an agent by loading and applying its default agent profile rather than applying the bare agent definition fields directly. The `/agent <name>` command MUST implicitly load that agent's default agent profile.
- **FR-003**: The system MUST support workspace-local agent profile files in `.pocketcode/agent-profiles/*.yaml`, loaded at startup and on `/reload`, which can target any registered agent.
- **FR-004**: Each agent profile MUST be addressable by a unique `name` string. Agent profile names MUST be unique across all sources (inline plugin declarations, synthesised agent defaults, and workspace-local files). If a plugin author declares a custom `name` inside `default_agent_profile` that collides with another agent profile name from any source, the conflict MUST emit a warning identifying both sources; the workspace-local file takes lowest precedence, the plugin declaration takes next, and a later-loaded plugin's declaration wins over an earlier-loaded one.
- **FR-005**: The CLI MUST provide the following commands: `/agent-profile list`, `/agent-profile show <name>`, `/agent-profile switch <name>`, and `/agent-profile clone <src> <new>`. There is no `/agent-profile off` command; the agent always runs under a named agent profile. To revert to an agent's default agent profile, the user runs `/agent-profile switch <qualified-agent-name>` (e.g. `/agent-profile switch core::react`).
- **FR-006**: The `/agent <name>` command MUST accept an optional `--agent-profile <name>` flag that switches the agent and activates the specified agent profile atomically.
- **FR-007**: An agent profile's `tool_confirmation` section MUST be evaluated as a distinct tier in the tool confirmation resolution chain, taking precedence over agent-level config defaults but below session-level overrides set via `/confirm`.
- **FR-008**: An agent profile's `tools` field, when present, MUST restrict the set of tools available to the agent during that session. When absent, the agent inherits its full registered tool set.
- **FR-009**: An agent profile's `extra_prompts` field MUST append additional prompt content to the agent's system prompt on each turn while the agent profile is active. File paths in `extra_prompts` MUST be resolved relative to the agent profile YAML file's own directory first; if a path is not found there, the system MUST attempt resolution relative to the workspace `.pocketcode/` directory as a convenience base. If neither location yields a file, the system MUST log a warning and skip that entry without aborting the turn.
- **FR-010**: The `/agent-profile clone <src> <new>` command MUST write a new `.pocketcode/agent-profiles/<new>.yaml` file and reload the agent profile registry. It MUST NOT overwrite an existing file of the same name.
- **FR-011**: The active agent profile name MUST be visible in the CLI status display alongside the active agent name.
- **FR-012**: An agent profile's `llm_profile` MUST be resolved at a precedence level above the agent definition's built-in `llm_profile` but below explicit CLI overrides (`/llm`, `/llm-agent`).

### Key Entities

- **AgentProfile**: A named configuration bundle targeting a specific agent. Key attributes: `name` (unique string), `agent` (qualified agent reference, e.g. `core::react`), `description`, `llm_profile` (optional, overrides agent default), `extra_prompts` (list of file paths to append to system prompt), `tools` (optional list of tool names; absent means inherit all), `tool_confirmation` (a `default` policy string plus an `overrides` dict keyed by tool name).
- **DefaultAgentProfile**: The implicit or explicit agent profile always associated with an `AgentDefinition`. A plugin may declare it inline in `plugin.yaml` under `agents.<name>.default_agent_profile`; if that block contains a `name` field, that name is used as the agent profile's identifier. If the `name` field is absent — or if no `default_agent_profile` block is declared at all — the system synthesises the default agent profile from the agent's top-level fields and assigns the qualified agent identifier as the name (e.g. `core::react`). In all cases the default agent profile is referenceable and switchable via all `/agent-profile` CLI commands without special-case syntax.
- **AgentProfileManager**: The runtime component responsible for discovering, loading, indexing, and persisting agent profile files from `.pocketcode/agent-profiles/`. Exposes lookup by name, listing, clone, and save operations.
- **ActiveAgentProfile**: The currently applied agent profile for the running session, held in engine state. Governs LLM selection, tool filtering, prompt augmentation, and confirmation policies for each agent turn.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Switching to any agent — including existing agents with no explicit agent profile declaration — completes without error, with a default agent profile automatically applied and visible in the status display.
- **SC-002**: A user can move from zero knowledge of agent profiles to having a cloned, customised workspace agent profile active in fewer than 5 CLI commands, without editing any plugin source file.
- **SC-003**: Tool confirmation policies declared in an agent profile are enforced on 100% of matching tool calls — no tool bypasses a `deny` or `confirm` policy set in the active agent profile.
- **SC-004**: Agent profile loading at startup or on `/reload` completes within the same time budget as plugin loading; no perceptible additional delay for workspaces with up to 20 agent profile files.
- **SC-005**: All existing agents continue to function correctly after the change with no user action required to migrate existing `plugin.yaml` files (full backward compatibility).
- **SC-006**: An agent profile file with invalid content is skipped with a human-readable warning and the rest of the system starts normally without crashing.

## Assumptions

- The `.pocketcode/` directory already exists (or is created on first use) for workspace-local customisation. The `agent-profiles/` subdirectory is created automatically when the first agent profile is cloned or saved.
- Agent profile YAML files use a flat, human-readable structure with no YAML anchors or advanced features required.
- `extra_prompts` paths are authored relative to the agent profile file or to `.pocketcode/`. Absolute paths are valid but discouraged as they reduce portability.
- The LLM resolution tier order in the existing system is stable and can be extended by inserting a new tier without breaking existing override behaviour.
- Workspace-local agent profile files in `.pocketcode/agent-profiles/` are the sole persistence mechanism for user-defined agent profiles; there is no account-level or server-side storage.
- An agent profile always targets exactly one agent (via its `agent` field). Cross-agent or multi-agent profiles are out of scope.
