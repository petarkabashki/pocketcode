# Feature Specification: Unified Plugin Namespace Architecture

**Feature Branch**: `003-unified-plugin-namespace`  
**Created**: 2026-03-05  
**Status**: Draft  
**Input**: User description: "Move the core tools into the core plugin. Make agents, prompts and tools referenceable by namespace(the plugin). Simplify and unify the architecture for maximum flexibility."

## Overview

PocketCoder currently stores core tools in a standalone package separate from the plugin system. Different plugin manifest formats exist (`agent.yaml` vs `plugin.yaml`) creating inconsistency, all tools are registered in a single flat global registry with no namespacing, and declarative workflow files exist as a parallel execution concept alongside agents. This feature consolidates all resources — tools, agents, and prompts — into a unified plugin-scoped namespace model where every resource is owned and identified by its plugin. Declarative workflows are eliminated as a separate concept: all execution graphs (simple single-node agents through complex multi-agent orchestrators) are expressed as PocketFlow-based agents using PocketFlow's `Flow` + `Node` graph abstraction. This unifies the execution model: one concept (Agent = PocketFlow Flow) spans the full range from a single LLM call to a multi-step orchestration pipeline.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Core Tools Consolidated in Core Plugin (Priority: P1)

As a plugin author, I want all built-in system tools (file operations, git, shell, search, user input) to live inside the core plugin directory so that the core plugin is a self‑contained, inspectable unit and I can understand the full capability of any plugin just by looking at its directory.

**Why this priority**: This is the structural foundation required by all other stories. Without collocating tools in their owning plugin, namespace references have no canonical home.

**Independent Test**: Can be fully tested by starting the system with only the core plugin active and verifying all previously available core tools are still operational when referenced from an agent definition.

**Acceptance Scenarios**:

1. **Given** the system starts fresh, **When** the core plugin is loaded, **Then** all system tools (read/write file, git operations, shell exec, search, user-input prompts) are registered and available without any code changes to external packages.
2. **Given** a plugin author inspects the core plugin directory, **When** they look at the tools/ folder, **Then** all core tool implementations are present there alongside the plugin manifest.
3. **Given** an agent in the core plugin references a tool by its local name, **When** the system resolves the tool, **Then** it resolves from the owning plugin first before searching elsewhere.

---

### User Story 2 - Namespace-Qualified Resource References (Priority: P2)

As a plugin author, I want to reference any tool, agent, or prompt using a `plugin_name.resource_name` notation in my manifest so that I can unambiguously address any resource in the system regardless of how many plugins are loaded.

**Why this priority**: Namespacing eliminates name collisions between plugins, enables cross-plugin resource sharing, and provides explicit provenance for every resource reference.

**Independent Test**: Can be fully tested by creating two plugins that each define a tool with the same local name, then writing an agent that references each by its namespaced form and confirming both are correctly resolved to their respective implementations.

**Acceptance Scenarios**:

1. **Given** two plugins both define a tool named `write_to_file`, **When** an agent references `core.write_to_file`, **Then** only the core plugin's implementation is used.
2. **Given** an agent in plugin `koder` references `core.read_file`, **When** the system resolves the reference, **Then** it loads the tool from the core plugin without ambiguity.
3. **Given** a prompt file is declared inside a plugin, **When** another plugin's agent references it as `plugin_name.prompt_name`, **Then** the correct prompt content is loaded from the declaring plugin.
4. **Given** a resource is referenced by its unqualified local name (no dot), **When** it belongs to the same plugin, **Then** the system resolves it to the owning plugin's resource without requiring an explicit prefix.

---

### User Story 3 - Single Unified Plugin Manifest Format (Priority: P3)

As a plugin author, I want a single, consistent manifest format for all plugins so that I do not need to learn two different schemas (`agent.yaml` vs `plugin.yaml`) and so that tooling, documentation, and validation can treat all plugins uniformly.

**Why this priority**: A unified format reduces cognitive overhead, simplifies validation, and makes the system easier to extend with new plugin capabilities in the future.

**Independent Test**: Can be fully tested by converting one existing plugin from each format to the unified format and confirming the system loads both correctly with identical runtime behavior.

**Acceptance Scenarios**:

