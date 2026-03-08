# Contract: Tool Approval Interactions

## Purpose

Define the shared interaction contract for tool approval prompts that support one-time, session-scoped, and persistent approval choices for a specific tool.

## Request Contract

When a tool requires explicit approval, the runtime must issue an interaction request with these properties:

```yaml
kind: buttons
prompt: "Allow tool '<tool_name>' ... ?"
options:
  - id: once
    label: Approve Once
    value: once
  - id: session
    label: Approve for Session
    value: session
  - id: always
    label: Always Approve
    value: always
  - id: deny
    label: Deny
    value: deny
default: deny
```

## Response Contract

The resolved interaction must preserve the selected scope value and be interpretable by both CLI and Textual UI. The confirmation tool result should normalize to this shape:

```yaml
success: true
approved: true | false
approval_scope: once | session | always | deny
response: <raw selected value>
interaction: <normalized interaction payload>
```

Normalization rules:

- `once` => `approved: true`, `approval_scope: once`
- `session` => `approved: true`, `approval_scope: session`
- `always` => `approved: true`, `approval_scope: always`
- `deny` => `approved: false`, `approval_scope: deny`

## Runtime Semantics

- The approval decision applies only to the specific requested tool.
- `once` authorizes the current tool call only and creates no persistent state.
- `session` updates only the active session’s confirmation overrides.
- `always` updates persistent confirmation policy independent of session history files.
- Deleting or clearing saved sessions must not remove `always` approvals.

## Rendering Semantics

- Basic CLI and one-shot mode must render the options through the shared interaction parser.
- Textual UI must present the same choices and return the same normalized values.
- Runtime event text may summarize that scoped approval input is required, but the event layer is not the source of truth for the contract.

## Failure Semantics

- Unrecognized interaction responses must fail closed.
- If interaction handling fails, the tool call must be treated as not approved.
- Missing or malformed scope values must not be coerced to `always`.