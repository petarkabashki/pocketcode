# Feature Specification: Agents to Plugins — Core ReAct Agent Only

**Feature Branch**: `004-agents-to-plugins`  
**Created**: 2026-03-05  
**Status**: Draft  
**Input**: User description: "move all agents to plugins. In core, leave only a react agent with core tools"

## Clarifications

### Session 2026-03-05

- Q: How should the system handle stale references to old `core::coder` / `core::architect` / `core::ask` agents after migration? → A: Hard break — startup fails with a descriptive "agent not found, did you mean X?" error (no silent aliasing or transparent remapping).
- Q: Should agent Python module files physically move into each plugin's `agents/` directory, or can they remain in `core/agents/` and be referenced by path? → A: Physical move — each agent `.py` file must physically reside inside its owning plugin's `agents/` directory. No cross-plugin file references.
- Q: Which agent should be the fallback default when the user invokes PocketCoder without specifying an agent? → A: `core::react` — the generic ReAct agent in core is always the default, ensuring predictable behaviour regardless of which domain plugins are loaded.
- Q: How should the runtime resolve a handoff short-name that matches agents in multiple loaded plugins? → A: Strict — ambiguous short names cause a startup/validation error; handoff declarations must use the fully-qualified `plugin::agent` form to resolve the ambiguity.
- Q: What is the implementation basis for the new `core::react` agent, and should the existing `single_agent` flow be retained? → A: New purpose-built ReAct implementation — do not reuse the `single_agent` flow pattern. The `single_agent` flow, its prompt files, and its node prompts MUST be removed from `core`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Core plugin exposes a single generic ReAct agent (Priority: P1)

A developer invoking any PocketCoder command is served by a clean, minimal `core` plugin that contains exactly one agent: a general-purpose ReAct (Reason + Act) agent backed by core tools. There are no domain-specific agents (`coder`, `architect`, `ask`) left in the core plugin manifest.

**Why this priority**: This is the foundational change. All other stories depend on the core plugin being trimmed first. A minimal core is the primary goal of the feature.

**Independent Test**: Configure and run PocketCoder with only the `core` plugin enabled. The system must start successfully and the single ReAct agent must be selectable and able to complete a tool call.

**Acceptance Scenarios**:

1. **Given** the `core` plugin's `plugin.yaml`, **When** it is loaded at startup, **Then** only one agent (`react`) is registered under the `core` namespace and no `coder`, `architect`, or `ask` agents are present in that namespace.
2. **Given** a user invokes the `core::react` agent, **When** the agent receives a task, **Then** it reasons, calls a core tool, receives the tool result, and produces a final answer — completing a full ReAct loop.
3. **Given** the `core` plugin is loaded without any other plugins, **When** PocketCoder starts, **Then** no import errors or missing-agent errors occur.

---

### User Story 2 — Domain agents migrate to their own plugins (Priority: P1)

Each domain agent currently defined in `core` (`coder`, `architect`, `ask`) is moved into its dedicated plugin (`coder`, `architect`, `asker`) that already exists in the codebase. These plugins become the canonical home for those agents, with their own `plugin.yaml` manifests registering the agents correctly.

**Why this priority**: Co-equal priority with Story 1 — the two stories are two sides of the same change. Moving agents out of core is meaningless without them landing somewhere functional.

**Independent Test**: Enable only the `coder` plugin (plus `core` for tools). Invoke `coder::coder`. The agent must execute its full workflow using tools sourced from `core` without errors.

**Acceptance Scenarios**:

1. **Given** the `coder` plugin is loaded, **When** its manifest is parsed, **Then** a `coder` agent is registered under the `coder` namespace with the same tool bindings and handoff targets it had in `core`.
2. **Given** the `architect` plugin is loaded, **When** its manifest is parsed, **Then** an `architect` agent is registered under the `architect` namespace.
3. **Given** the `asker` plugin is loaded, **When** its manifest is parsed, **Then** an `ask` agent is registered under the `asker` namespace.
4. **Given** all three domain plugins are enabled alongside `core`, **When** PocketCoder starts, **Then** agents from all three plugins are discoverable and the system reports no duplicate or missing registrations.

