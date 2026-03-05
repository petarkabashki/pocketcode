# Feature Specification: PocketFlow Agents and Plugin Factory

**Feature Branch**: `002-pocketflow-agents`  
**Created**: 2026-03-05  
**Status**: Draft  
**Input**: User description: "agents should be only based on pocketflow rather than workflow dot descriptions. Plugins should have factory function returning the tools, prompts and agents they contain."

## Clarifications

### Session 2026-03-05
- Q: How should the plugin factory return its tools, prompts, and agents? → A: Return an instance of a `Plugin` class (Object-oriented).
- Q: How should Nodes access local plugin context? → A: Auto-inject context into `shared`.
- Q: Should tool/prompt configuration move out of YAML? → A: Pure Python (Flows define their own toolsets).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create and Run a PocketFlow Agent (Priority: P1)

As a developer, I want to define my agent's logic directly using PocketFlow's Node and Flow classes (Python-based), so that I have full programmatic control over the agent's behavior without relying on external YAML/Markdown workflow descriptions.

**Why this priority**: This is the core shift from descriptive workflows to programmatic ones, enabling more complex and maintainable agent logic.

**Independent Test**: Can be fully tested by creating a plugin with a PocketFlow-based agent and running it through the CLI to verify it executes the defined flow and reaches the expected outcome.

**Acceptance Scenarios**:

1. **Given** a plugin that defines an agent as a `pocketflow.Flow`, **When** the agent is executed, **Then** the Flow's nodes are executed in the defined sequence.
2. **Given** an agent defined in PocketFlow, **When** it encounters a conditional branch (e.g., `-action >> next_node`), **Then** it correctly follows the path based on the node's returned action.

---

### User Story 2 - Plugin Factory Registration (Priority: P1)

As a developer, I want to use a single factory function in my plugin to register its tools, prompts, and agents, so that the plugin structure is clean, centralized, and easy for the system to discover and initialize.

**Why this priority**: This streamlines the plugin loading process and ensures consistency across all plugins.

**Independent Test**: Can be tested by verifying that the `PluginManager` can discover and load tools, prompts, and agents from a plugin that provides a factory function, and that these resources are available to the LLM and the runtime.

**Acceptance Scenarios**:

1. **Given** a plugin directory, **When** the system loads the plugin, **Then** it calls a designated factory function to retrieve the plugin's components.
2. **Given** a factory function, **When** it returns a dictionary or object containing tools and agents, **Then** these tools and agents are registered in the global registry.

---

### User Story 3 - Accessing Prompts within PocketFlow Nodes (Priority: P2)

As a developer, I want to easily access my plugin's prompts from within my PocketFlow nodes, so that I can inject them into LLM calls easily.

**Why this priority**: Agents core functionality depends on prompts; easy access is essential for a good developer experience.

**Independent Test**: Can be tested by creating a node that retrieves a prompt by name from its plugin context and uses it.

**Acceptance Scenarios**:

1. **Given** a node within an agent belonging to Plugin A, **When** it requests a specific prompt, **Then** it receives the correct prompt content defined in Plugin A.

### Edge Cases

- **Circular Dependencies**: What happens if two plugins' factories depend on each other?
- **Missing Resource**: How does the system handle an agent that refers to a tool not returned by the plugin's factory (or any other factory)?
- **Factory Errors**: How are exceptions within a factory function handled during plugin discovery?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support agent definitions using `pocketflow.Flow` and `pocketflow.Node` exclusively.
- **FR-002**: Each plugin MUST provide a factory function (e.g., `get_plugin()`) that returns its tools, prompts, and agents via a `Plugin` class instance.
- **FR-003**: THE plugin's `agent.yaml` MUST remain as the structural indicator but can now reference a factory (e.g., via `factory: true` or `handler: get_plugin`) to specify programmatic tool/prompt/agent discovery.
- **FR-004**: PocketFlow agents MUST have access to the plugin's prompt library and toolset during execution via a `PluginContext` automatically injected into the `shared` dictionary.
- **FR-005**: The system MUST allow for both synchronous (`Flow`) and asynchronous (`AsyncFlow`) PocketFlow agents to provide developer flexibility.
- **FR-006**: Factory functions MUST return an instance of a `Plugin` class that encapsulates tools, prompts, and agents for better type safety and validation.
- **FR-007**: System MUST support hierarchical prompt management (global vs. plugin-specific).

### Key Entities *(include if feature involves data)*

- **PluginFactory**: A function within a plugin's `__init__.py` or similar entry point that returns a `Plugin` object.
- **Plugin**: A container object holding the plugin's metadata, `tools` (list of functions/classes), `prompts` (dictionary of prompt strings), and `agents` (mapping of names to `pocketflow.Flow` instances).
- **PocketFlowAgent**: An agent implementation where the logic is defined as a `pocketflow.Flow`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Developers can define a complete agent (logic + tools + prompts) entirely in Python code in under 5 minutes (assuming logic is known).
- **SC-002**: Plugin discovery and initialization time remains under 500ms for projects with up to 20 plugins.
- **SC-003**: 100% of existing workflow-description-based features can be represented using PocketFlow agents.
- **SC-004**: Code duplication for tool/prompt registration across different agents within the same plugin is reduced by at least 50% due to the centralized factory.

## Assumptions

- **A-001**: We will provide a base class or decorator for PocketFlow nodes to easily access the `shared` state and `Plugin` resources.
- **A-002**: The existing `pocketflow.py` implementation is sufficient for current orchestration needs or can be extended incrementally.
- **A-003**: We will maintain backward compatibility for a transition period or migrate all existing plugins to the new format.
