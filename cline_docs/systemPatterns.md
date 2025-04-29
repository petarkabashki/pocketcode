# System Patterns: Pocketcode

## Core Architecture

*   **Framework:** Built upon the PocketFlow framework (Python). This implies leveraging PocketFlow's concepts for workflows, modes (agents), tools, and state management.
*   **Modularity:** Designed for high modularity. Core components (modes, tools, workflows) should be loosely coupled and easily replaceable or extendable.
*   **Agentic Design:** Will utilize distinct agentic modes (e.g., Coder, Architect, Orchestrator) for handling different types of tasks, similar to the concept requested. Each mode will have specific capabilities and potentially restricted access (e.g., file permissions).
*   **Tool Integration:** Tools will be a primary mechanism for interaction with the environment (filesystem, commands, APIs). Support for both standard Python functions registered as tools and MCP-based tools is required.
*   **Workflow Engine:** PocketFlow will manage the execution flow, potentially allowing complex sequences of operations involving multiple modes and tools. Workflows themselves should be definable and potentially embeddable.

## Key Technical Decisions (Initial)

*   **Language:** Python (version TBD, assume latest stable initially).
*   **Framework:** PocketFlow.
*   **Extendability:** Prioritized through clear interfaces for adding modes, tools, and workflows.
*   **Embeddability:** Core logic should be designed such that it can be invoked or integrated into other Python applications.

## Future Considerations

*   State management approach within PocketFlow.
*   Specific design for mode interaction and delegation.
*   API design if exposing functionality externally.
*   Potential integration points (e.g., IDE plugins).