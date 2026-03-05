# Feature Specification: Refactor Plugin Structure and Composition

**Feature Branch**: `001-refactor-plugin-structure`  
**Created**: 2026-03-05  
**Status**: Draft  
**Input**: User description: "analyse the composition patterns and implementation and remove obsolete and redundant stuff. Check mode_flows , workflows and plugins and tools folders. Each plugin should be self-contained in its own folder. use the pocketflow.py code as the core orchestration framework."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - User-Supplied Agent Plugins (Priority: P1)

A user provides their own persona or specialized agent as a self-contained plugin folder. The system loads the agent's definition, tools, and preferred workflows using `pocketflow.py` for orchestration without requiring core code changes.

**Why this priority**: Shifting from hardcoded modes to user-supplied agents is the central architectural goal.

**Independent Test**: Create a temporary `plugins/test_plugin` folder with a simple workflow, prompt, and tool, and verify it can be run via the CLI/Engine.

**Acceptance Scenarios**:

1. **Given** a self-contained plugin folder structure, **When** the system initializes, **Then** all internal resources (prompts, tools, workflows) are correctly scoped to that plugin.
2. **Given** a workflow in a plugin, **When** it references a tool, **Then** it first looks for the tool within its own plugin folder before falling back to core tools.

---

### User Story 2 - Minimal PocketFlow Orchestration (Priority: P1)

The system uses `pocketflow.py` as the direct orchestration engine. Custom logic for flow control is minimized, relying on the built-in `Flow` and `Node` patterns rather than complex extension classes.

**Why this priority**: Ensures that the core remains lightweight and that orchestration behavior is predictable and standard.

**Independent Test**: Execute the "orchestrator" workflow and verify it uses `pocketflow.Flow` and `pocketflow.Node` for execution transitions.

**Acceptance Scenarios**:

1. **Given** a workflow definition, **When** it is loaded, **Then** it is compiled into a `pocketflow.Flow` structure.
2. **Given** an executing flow, **When** a node finishes with a transition label, **Then** `pocketflow` correctly routes to the successor node.

---

### User Story 3 - Removal of Obsolete Flow Implementations (Priority: P2)

Redundant flow logic in `pocketcode/mode_flows/` is removed or migrated to the new plugin-based architecture.

**Why this priority**: Cleans up the codebase and removes confusion between different execution paths.

**Independent Test**: Verify that `pocketcode/mode_flows/` contains only base classes or is removed if no longer needed.

**Acceptance Scenarios**:

1. **Given** the new architecture is in place, **When** specific modes (architect, coder, etc.) are called, **Then** they execute via the `plugins` workflow system rather than hardcoded Python flows.

### Edge Cases

- **Circular Dependencies**: Prevent plugins from importing each other directly; use shared core abstractions.
- **Missing Internal Resources**: Gracefully handle cases where a plugin is missing its `tools/` or `workflows/` directory.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST resolve user-supplied agent definitions (personas, prompts, tools).
- **FR-002**: Orchestration MUST be minimal, using `pocketflow.py` classes (`Flow`, `Node`, `AsyncFlow`) with minimal extensions only when mandatory.
- **FR-003**: User-supplied tools MUST be discoverable dynamically from the agent's plugin folder.
- **FR-004**: System MUST maintain the "Recursive Agent" pattern using standard `pocketflow.Flow` instances as nodes where possible.
- **FR-005**: Obsolete hardcoded flows in `mode_flows/` MUST be removed.
- **FR-006**: Core tools (filesystem, git, etc.) MUST remain in a shared `pocketcode/tools/` folder.

### Key Entities *(include if feature involves data)*

- **Agent Plugin**: A user-supplied folder containing `agent.yaml`, local prompts, tools, and a thin `pocketflow` definition.
- **WorkflowRuntime**: An adapter that maps `WorkflowDefinition` to `pocketflow.Flow`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- SC-001: Total lines of redundant flow logic code decreased by 30%.
- SC-002: 100% of existing modes (Archi, Code, Ask) migrated to the self-contained plugin structure.
- SC-003: Performance overhead of loading a self-contained plugin is under 100ms.
- SC-004: No "import" cycles between `core` and `plugins` folders.