1. **Given** a plugin uses the unified manifest format, **When** the system loads it, **Then** it recognises all sections (tools, agents, prompts, llm_profiles) without special-casing the format. There is no separate `workflows:` section — multi-step pipelines are expressed as agents with PocketFlow graph definitions.
2. **Given** a plugin declares multiple agents in a single manifest file, **When** the system loads it, **Then** all agents are registered under the plugin's namespace.
3. **Given** a plugin declares tools in a `tools/` subdirectory, **When** an agent within the same plugin references those tools by local name, **Then** they resolve without the author specifying absolute module paths.
4. **Given** a plugin declares an orchestrating agent whose PocketFlow graph nodes delegate to other named agents (sub-flows), **When** the system loads it, **Then** those sub-agent references are resolved using the same namespace rules as tool references.
5. **Given** a legacy `agent.yaml` plugin exists, **When** the system starts, **Then** it either loads it transparently by mapping to the unified format, or emits a clear migration warning indicating what needs to change.

---

### User Story 4 - No Regressions for Existing Agents (Priority: P1)

As a developer maintaining the existing system, I want all existing agents (Coder, Architect, Ask, micromanager) and their workflows to continue functioning identically after the refactor so that no user-visible behavior changes during the migration.

**Why this priority**: A refactor that breaks running agents provides no net gain. Backward compatibility is a gate condition for shipping.

**Independent Test**: Can be fully tested by running the existing integration test suite against the refactored system and confirming all tests pass without modification to test files.

**Acceptance Scenarios**:

1. **Given** the refactored system is started, **When** an existing agent workflow is invoked, **Then** it executes with the same tools, prompts, and handoff behavior as before the refactor.
2. **Given** an agent references a tool by its old unqualified name, **When** the system resolves it, **Then** it resolves correctly (via backward-compatible aliasing or automatic namespace inference) without requiring immediate manifest updates.

---

### Edge Cases

- What happens when two different plugins declare the same qualified name (e.g., both name themselves `core`)? The system MUST treat this as a hard error at load time: the later-loaded conflicting plugin MUST be skipped entirely, and an error MUST be emitted naming both plugins and the exact colliding resource name. No winner is silently chosen.
- What happens when a namespaced reference points to a plugin that is not loaded? The system MUST emit a clear error at load time naming the missing plugin and the referencing agent.
- What happens when a tool implementation file is missing from the plugin's tools directory? The system MUST log an actionable error and skip registering the broken tool rather than crashing the entire plugin load.
- What happens when a prompt referenced by agent A is defined in plugin B which is not active? The system MUST fail with a descriptive error rather than silently providing an empty prompt.
- How does the system resolve a bare tool name that exists in multiple loaded plugins? It MUST require an explicit qualifying namespace and refuse to guess, returning an error that lists all matching plugins.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support a single canonical plugin manifest format that encompasses all resource types: tools, agents, prompts, and LLM profiles. There is no separate workflow resource type — all execution graphs, whether single-node or multi-step orchestration pipelines, are declared as agents with PocketFlow `Flow` + `Node` graph definitions. All resource types MUST participate equally in the plugin namespace model. Every manifest MUST declare a top-level `schema_version: 1` integer field; the loader MUST emit a hard error and skip the plugin if the field is absent or holds an unrecognised value.
- **FR-002**: The system MUST load all core tool *registrations* from within the core plugin directory. The existing standalone tools package MAY remain as an internal shared library whose classes are importable, but it MUST NOT serve as the registration source for any plugin's tools. The core plugin's own manifest and tools directory are the sole authoritative registration point for all core tools.
- **FR-003**: Every tool, agent, and prompt registered by a plugin MUST be addressable using a `plugin_name.resource_name` qualified reference in addition to its local name. No resource type is exempt from namespace qualification. Agents that compose other agents reference the sub-agents by their qualified name (`plugin_name.agent_name`).
- **FR-004**: Within a plugin's own manifest, resources MAY be referenced by their local name alone (without prefix), and the system MUST resolve them to the owning plugin.
- **FR-005**: The system MUST detect and report name collisions between plugins at load time rather than silently overwriting an existing registration. Collisions MUST be emitted as `ERROR`-level log records via Python's `logging` module, written to stderr, naming both conflicting plugins and the exact colliding resource.
- **FR-006**: During the transition period, when an agent references a resource by its unqualified local name and exactly one loaded plugin owns a resource with that name, the system MUST resolve it to that plugin and emit a `WARNING`-level log record via Python's `logging` module identifying the reference, the resolved plugin, and the recommended qualified form. When more than one plugin owns a resource with that name the system MUST emit an `ERROR`-level log record (identical to FR-005 collision behavior) and refuse to guess.
- **FR-007**: The system MUST expose a unified discovery interface that allows any component to enumerate all available tools, agents, and prompts grouped by their owning plugin namespace.
- **FR-008**: Adding a new tool to the system MUST require changes only within the owning plugin's directory — no modifications to packages, modules, or files outside the plugin folder are needed.
- **FR-009**: The system MUST allow prompts to be declared as named resources within a plugin, enabling other plugins to reference them by qualified name.
- **FR-010**: The plugin loading order MUST be deterministic. When two plugins register a resource under the same qualified name, the system MUST treat this as a hard error: the conflicting plugin MUST be skipped (not loaded), an error MUST be emitted naming both plugins and the colliding resource, and no silent winner is ever chosen.
- **FR-011**: The Namespace Registry MUST support full hot-reload — when any plugin file changes at runtime, the registry MUST rebuild into a new snapshot and atomically swap the active reference so that new sessions immediately use the updated registry. Sessions that were already in-flight at the moment of the swap MUST continue using their pre-reload registry snapshot until they complete naturally. No process restart is required and no in-flight session is interrupted.
- **FR-012**: Every agent declaration in the plugin manifest MUST reference a Python module and entry function that constructs and returns the PocketFlow `Flow` object for that agent (via `module:` and `entry_fn:` keys in the agent block). Simple agents (single LLM call) and complex orchestrating agents (multi-node, multi-agent pipelines) share the same `agents:` manifest section and the same runtime execution path — both point to a Python function returning a `Flow`. There is no separate workflow declaration or workflow runtime, and no inline YAML graph DSL.