---

### User Story 3 — Handoff routing works across plugin boundaries (Priority: P2)

When a domain agent (e.g., `coder::coder`) requests a handoff to another agent (e.g., `architect`), the runtime resolves the target agent across plugin boundaries. Handoff declarations in each plugin's manifest reference agents by their new namespaced or short names, and the agent runtime correctly routes between plugins.

**Why this priority**: Handoffs are a key collaboration mechanism. Without correct cross-plugin handoffs, multi-agent workflows break — but this can be stabilized after the core migration (P1) is complete.

**Independent Test**: Run a task where `coder::coder` triggers a handoff to `architect`. Verify the conversation continues inside `architect::architect` without error.

**Acceptance Scenarios**:

1. **Given** `coder::coder` is configured with `handoff_agents: [architect::architect, asker::ask]`, **When** the agent triggers a handoff, **Then** the runtime locates `architect::architect` in the `architect` plugin and `asker::ask` in the `asker` plugin without ambiguity.
2. **Given** an agent in any plugin requests a handoff to a non-existent agent, **When** the runtime attempts resolution, **Then** a descriptive error is raised identifying the missing target.

---

### Edge Cases

- What happens if a user loads only `core` and requests `coder` (which no longer exists in `core`)? The system MUST fail with a descriptive error: "Agent 'core::coder' not found. Did you mean 'coder::coder'? Enable the 'coder' plugin to use it." No silent fallback or crash.
- What happens if a user config (`pocketcode.yml`) or plugin manifest contains a reference to `core::coder`, `core::architect`, or `core::ask` after migration? Startup MUST abort with the same descriptive "agent not found" hard-break error, naming the stale reference and its suggested replacement.
- What happens if both an old `core`-registered agent and a new plugin-registered agent with the same short-name coexist during transition? The system must detect the conflict and raise a configuration error.
- What happens if a plugin agent references a core tool that is not loaded? Tool resolution must fail with a descriptive error pointing to the missing tool.
- What happens if two loaded plugins both register an agent with the same short name (e.g., `architect`)? Any handoff declaration using that bare short name MUST cause a startup/validation error requiring use of the fully-qualified `plugin::agent` form.
- What happens if the `micromanager` plugin references `core::coder` after that agent has been removed from `core`? Its manifest must be updated before the change is considered complete.
- What happens when a user runs `pocketcode` with no agent specified and no domain plugins enabled? The system MUST successfully invoke `core::react`, which is always available.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `core` plugin's `plugin.yaml` MUST define exactly one agent entry, named `react`, after this change.
- **FR-002**: The `react` agent in `core` MUST have access to all tools currently listed in the `core` plugin's tool registry (filesystem, search, system, git, user_input, context_elephant_store).
- **FR-003**: The `coder` plugin MUST define a `coder` agent with the same capabilities (tools, LLM profile, handoff targets) that `core::coder` had, adjusted for cross-plugin handoff references.
- **FR-004**: The `architect` plugin MUST define an `architect` agent with the same capabilities that `core::architect` had.
- **FR-005**: The `asker` plugin MUST define an `ask` agent with the same capabilities that `core::ask` had.
- **FR-006**: Each plugin's agent module files (Python) that were previously housed in `core/agents/` MUST be physically moved into their respective plugin's `agents/` directory (e.g., `coder/agents/coder_agent.py`). Cross-plugin file references from manifests to files in `core/agents/` are not permitted.
- **FR-007**: Handoff agent references in all plugin manifests MUST be updated so the runtime can resolve them across plugin boundaries without ambiguity. If a handoff target short name (e.g., `architect`) matches agents in more than one loaded plugin, the system MUST raise a startup/validation error and require the fully-qualified `plugin::agent` form (e.g., `architect::architect`). No silent first-win resolution is permitted.
- **FR-008**: The `micromanager` plugin's manifest and agent references MUST be reviewed and updated to point to agents in their new plugin locations.
- **FR-009**: Existing integration tests MUST continue to pass, or be updated to reflect the new plugin namespacing, with zero net-new test failures.
- **FR-010**: The system MUST NOT break when any single domain plugin is disabled — disabling `coder` must not prevent `architect` or `asker` from functioning independently.
- **FR-011**: When no agent is specified by the user at invocation time, the system MUST default to `core::react`. This default MUST be hardcoded and MUST NOT depend on any domain plugin being present.
- **FR-012**: The `core::react` agent MUST be implemented as a purpose-built ReAct (Reason → Act → Observe) loop. It MUST NOT delegate to or reuse the `single_agent` flow pattern.
- **FR-013**: The `single_agent` flow definition, its associated prompt files (`core/prompts/flows/single_agent.md`, `core/prompts/nodes/single_agent/`), and any manifest references to it MUST be removed from the `core` plugin as part of this feature.

