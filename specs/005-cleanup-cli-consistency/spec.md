# Feature Specification: CLI Consistency Cleanup

**Feature Branch**: `[005-cleanup-cli-consistency]`  
**Created**: 2026-03-07  
**Status**: Draft  
**Input**: User description: "Clean up CLI inconsistencies, stale compatibility artifacts, and obsolete command/help surfaces based on the prior CLI review findings."

## Clarifications

### Session 2026-03-07

- Q: How should deprecated aliases, flags, and compatibility paths be handled? → A: Remove deprecated aliases, flags, and compatibility paths entirely when they are not part of the preferred CLI model.
- Q: What terminology should be canonical in the public CLI? → A: Use agent as the primary public term, and remove workflow because it is no longer used.
- Q: How should interface-specific commands be handled? → A: Keep interface-specific commands, but mark them explicitly as interface-specific and exclude them from universal help and suggestions.
- Q: How should internal compatibility helpers tied to old CLI terminology and routing be handled? → A: Remove all internal compatibility helpers related to old CLI terminology and routing in the same feature.
- Q: How should help and command discovery be structured across interfaces? → A: Keep one universal help surface for shared commands, plus separate interface-specific help or discovery for interface-only commands.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reliable Command Surface (Priority: P1)

As a CLI user, I want every advertised command and alias to behave consistently across the available interfaces so that I can trust help text, completion, and runtime feedback.

**Why this priority**: The command surface is the primary user contract. If help text and suggestions advertise commands that fail or behave differently by interface, the CLI feels unreliable even when the underlying runtime works.

**Independent Test**: Can be fully tested by invoking every documented command and alias in the supported interfaces and verifying that each one either executes successfully or returns an explicit, accurate availability message.

**Acceptance Scenarios**:

1. **Given** a command is shown in help text or suggestions, **When** a user invokes it in a supported interface, **Then** the command completes with behavior that matches the documented description.
2. **Given** a command is limited to a specific interface, **When** a user invokes it elsewhere, **Then** the CLI reports that limitation explicitly instead of presenting it as a generic unknown command.
3. **Given** a command is specific to one interface, **When** a user views universal help or suggestions, **Then** that command is excluded from the universal command surface and only shown in interface-specific documentation or affordances.
4. **Given** a user needs to discover interface-only commands, **When** they are using that interface, **Then** the interface provides its own help or discovery path without polluting the universal help surface.

---

### User Story 2 - Clear Runtime Terminology (Priority: P2)

As a user switching between startup output, status output, and command help, I want the CLI to use one consistent set of public terms centered on agents so that I do not have to interpret old or unused naming models.

**Why this priority**: Terminology drift increases cognitive load and makes configuration and troubleshooting harder, especially where flow, agent, profile, and workflow language overlap.

**Independent Test**: Can be fully tested by reviewing startup text, status output, help output, and key command responses to confirm that the same runtime concepts use the same labels throughout.

**Acceptance Scenarios**:

1. **Given** the CLI presents startup or status information, **When** it names the active runtime selections, **Then** it uses the canonical public terms consistently with agent as the primary public term.
2. **Given** a user views agent, flow, tool, or mode details, **When** related entities are displayed, **Then** each label accurately describes the entity being shown.

---

### User Story 3 - Lower Maintenance Overhead (Priority: P3)

As a maintainer, I want obsolete compatibility artifacts and dead CLI helpers removed so that the command layer is easier to evolve without hidden drift.

**Why this priority**: Unused shims and stale compatibility paths make the CLI harder to reason about and increase the risk of future inconsistencies.

**Independent Test**: Can be fully tested by confirming that helpers, aliases, flags, and routing adapters tied only to removed terminology or deprecated command paths no longer exist, while explicitly retained command surfaces still work.

**Acceptance Scenarios**:

1. **Given** a CLI helper, alias, or compatibility branch exists, **When** the command layer is reviewed, **Then** any helper tied to old CLI terminology or routing is removed rather than retained as an adapter.
2. **Given** an obsolete artifact is no longer part of the supported CLI contract, **When** the cleanup is complete, **Then** it is removed from user-facing surfaces and does not leave stale documentation behind.

### Edge Cases

- A command may be valid only in one interface while still being discoverable globally.
- Legacy aliases or deprecated flags that are no longer part of the supported CLI model must either remain supported as first-class behavior or be removed entirely.
- Startup or status output may expose internal runtime fields that must no longer leak removed workflow terminology.
- Cleanup may remove user-facing references without removing internal compatibility support.
- Interface-specific commands must remain discoverable within their own interface without leaking into universal command help or shared suggestion lists.
- Removing old routing adapters may require updating tests and any remaining internal call sites in the same feature.
- Universal help and interface-local help must not contradict each other about command scope or availability.

## Requirements *(mandatory)*

### Functional Requirements

#### Retained vs Removed Command Inventory

The following reviewed command surfaces define the minimum retained-versus-removed scope for this feature.

**Retained universal commands and aliases**