### Key Entities

- **Plugin**: The fundamental unit of organisation. Identified by a unique name (namespace). Owns zero or more tools, agents, and prompts. Self-contained within a single directory.
- **Tool**: A callable capability owned by a plugin. Identified within the system as `plugin_name.tool_name`. Implementations reside within the plugin's own directory.
- **Agent**: A PocketFlow `Flow` owned by a plugin. Identified as `plugin_name.agent_name`. Spans the full spectrum from a single-node LLM call to a multi-node, multi-agent orchestration pipeline — the distinction is purely in how many `Node`s and sub-flows the `Flow` contains. Declared in the manifest via `module:` (relative Python module path within the plugin) and `entry_fn:` (a zero-argument factory function that returns the `Flow`). Declares which tools it uses, which prompts guide it, and which other agents it delegates to (as nested PocketFlow sub-flows) — all via qualified references. There is no separate workflow concept: an orchestrating agent (e.g. micromanager) is simply an Agent whose PocketFlow graph composes other agents as sub-flows.
- **Prompt**: A named text resource owned by a plugin. Identified as `plugin_name.prompt_name`. Can be referenced across plugins via qualified reference.
- **Namespace Registry**: The runtime structure that maps qualified names (`plugin.resource`) to their loaded implementations, covering tools, agents, and prompts. Replaces the current flat global tool/agent dictionaries. MUST support atomic snapshot-swap hot-reload: on any plugin file change the registry rebuilds into a new snapshot, atomically replaces the active reference, and allows in-flight sessions to drain against their pre-reload snapshot without interruption.
- **Plugin Manifest**: The declarative file describing a plugin's identity, owned resources, and inter-plugin references. A single unified format covers all plugin types and all resource categories. MUST contain a top-level `schema_version: 1` integer field (hard error if absent or unrecognised). The `agents:` section is the sole declaration point for all execution graphs regardless of complexity.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing integration tests pass without any modifications to test files after the refactor is complete.
- **SC-002**: A new tool can be added to any plugin and made available to agents in under 5 minutes, requiring edits to no more than 2 files (the tool implementation and the plugin manifest).
- **SC-003**: Zero name-collision silent overwrites occur at system startup — every collision produces a logged warning or error.
- **SC-004**: A plugin author can create a fully functional new plugin — with its own tools and an agent that uses them — without reading or modifying any file outside the new plugin's directory.
- **SC-005**: All qualified resource references (`plugin_name.resource_name`) resolve correctly across all loaded plugins in a system with at least 4 simultaneously active plugins.
- **SC-006**: The core plugin is fully self-contained: all its tools and capabilities load and operate correctly without any resource defined outside the plugin's own directory, verified by confirming no external tool-package dependency is needed for the system to start and run standard workflows.
- **SC-007**: When any plugin file is modified at runtime, the system reloads all plugins and rebuilds the Namespace Registry within 5 seconds without requiring a process restart, and any agent session started after the reload uses the updated registrations (including updated PocketFlow graph definitions for orchestrating agents).

