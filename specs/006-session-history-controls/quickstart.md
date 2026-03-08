# Quickstart: Session History Controls

## Goal

Validate scoped tool approvals and workspace-scoped saved session history across the shared CLI runtime and the Textual UI.

## Prerequisites

1. Activate the project environment.
2. Ensure you are on branch `006-session-history-controls`.

## Validation Steps

1. Run the targeted unit tests for the shared runtime and UI surfaces touched by this feature.

```bash
source .venv/bin/activate
pytest tests/unit/test_session_manager.py tests/unit/test_tool_runtime.py tests/unit/test_engine_runtime_events.py tests/unit/test_command_handler.py tests/unit/test_cli_user_interaction.py tests/unit/test_textual_app.py
```

2. Run the broader CLI/runtime unit suite to catch cross-surface regressions.

```bash
source .venv/bin/activate
pytest tests/unit -k "tool_runtime or engine_runtime_events or command_handler or cli_user_interaction or textual_app or session"
```

3. Smoke-test the shared session command surface in one-shot mode.

```bash
source .venv/bin/activate
python -m pocketcode.main --prompt "/session list"
python -m pocketcode.main --prompt "/session new"
python -m pocketcode.main --prompt "/session show"
```

Expected result:

- empty history shows a clear no-sessions state when appropriate
- creating a new session reports the created session and does not remove earlier sessions
- showing session state identifies the active workspace-scoped session

4. Smoke-test scoped approval behavior in an interactive CLI session by invoking a tool that requires confirmation and choosing each approval duration in turn.

```bash
source .venv/bin/activate
python -m pocketcode.main
```

Expected result:

- the approval prompt offers `once`, `session`, and `always` choices for the requested tool
- `once` re-prompts on the next call of the same tool
- `session` suppresses re-prompting only within the current session
- `always` suppresses re-prompting in later sessions for the same tool only

5. Verify saved-session lifecycle behavior in the same workspace.

```text
/session new
<send at least one user request>
/session new
/session list
/session resume <previous-session-id>
/session delete <non-active-session-id>
/session clear-all
```

Expected result:

- previous sessions remain available after starting a new session
- session list shows title and last updated timestamp for each saved session
- resuming a prior session restores its prior conversation context and session-scoped confirmation state
- deleting a non-active session removes only that session
- clear-all requires confirmation and removes only non-active saved sessions

6. Verify the same flows from the Textual UI.

```bash
source .venv/bin/activate
python -m pocketcode.main
```

Expected result:

- Textual UI exposes session history controls backed by the same engine methods as the CLI
- session history actions reflect immediately in the UI
- the active session cannot be deleted from the picker/dialog surface

## Completion Checklist

- Tool confirmation prompts expose scoped approval durations for a single tool.
- `once`, `session`, and `always` approvals follow the expected lifetime rules.
- Saved sessions remain workspace-local and listable with title plus timestamp.
- Resuming a session restores the intended session state.
- Delete and clear-all actions require explicit confirmation and never remove the active session.
- Persistent always approvals still work after session history cleanup.