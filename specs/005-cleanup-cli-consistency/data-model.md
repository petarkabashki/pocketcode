# Data Model: CLI Consistency Cleanup

## Entity: Universal Command Surface

- Purpose: Represents the shared command contract exposed across supported CLI entry points.
- Fields:
  - command_name: canonical slash command string
  - aliases: zero or more supported shorthand forms that remain part of the public contract
  - help_entry: user-facing help text for the command
  - suggestion_visibility: whether the command appears in universal suggestion sources
  - supported_interfaces: set of interfaces where the command is valid
- Validation Rules:
  - Every command present in universal help must be valid in every interface claimed by the universal surface.
  - Deprecated commands removed from the preferred model cannot remain in this entity.
  - Command name and help text must use agent-centered public terminology.

## Entity: Interface-Specific Command Surface

- Purpose: Represents commands intentionally limited to a single interface, such as Textual-only actions.
- Fields:
  - command_name: command or affordance name
  - interface_name: owning interface, such as `textual`
  - discovery_surface: where users can discover the command inside that interface
  - fallback_behavior: message or behavior when invoked outside the owning interface, if applicable
- Validation Rules:
  - Interface-specific commands must not appear in universal help or shared suggestions.
  - Interface-specific discovery must identify the interface scope explicitly.
  - Discovery text must not contradict universal command help.

## Entity: Runtime Terminology Set

- Purpose: Defines the public labels used for runtime selections and status information.
- Fields:
  - primary_terms: approved labels, including `agent`, `agent profile`, and `mode`
  - removed_terms: disallowed labels, including `workflow`
  - output_surfaces: startup output, status output, command output, and docs/help surfaces using the terms
- Validation Rules:
  - Removed terms cannot appear in user-facing CLI output.
  - The same runtime concept must use the same public term across all output surfaces.

## Entity: Compatibility Artifact

- Purpose: Captures any alias, helper, or routing adapter inherited from earlier CLI behavior.
- Fields:
  - artifact_name: function, alias, flag, or branch identifier
  - artifact_kind: user-facing or internal
  - legacy_purpose: what historical behavior it supported
  - current_status: retained or removed
  - replacement_surface: current supported command or term, if one exists
- Validation Rules:
  - Artifacts tied only to removed terminology or deprecated routing must be removed.
  - Retained artifacts must correspond to explicitly supported behavior in the spec.

## Entity: CLI Help Surface

- Purpose: Represents a help or discovery output surface shown to users.
- Fields:
  - surface_name: universal help, textual help, startup hint, etc.
  - surface_scope: universal or interface-specific
  - listed_commands: commands discoverable from that surface
  - terminology_profile: public term set used in that surface
- Validation Rules:
  - Universal help surfaces list only universally supported commands.
  - Interface-specific help surfaces list only commands valid in that interface or explicitly scoped there.
  - No two help surfaces may describe the same command with contradictory scope or terminology.

## Relationships

- Universal Command Surface is exposed through one or more CLI Help Surfaces with `surface_scope = universal`.
- Interface-Specific Command Surface is exposed through one or more CLI Help Surfaces with `surface_scope = interface-specific`.
- Runtime Terminology Set constrains labels used by all CLI Help Surfaces and command/status outputs.
- Compatibility Artifacts are evaluated against both command surfaces and either removed or mapped to a supported replacement.