## Clarifications

### Session 2026-03-05

- Q: When two plugins register a resource under the same qualified name, which wins? → A: Hard error — collision halts the later-loaded plugin and requires the author to use a qualified reference; no winner is ever chosen silently.
- Q: How should unqualified cross-plugin references be handled during the transition period? → A: Warn but resolve — if exactly one plugin owns the name, resolve it and emit a deprecation warning; if multiple plugins match, hard error immediately.
- Q: What happens to the existing standalone `pocketcode/tools/` package? → A: Retained as an internal shared library (classes remain importable); all tool registrations move to the core plugin's own directory. Full package removal deferred to a later cleanup cycle.
- Q: Are workflows included in the plugin namespace model alongside tools, agents, and prompts? → A: Workflows are eliminated as a separate concept. All execution graphs — from single LLM calls to multi-step orchestration pipelines — are expressed as PocketFlow-based agents and declared in the `agents:` section of the plugin manifest. What was previously called a "workflow" is now an orchestrating Agent whose PocketFlow `Flow` composes other agents as nested sub-flows. This unifies the execution model: one concept (Agent = PocketFlow Flow) covers the full range.
- Q: Must the Namespace Registry support hot-reload when plugin files change at runtime? → A: Yes — full hot-reload required; registry must rebuild cleanly on any file change without a process restart and without corrupting in-flight sessions.
- Q: How is an agent's PocketFlow graph declared in the plugin manifest? → A: Via `module:` and `entry_fn:` keys in the agent block — the entry function is a zero-argument Python factory that constructs and returns the `Flow` object. No inline YAML graph DSL.
- Q: How does the Namespace Registry protect in-flight sessions during hot-reload? → A: Snapshot isolation — the registry rebuilds into a new snapshot and atomically swaps the active reference; running sessions retain their pre-reload snapshot and drain to completion without interruption.
- Q: Does the plugin manifest need a schema version field? → A: Yes — `schema_version: 1` is a required top-level integer field; the loader emits a hard error and skips the plugin if it is absent or holds an unrecognised value.
- Q: What is the plugin trust model? → A: Trusted-only — all plugins are considered authored or explicitly installed by the user; no sandboxing, capability restrictions, or signature verification are required in this version.
- Q: How are collision and deprecation warnings surfaced to plugin authors? → A: Structured log records via Python's `logging` module — `WARNING` level for unqualified-reference deprecations, `ERROR` level for collisions and missing-plugin references — written to stderr and readable by any log handler the host configures.

## Assumptions

- The plugin name declared in the manifest is treated as the authoritative namespace identifier; plugin directory name serves as a fallback only.
- Backward compatibility for unqualified cross-plugin references follows a warn-but-resolve policy for one release cycle: if exactly one plugin owns the name it is resolved with a deprecation warning; if multiple plugins own the name it is a hard error immediately. After the transition period all unqualified cross-plugin references become hard errors regardless of match count.
- Prompt files are referenced by their declared name within the plugin manifest, not by raw file path, when used in cross-plugin references.
- The existing standalone tools package is retained as an internal shared library — tool classes remain importable by tests and internal components, but no plugin manifest references it as a registration source. The core plugin's `tools/` directory holds registrations; implementations may delegate to the shared library. Full removal of the standalone package is deferred to a subsequent cleanup cycle.
- The unified manifest format uses `plugin.yaml` as the filename (currently used by the core plugin) rather than `agent.yaml`.
- All `plugin.yaml` files MUST include `schema_version: 1` as the first top-level key. Legacy `agent.yaml` files do not carry this field and will trigger a migration warning on load.
- Plugins that currently use `agent.yaml` with a single implicit agent will map cleanly to the unified format with a single `agents:` entry.
- Existing declarative workflow files (e.g. any `workflows/` directory YAML files) are migrated to agent declarations in the `agents:` section of the plugin manifest. Their PocketFlow graph structure (nodes and transitions) is expressed inline or via a referenced Python module. No runtime `workflow_runtime.py` is needed once all workflows are expressed as PocketFlow agents.
- An "orchestrating agent" (the successor to a standalone workflow) is architecturally identical to any other agent — it is a PocketFlow `Flow` whose nodes delegate to other agents (sub-flows) rather than calling an LLM directly. The micromanager plugin is the primary example of this pattern.
- All plugins are treated as trusted code authored or explicitly installed by the user. No sandboxing, capability manifest, or signature verification is in scope for this version. Plugin code executes with the same permissions as the host process.