- `/help`, `/list`, `/prompts`, `/modes`, `/mode`, `/skills`, `/skill`, `/agents`, `/agent`, `/llms`, `/llm`, `/llm-flow`, `/llm-agent`, `/llm-handoff`, `/tools`, `/reload`, `/stop`, `/cancel`, `/status`, `/context`, `/confirm`, `/exit`, `/quit`
- Universal aliases that remain supported: `/ls`, `/ag`, `/ap`, `/lm`, `/lf`, `/la`, `/lh`, `/st`, `/c`, `/r`, `/q`

**Retained interface-specific commands**

- Textual-only command surfaces: `/copy`, `/copy-all`

**Removed reviewed flags, terms, and compatibility surfaces**

- `--workflow`
- User-facing `workflow` terminology in startup output, status output, help text, and command responses
- Workflow-derived compatibility helpers and routing adapters that exist only to support old terminology or deprecated command paths
- Any alias, flag, or helper that routes only to removed workflow-era behavior rather than to the retained command inventory above

- **FR-001**: The system MUST define a canonical user-facing command surface for the CLI, including documented commands, aliases, and any interface-specific restrictions.
- **FR-002**: The system MUST ensure that every command presented in universal user-facing help or suggestions works in that interface-neutral command surface.
- **FR-003**: The system MUST align startup output, status output, help text, and command responses to one consistent set of public runtime terms centered on agent terminology.
- **FR-004**: The system MUST distinguish between internal compatibility behavior and the public CLI contract so that deprecated or compatibility-only paths are not presented as first-class user features unless intentionally supported.
- **FR-005**: The system MUST remove deprecated aliases, flags, and compatibility paths entirely when they are not part of the preferred supported CLI model.
- **FR-006**: The system MUST keep documentation consistent with the cleaned command surface and terminology.
- **FR-007**: The system MUST preserve supported command behavior that remains in scope for the preferred CLI model, and MUST not keep deprecated behavior solely for convenience once it has been reclassified as unsupported.
- **FR-008**: The system MUST provide automated verification for the cleaned CLI contract, including command availability and user-facing output expectations for the affected surfaces.
- **FR-009**: The system MUST remove user-facing workflow terminology and workflow-specific compatibility surfaces from the CLI where workflow is no longer part of the supported model.
- **FR-010**: The system MUST keep interface-specific commands only where they provide real value inside that interface, and MUST label them as interface-specific in the surfaces where they remain discoverable.
- **FR-011**: The system MUST exclude interface-specific commands from universal help text and shared completion or suggestion surfaces.
- **FR-012**: The system MUST remove internal compatibility helpers and routing adapters that exist only to support old CLI terminology or deprecated command paths.
- **FR-013**: The system MUST update remaining internal call sites and automated tests so that removed compatibility helpers do not leave orphaned references.
- **FR-014**: The system MUST maintain a single universal help and discovery surface for commands shared across interfaces.
- **FR-015**: The system MUST provide separate interface-specific help or discovery surfaces for retained interface-only commands.
- **FR-016**: The system MUST keep universal and interface-specific help surfaces consistent about command naming, scope, and availability.

### Key Entities *(include if feature involves data)*

- **CLI Command Surface**: The set of commands, aliases, availability rules, and help entries that users can discover and invoke.
- **Runtime Terminology Set**: The public labels used to describe selections and runtime state across startup, status, and command output, using agent as the primary public term.
- **Compatibility Artifact**: Any alias, helper, branch, or output path retained for migration or backward compatibility rather than as part of the preferred public contract.
- **Interface Context**: The execution environment in which a command is invoked, such as the basic interactive CLI, one-shot CLI usage, or the Textual UI.

## Assumptions

- The cleanup is scoped to the CLI user contract and adjacent documentation, not to redesigning the underlying runtime model.
- Existing supported behavior should be preserved only where it remains part of the preferred CLI model; deprecated behavior outside that model should be removed rather than hidden.
- Interface-specific commands are acceptable if they are clearly scoped, remain useful within that interface, and are not advertised as universally available.
- Workflow is not part of the supported public CLI model and should not remain visible in user-facing terminology.
- Internal compatibility layers for removed CLI terminology or routing are in scope for deletion in this feature.
- Users should not need to infer interface scope from error messages alone; discovery should be explicit in the relevant help surface.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of commands listed in the primary universal CLI help output are universally supported within that public command surface.
- **SC-002**: 100% of reviewed startup, status, and key command outputs use the selected canonical public terminology with agent as the primary user-facing term and no remaining workflow wording.
- **SC-003**: The affected CLI test suite includes explicit coverage for command availability and help/output behavior for all identified cleanup areas.
- **SC-004**: The number of user-visible stale or misleading CLI surfaces identified in the prior review is reduced to zero for the scoped cleanup items.
- **SC-005**: 100% of retained interface-specific commands are excluded from universal help and suggestion surfaces and remain documented or discoverable only in their relevant interface.
- **SC-006**: No internal helper or adapter remains solely to translate removed workflow-era or deprecated CLI routing concepts after the cleanup is complete.
- **SC-007**: Universal help and interface-specific help surfaces contain no contradictory command listings or scope labels for the cleaned command set.
