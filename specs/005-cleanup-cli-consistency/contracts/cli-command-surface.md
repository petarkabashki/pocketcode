# Contract: CLI Command Surface

## Purpose

Define the user-visible contract for command routing and command discovery after the CLI consistency cleanup.

## Universal Command Surface

The universal command surface includes only commands that are supported across the shared public CLI contract.

### Contract Rules

1. Any command listed in the primary CLI help output must be valid in the universal command surface.
2. Any command listed in universal suggestions or completions must also belong to the universal command surface.
3. Universal command names, help text, and status wording must use agent-centered public terminology.
4. Removed deprecated aliases, removed flags, and removed workflow-era terminology must not remain in the universal command surface.

## Interface-Specific Command Surface

Commands that are retained for a specific interface may exist outside the universal command surface.

### Contract Rules

1. Interface-specific commands must be discoverable only through that interface’s help, hints, or direct affordances.
2. Interface-specific commands must not appear in the universal help output or shared suggestion list.
3. If invoked outside their owning interface through a direct path, they must respond with an explicit interface-scope message rather than a misleading generic response.

## Terminology Contract

### Allowed public terms

- `agent`
- `agent profile`
- `mode`
- `skill`
- `tool`

### Removed public terms

- `workflow`
- workflow-derived compatibility naming used only for historical routing or output

## Output Consistency Contract

The following surfaces must agree on naming and scope:

- startup output in the basic CLI
- `/help` output
- `/status` output
- command-specific help and response text
- Textual discovery/help surfaces for interface-only commands

No surface may advertise a command as universal if another surface treats it as interface-specific.

## Verification Expectations

Implementation is complete only when tests demonstrate all of the following:

1. Universal help contains only universal commands.
2. Interface-only commands are absent from universal help and shared suggestions.
3. User-facing workflow wording has been removed from the CLI contract.
4. Removed compatibility helpers and deprecated routing paths leave no orphaned references in tests or live CLI code.