### Key Entities

- **Core Plugin**: The `core` built-in plugin providing shared tools and a single generic ReAct agent. After this change its `agents` section contains only `react`.
- **Domain Plugin** (`coder`, `architect`, `asker`): A plugin that owns one or more domain-specific agents and declares those agents in its own `plugin.yaml`. Tool bindings may reference tools from `core` or from the plugin itself.
- **ReAct Agent**: A general-purpose agent that follows the Reason → Act → Observe loop. Registered as `core::react`. Backed by the full set of core tools. Implemented as a new, purpose-built execution loop — not derived from the `single_agent` flow pattern.
- **single_agent flow** *(removed)*: The prior built-in flow for single-agent execution, previously shipped in `core/prompts/flows/single_agent.md`. This flow and all its prompt files are removed as part of this feature.
- **Agent Manifest Entry**: The YAML block within a `plugin.yaml` that registers an agent with its module path, entry function, LLM profile, tools, and handoff targets.
- **Handoff Target**: A reference from one agent's manifest to another agent it may transfer control to. Must be resolvable to a concrete `plugin::agent` pair at runtime.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After the change, `core/plugin.yaml` contains exactly 1 agent entry (`react`), verifiable by manifest inspection.
- **SC-002**: `coder`, `architect`, and `asker` plugins each register their respective domain agents, verifiable by manifest inspection and runtime agent-discovery output.
- **SC-003**: All existing integration tests pass (or are updated and pass) within a single test run with zero regressions introduced by this migration.
- **SC-004**: A full multi-agent handoff sequence (e.g., `coder::coder` → `architect::architect` → `coder::coder`) completes successfully end-to-end after the migration.
- **SC-005**: The `core` plugin loads and the `react` agent executes a tool call in under 5 seconds on a warm system, confirming no performance regression from the restructuring.
- **SC-006**: Disabling any single domain plugin results in a clean startup with only that plugin's agents absent — no cascading failures to other loaded plugins.
- **SC-007**: The `core` plugin contains no `single_agent` flow files or prompt nodes after the migration, verifiable by filesystem inspection of `core/prompts/flows/` and `core/prompts/nodes/`.

## Assumptions

- The existing `coder`, `architect`, and `asker` plugin directories are the correct destinations for their respective agents. No new plugin directories need to be created for this feature.
- Tool resolution across plugins follows the convention already established by the unified plugin namespace feature (spec 003): domain plugins can reference tools from `core` by short name.
- The LLM profiles (`gemini_default`, `gemini_fast`) remain unchanged and are not part of this migration.
- The `micromanager` plugin may reference domain agents; its manifest will need updating but no new Python logic is required in its agent code — only manifest corrections.
- The Python agent module files (e.g., `coder_agent.py`) will be physically moved into their owning plugin's `agents/` directory (e.g., `coder/agents/coder_agent.py`). Files MUST NOT remain in `core/agents/`. Stale `__pycache__` entries in `core/agents/` will be removed as part of the cleanup.
- The `single_agent` flow and all associated prompt files (`core/prompts/flows/single_agent.md`, `core/prompts/nodes/single_agent/think.md`) are removed. The `core::react` agent uses a new, self-contained ReAct implementation.
- There is NO backward-compatible aliasing: any configuration or manifest referencing `core::coder`, `core::architect`, or `core::ask` after this migration MUST be updated. The system will hard-fail at startup with a descriptive error message pointing to the correct replacement agent name.
