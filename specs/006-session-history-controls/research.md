# Research: Session History Controls

## Decision 1: Store saved sessions as workspace-local JSON files under `.pocketcode/state/sessions/`

- Decision: Persist each saved conversation session as its own JSON document under `.pocketcode/state/sessions/`, and derive the session list by scanning those files instead of maintaining a separate global session index.
- Rationale: The feature requires workspace-scoped history, but the existing workspace config file already stores durable runtime selections and persistent confirmation policy. Conversation transcripts can grow materially larger than config selections, so they should live outside `pocketcode.yml`. A per-session file model keeps CRUD simple, avoids index synchronization problems, and stays aligned with the constitution's preference for minimal orchestration.
- Alternatives considered:
  - Store saved sessions in `pocketcode.yml`. Rejected because transcript-like data does not belong in the canonical config file and would make writes larger and riskier.
  - Maintain an index file plus separate session payload files. Rejected for the initial feature because the expected session count is small enough that directory scanning is simpler and sufficient.
  - Store sessions directly under `.pocketcode/sessions/`. Rejected in favor of `.pocketcode/state/sessions/` so saved runtime state is clearly separated from auto-discovered workspace resources such as modes, skills, prompts, and tools.

## Decision 2: Keep `always` approvals in existing persistent tool confirmation config and map `session` approvals to session overrides

- Decision: Represent approval choices as `once`, `session`, `always`, and `deny/cancel` at interaction time, then translate them into the existing runtime layers: `once` allows only the current invocation, `session` writes to `session_tool_confirmation`, and `always` updates the persistent `runtime.tool_confirmation` configuration for the specific tool.
- Rationale: The runtime already has a mature confirmation precedence model with both persistent and session-scoped layers in `ToolRuntime._resolve_confirmation_policy()`. Reusing those layers avoids inventing a second approval store and directly satisfies the requirement that persistent approvals remain independent from session deletion.
- Alternatives considered:
  - Create a new approval-specific persistence file outside existing config. Rejected because it duplicates behavior already modeled by `runtime.tool_confirmation`.
  - Treat `always` as a special session type. Rejected because it would violate the feature requirement that session history cleanup must not affect persistent approvals.
  - Replace policy resolution with a brand-new approval subsystem. Rejected because the existing precedence stack already covers the needed separation.

## Decision 3: Capture and restore saved sessions at the shared engine request boundary, not from Textual-only output buffers

- Decision: Integrate saved-session state through `PocketCodeEngine.start_request()`, `_build_shared_store()`, and request completion paths so that user prompts, assistant outputs, active agent/mode/skills, and session-scoped confirmation overrides are captured consistently across one-shot CLI, basic CLI, and Textual UI.
- Rationale: The current Textual UI maintains an output buffer, but the feature must work in all interfaces. The engine already owns the shared store and RunHandle lifecycle, so it is the correct place to attach current session identity, transcript updates, and resume behavior.
- Alternatives considered:
  - Persist the Textual output buffer only. Rejected because it would fail basic CLI and one-shot mode.
  - Capture history from runtime event strings only. Rejected because event text is not the canonical user/assistant conversation payload and can omit important final output context.
  - Persist sessions only when the UI exits. Rejected because the user needs to switch or resume sessions during runtime.

## Decision 4: Reuse the existing interaction system and extend confirmation prompts to explicit multi-option button choices

- Decision: Keep tool approval prompts in the existing shared interaction model (`buttons` interactions) and return explicit approval-scope values rather than a boolean-only yes/no result.
- Rationale: The CLI and Textual UI already share `InteractionRequest` parsing and `buttons` handling. Extending the existing confirmation payload is the smallest change that supports one-time, session, and always choices across both interfaces.
- Alternatives considered:
  - Introduce a new interaction kind just for approval scope. Rejected because the existing button interaction already fits the need.
  - Use free-form text input for scope selection. Rejected because it is less discoverable and less reliable than structured options.
  - Add approval scope only in Textual UI and keep basic CLI yes/no. Rejected because the feature is part of the shared runtime contract.

## Decision 5: Expose session management through a shared `/session` command family and mirror it in Textual UI

- Decision: Define a shared `/session` command surface for `show`, `list`, `new`, `resume`, `delete`, and `clear-all`, and have Textual UI call the same engine methods via picker/dialog affordances.
- Rationale: Session control is a core runtime behavior, not a Textual-only convenience. The repository already centers shared behavior in `command_handler.py`, so the CLI contract should exist there first while Textual builds on top of it.
- Alternatives considered:
  - Make session history Textual-only. Rejected because the feature spec is not interface-limited.
  - Add session management only through startup flags. Rejected because users need to switch and clean up sessions during interactive use.
  - Fold session management into `/status` or `/context`. Rejected because session history is its own user-facing capability with destructive actions and should be explicit.

## Decision 6: Autogenerate titles from conversation content with a timestamp fallback

- Decision: Generate each session title automatically from the first user request excerpt, with a timestamp-based fallback when no meaningful first prompt is available.
- Rationale: The spec requires autogenerated titles and a readable session list. A first-prompt excerpt gives users a recognizable label without introducing manual naming UI, while a timestamp fallback preserves deterministic creation behavior for empty or nonstandard openings.
- Alternatives considered:
  - Use only opaque IDs as titles. Rejected because it would make the session list much less usable.
  - Force the user to name every session. Rejected by the clarified requirement that titles are autogenerated.
  - Use only timestamps as titles. Rejected because timestamps alone are less helpful than prompt-derived labels when choosing among many saved sessions.