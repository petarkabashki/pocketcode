# CLI And Textual UI

This document is the canonical reference for PocketCoder's command-line surface and Textual UI as implemented today.

It covers:

- startup and interface selection
- shared command parsing and runtime behavior
- request execution and live event streaming
- Textual UI layout, controls, persistence, and implementation boundaries

For load order and runtime precedence, see `architecture.md`. For Markdown asset file formats and validation behavior, see `markdown_assets.md`. For agent, mode, and skill semantics, see `agent_system.md` and `modes_and_skills.md`.

## Scope

PocketCoder currently exposes three user-facing CLI modes from the same entrypoint in `pocketcode/main.py`:

- one-shot mode for `--prompt` or piped stdin
- a basic interactive REPL for terminals where Textual is unavailable or when the Textual UI fails to start
- the full Textual UI for interactive terminal sessions with `textual` installed

All three surfaces share the same engine and the same slash-command dispatcher in `pocketcode/cli/command_handler.py`.

## Entrypoint

The installed CLI entrypoint calls `pocketcode.main.run()`.

Startup sequence:

1. Load environment variables with `python-dotenv`.
2. Parse CLI flags.
3. Resolve configuration from `./pocketcode.yml` in the workspace root.
4. Configure logging to `pocketcode.log` and optionally stderr/stdout.
5. Construct `PocketCodeEngine(config=config, workspace_root=os.getcwd())`.
6. Apply startup overrides such as flow, global LLM, and auto-confirm.
7. Choose one of the runtime interfaces: one-shot, basic interactive, or Textual.

The `--config` flag still exists for compatibility, but it is ignored. The runtime always resolves configuration from the workspace-local `pocketcode.yml`.

## Startup Flags

Current supported startup flags are:

- `--flow <flow_name|auto>`: select the initial flow, or clear explicit selection with `auto`
- `--llm <profile_name>`: apply a global LLM override before the first request
- `--prompt "..."`: run one request non-interactively and exit
- `--auto-confirm-tools`: force tool execution approval regardless of runtime defaults
- `--config <path>`: accepted but ignored; configuration still comes from `./pocketcode.yml`

There is no current startup `--agent` flag and no `--workflow` flag.

## Interface Selection

`pocketcode/main.py` chooses the interface using terminal capabilities and input state.

### One-Shot Mode

One-shot mode is used when either of these is true:

- `--prompt` is provided
- stdin is not a TTY and contains non-empty piped input

Behavior:

- the runtime sets `cli_context["interface"] = "one-shot"`
- slash commands are executed once and any returned text is printed
- non-command prompts are executed through `engine.start_request(..., bridge_user_input=False)`
- runtime lifecycle events are drained and printed while the request runs
- the process exits after the command or request completes

If stdin is non-interactive but empty, PocketCoder exits with an error and suggests either an interactive terminal or `--prompt`.

### Basic Interactive CLI

The fallback REPL is used when:

- non-interactive stdout is detected before Textual startup, or
- the Textual import fails because the `textual` package is missing, or
- the Textual UI raises an exception during startup and the runtime falls back

Behavior:

- the runtime sets `cli_context["interface"] = "basic"`
- input is read with Python `input()` using the prompt `(<flow>) > `
- slash commands execute immediately through the shared command handler
- normal requests run through the same live event drain loop used by one-shot mode
- `Ctrl+C` during an active request requests cooperative cancellation, then waits for completion

The basic CLI does not currently use the helper completers defined in `pocketcode/cli/completers.py`.

### Textual UI

The full UI is used for interactive terminals when `textual` is importable.

Behavior:

- the runtime sets `cli_context["interface"] = "textual"`
- `pocketcode/cli/textual_app.py::run_textual_cli()` remains the stable entrypoint and forwards to the split Textual UI implementation under `pocketcode/cli/textual_ui/`
- the app owns the screen state, input routing, picker dialogs, editing dialogs, and live run monitor
- the Textual implementation now keeps two reducer-backed state slices: `TextualCliState` for layout, theme, active view, and engine snapshot, and `TextualRuntimeState` for run status, pending input prompts, console history, the main input placeholder, and the currently presented modal kind/title
- the runtime console state now stores both plain-text transcript lines and semantic output blocks so the interactive chat pane can render theme-aware Rich content without changing copy/export behavior
- runtime-derived console text, inspector summary text, modal labels, context/session summaries, prompt summaries, and run preview text are now computed through selector helpers in `pocketcode/cli/textual_ui/selectors.py` so the rendering mixin mostly binds derived values into widgets instead of formatting those runtime strings inline
- shared skill/tool picker grouping, nested tool tree construction, and selection-list option shaping now live in `pocketcode/cli/textual_ui/picker_model_mixin.py` so rendering, interaction, and asset-management flows reuse one picker-model layer
- `TextualUIState` construction now lives in `pocketcode/cli/textual_ui/ui_state_mixin.py`, which assembles the view model from reducer state, selector outputs, and picker-model helpers before the rendering mixin applies it to widgets
- cached widget updates, view switching, and `TextualUIState` application now live in `pocketcode/cli/textual_ui/widget_sync_mixin.py` so the rendering mixin focuses on runtime output flow and live event handling
- render commits now flow through a single helper in `pocketcode/cli/textual_ui/rendering_mixin.py`, which can optionally refresh input suggestions, hydrate reducer-backed engine snapshots, and then apply the rebuilt `TextualUIState`; that layer also supports batched commits plus engine-mutation transactions so multi-step updates can merge into one reducer-and-render pass
- slash-command execution and run-event consumption update runtime UI state before the renderer reapplies derived widget values
- Textual side effects are now funneled through dedicated helpers for command execution, request startup, pending-input resolution, and active-run draining so widget event handlers remain thin orchestration code
- picker-driven mutations such as profile, mode, and LLM selection, system-settings persistence, selection presets, clone/delete flows, and saved-session operations are also routed through dedicated selection-effect helpers instead of calling engine mutation APIs inline from UI handlers
- edit-screen flows now route workspace-agent saves, LLM-profile updates, mode updates, clone-before-edit flows, and tool-policy/tool-allowlist default persistence through dedicated config-effect helpers instead of mixing those engine writes into the YAML-editing UI code
- Textual edit and control-center flows now also support workspace markdown flow and tool assets through the shared engine asset API used by the basic CLI
- workspace markdown flow edits and clones proactively validate executable Mermaid and DOT graph definitions before runtime reload
- workspace markdown flow and tool edits and clones also resolve Markdown `include` and `import` directives before reload, so broken prompt-file references fail during authoring instead of during a later runtime load
- workspace markdown flow edits and clones now also validate that referenced tools, handoff targets, composite agents, and prompt-bundle entries resolve before reload
- workspace markdown agent edits and clones now apply the same pre-reload `include` and `import` validation path as workspace flow and tool assets
- workspace markdown agent edits and clones also validate that referenced flows, tools, and `prompt:` entries resolve in the live registries before reload
- modal and picker presentation is now centralized behind a modal coordinator helper so `push_screen`, callback wrapping, error handling, reducer-backed modal open/close dispatch, and post-close UI resync happen in one place instead of being duplicated across view mixins; modal dismissal now participates in the same batched render-commit path as follow-up result handlers
- slash commands still route through `handle_command()` so the command layer remains shared with the basic CLI
- skill toggles in the inspector persist against the active agent profile when one is selected; otherwise they persist as the global Textual last-used skill selection
- the inspector `Save` buttons write the current skill or tool selection into the active workspace agent profile file
- the edit picker can open workspace markdown flow and tool assets in the Textual editor, and the control center can clone or delete those same assets

## Shared CLI Context

All interfaces pass a mutable CLI context object into commands and requests.

Current structure:

```python
{
	"files": set(),
	"folders": set(),
	"urls": set(),
	"snippets": {},
	"interface": "one-shot" | "basic" | "textual" | None,
}
```

This context is session-local. It is not persisted by the CLI itself.

## Command Architecture

All slash commands are parsed and dispatched by `pocketcode/cli/command_handler.py`.

Design properties:

- commands are shell-split with `shlex.split()`
- aliases are normalized before dispatch
- Textual-only commands are rejected outside the Textual interface
- most commands mutate engine state directly and print user-facing status lines
- command handlers are intentionally thin wrappers over engine methods

The dispatcher returns `"__exit__"` only for `/exit` and `/quit`. All other commands communicate by printing to stdout.

## Universal Commands

The shared command layer exposes these primary command groups:

- `/help`
- `/list`
- `/set`
- `/flow`
- `/prompts`
- `/agent`
- `/asset`
- `/mode`
- `/skill`
- `/context`
- `/confirm`
- `/session`
- `/reload`
- `/stop`
- `/cancel`
- `/status`
- `/exit`
- `/quit`

Plural convenience commands map to `/list` scopes:

- `/flows`
- `/agents`
- `/modes`
- `/skills`
- `/llms`
- `/tools`
- `/prompts`

### Aliases

Short aliases are normalized as follows:

- `/ls` -> `/list`
- `/ag` -> `/agent`
- `/ap` -> `/agent`
- `/lm` -> `/llm`
- `/lf` -> `/llm-flow`
- `/la` -> `/llm-agent`, then normalized to `/llm-flow`
- `/lh` -> `/llm-handoff`
- `/st` -> `/status`
- `/c` -> `/cancel`
- `/r` -> `/reload`
- `/q` -> `/quit`

## Listing Commands

`/list` supports these scopes:

- `flows`
- `prompts`
- `modes`
- `skills`
- `agents`
- `llms`
- `tools`

Examples:

```text
/list flows
/list agents
/list tools core.react
```

Behavior by scope:

- `flows`: lists registered flow names and marks the active flow
- `agents`: lists named agent profiles excluding synthesised defaults and marks the active profile
- `modes`: lists known modes and marks the active mode
- `skills`: prints skills grouped by top-level prefix and marks enabled entries
- `prompts`: lists registered prompt assets
- `llms`: lists available LLM profiles and marks the global override
- `tools`: resolves tool descriptions for the requested flow, or the current flow if none is supplied

`/tools` requires either an explicit flow name or an active flow selection.

## Selection And Override Commands

## Asset Scaffolding

Syntax:

```text
/asset list <agent|flow|tool>
/asset show <agent|flow|tool> <name>
/asset clone <agent|flow|tool> <source_name> <new_name>
/asset edit <agent|flow|tool> <name> <markdown_file>
/asset delete <agent|flow|tool> <name> --yes
/asset create <agent|flow|tool> <name>
```

Behavior:

- `list` shows workspace-backed Markdown assets currently loaded for that kind
- `show` prints the resolved source path and current Markdown source for a workspace-backed asset
- `clone` copies a workspace-backed Markdown asset to a new name
- `edit` replaces a workspace-backed Markdown asset from an external Markdown file
- `delete` removes a workspace-backed Markdown asset after explicit `--yes` confirmation
- scaffolds workspace Markdown assets in the primary resource root, typically `.pocketcode/`
- `agent` creates a Markdown agent profile under `agents/`
- `flow` creates a Markdown flow scaffold under `flows/` with a minimal executable Mermaid graph and `nodes:` mapping
- `tool` creates both a Markdown tool definition and a sibling Python handler module under `tools/`
- cloning a tool also copies a sibling relative Python handler module when the Markdown `handler:` points at a local file
- editing validates that front matter `name:` still matches the target asset name before saving
- editing and cloning tool assets also validate that the `handler:` reference resolves before reload
- deleting a tool removes the Markdown definition but currently leaves any sibling handler module in place
- successful creation triggers an engine reload so the new asset is immediately visible to runtime discovery
- names are restricted to letters, numbers, dot, underscore, and hyphen to keep file paths and registry names stable
- the exact Markdown file formats for these assets are documented in `markdown_assets.md`

Examples:

```text
/asset list flow
/asset show tool workspace_echo
/asset clone tool workspace_echo workspace_echo_copy
/asset edit flow triage ./drafts/triage.md
/asset delete tool workspace_echo_copy --yes
/asset create agent reviewer.safe
/asset create flow triage
/asset create tool workspace_echo
```

### Flow Selection

Syntax:

```text
/flow <flow_name|auto> [--agent <agent_name>]
```

Behavior:

- selecting a concrete flow sets the active executable flow
- selecting `auto` clears explicit flow selection and returns to runtime default or handoff behavior
- `--agent`, `--profile`, and `--agent-profile` are treated as synonyms in this command path
- when an agent profile is supplied, the handler switches the flow first and then activates the named profile

### Global LLM Override

Syntax:

```text
/llm <profile_name|none>
```

Accepted reset tokens are `none`, `reset`, and `auto`.

### Flow-Specific LLM Override

Syntax:

```text
/llm-flow <flow_name> <profile_name|none>
```

`/llm-agent` is a compatibility alias for the same command path.

### Handoff-Specific LLM Override

Syntax:

```text
/llm-handoff <source_agent> <target_agent> <profile_name|none>
```

This writes a per-handoff override through `engine.set_handoff_llm_override()`.

### `/set` Compatibility Wrapper

`/set` forwards to the concrete commands above.

Supported targets:

- `flow`
- `llm`
- `llm-flow`
- `llm-handoff`

## Agent Commands

Current subcommands are:

```text
/agent list
/agent show [agent_name]
/agent switch <agent_name>
/agent clone <source> <new_name>
/agent edit llm <agent> <profile|inherit>
/agent edit prompts <agent> <paths...>
/agent edit prompts <agent> clear
/agent tools <agent> all
/agent tools <agent> none
/agent tools <agent> set <tools...>
/agent policy default <agent> <allow|confirm|deny|reset>
/agent policy tool <agent> <tool> <allow|confirm|deny|reset>
/agent help
```

Behavior:

- `/agent list` excludes synthesised defaults
- `/agent show` defaults to the active profile when no name is provided
- `/agent switch` activates an existing named profile
- `/agent clone` creates a workspace-backed copy, which is the prerequisite for editing plugin or synthesised profiles
- `/agent edit llm` updates only the profile-level LLM override
- `/agent edit prompts` replaces the full extra prompt path list
- `/agent tools` replaces the tool allowlist
- `/agent policy` edits the default or per-tool confirmation policy

Editing constraints:

- only workspace-backed agent profiles are editable
- plugin-backed and synthesised profiles must be cloned first
- tool names are validated against the profile's underlying flow before being written

## Mode Commands

Current subcommands are:

```text
/mode list
/mode show [mode_name]
/mode switch <mode_name>
/mode clear
/mode help
```

Behavior:

- modes are Markdown-authored runtime overlays
- activating a mode resolves an ephemeral profile layered over the active runtime state
- clearing a mode returns to the selected or default agent-profile path

`/mode show` prints the resolved mode fields including flow, agent, LLM, tools, prompts, confirmation settings, and source path.

## Skill Commands

Current subcommands are:

```text
/skill list
/skill show <skill_name>
/skill enable <skill_name>
/skill disable <skill_name>
/skill help
```

Behavior:

- `/skill list` groups skills by top-level prefix derived from `::`, `-`, or `.` separators
- enabling a skill appends it to the session skill set and refreshes runtime components
- disabling a skill removes it from the session skill set and refreshes runtime components
- `/skill show` prints tool refs, provided tools, extra prompts, references, scripts, assets, and source path

## Context Commands

Current subcommands are:

```text
/context show [files|folders|urls|snippets|all]
/context add file <path>
/context add folder <path>
/context add url <url>
/context add snippet <name> <content...>
/context remove file <path>
/context remove folder <path>
/context remove url <url>
/context remove snippet <name>
/context clear [files|folders|urls|snippets|all]
/context help
```

Behavior:

- paths and URLs are stored in the session-local CLI context object
- snippets are stored as name-to-content mappings
- `show` prints the current context without mutating it
- `clear` can target one category or all categories

## Confirmation Commands

Current subcommands are:

```text
/confirm show
/confirm clear
/confirm session <allow|confirm|deny|reset>
/confirm tool <tool_name> <allow|confirm|deny|reset>
/confirm agent <agent_name> <allow|confirm|deny|reset>
/confirm agent-tool <agent_name> <tool_name> <allow|confirm|deny|reset>
/confirm help
```

Behavior:

- these commands operate on session-level confirmation overrides
- they layer on top of persisted config and active profile policy
- `reset`, `none`, and `default` all normalize to clearing the override
- `/confirm clear` removes all session-level overrides
- interactive confirmation prompts can return `once`, `session`, `always`, or `deny`
- `once` applies only to the current tool invocation, `session` writes a session override, and `always` persists the tool policy into `pocketcode.yml`

## Session Commands

Current subcommands are:

```text
/session show
/session list
/session new [title...]
/session resume <session_id>
/session delete <session_id> --yes
/session clear-all --yes
/session help
```

Behavior:

- saved sessions are workspace-local and backed by JSON files under `.pocketcode/state/sessions/`
- `/session show` prints the active session id, title, and whether it was resumed from history
- `/session list` prints saved sessions with id, title, and last-updated timestamp, marking the active session
- `/session new` creates a fresh active session without deleting earlier history
- `/session resume` restores the saved agent, mode, enabled skills, global LLM override, and session-scoped confirmation overrides
- `/session delete` requires `--yes`, refuses to delete the active session, and removes only the targeted saved session
- `/session clear-all` requires `--yes`, preserves the active session, and reports how many prior saved sessions were removed

## Runtime Control Commands

- `/reload` rebuilds plugins, agents, tools, skills, and LLM profile mappings
- `/stop` and `/cancel` request cooperative cancellation on the active run if one exists
- `/status` prints runtime flow, selected flow, active agent, active mode, skills, LLM overrides, default LLM, and confirmation state

`/stop` and `/cancel` only work when the interface passes an active run handle to the command layer.

## Request Execution And Live Events

Both one-shot mode and the basic CLI use the same request runner in `pocketcode/main.py`.

Execution model:

1. Call `engine.start_request(user_input=..., cli_context=..., bridge_user_input=...)`.
2. Poll the `RunHandle` until `is_done`.
3. Drain runtime events continuously.
4. Print formatted runtime lifecycle lines using `pocketcode/cli/runtime_events.py`.
5. When bridging is enabled, resolve `interaction_requested` and `user_input_requested` events from console input.
6. Wait for final output and print the final assistant response.

The event formatter currently emits human-readable lines for:

- run start and completion
- agent turns
- LLM calls, usage, and estimated cost
- tool confirmation requests
- tool start, finish, timeout, and subprocess lifecycle
- handoffs and handoff returns
- session start, resume, save, delete, and clear events
- user-input and interaction prompts
- runtime errors and cancellation

This event stream is shared with the Textual UI so both interfaces present the same lifecycle vocabulary.

## Textual UI Architecture

The public Textual UI import surface remains `pocketcode/cli/textual_app.py`, but the implementation is now split across `pocketcode/cli/textual_ui/`.

The main app class is `PocketCodeTextualApp(App[None])`.

Current module layout:

- `pocketcode/cli/textual_app.py`: compatibility facade that re-exports the Textual UI surface
- `pocketcode/cli/textual_ui/app.py`: final `PocketCodeTextualApp` composition and `run_textual_cli()`
- `pocketcode/cli/textual_ui/base.py`: app shell, bindings, CSS, and layout composition
- `pocketcode/cli/textual_ui/picker_model_mixin.py`: shared skill/tool picker models and grouping helpers used across rendering and interaction flows
- `pocketcode/cli/textual_ui/ui_state_mixin.py`: `TextualUIState` assembly from reducer state, selector outputs, and picker models
- `pocketcode/cli/textual_ui/widget_sync_mixin.py`: cached widget updates, view switching, and `TextualUIState` application
- `pocketcode/cli/textual_ui/rendering_mixin.py`: runtime output flow and run-event updates
- `pocketcode/cli/textual_ui/selection_mixin.py`: profile, mode, LLM, confirmation, and system-settings selection flows
- `pocketcode/cli/textual_ui/control_center_mixin.py`: F6 control-center category and action routing
- `pocketcode/cli/textual_ui/config_editing_mixin.py`: agent, mode, LLM, and tool-policy editing helpers
- `pocketcode/cli/textual_ui/asset_management_mixin.py`: clone, delete, preset, skill, and tool-selection flows
- `pocketcode/cli/textual_ui/interaction_mixin.py`: input handling, UI event handlers, and user actions
- `pocketcode/cli/textual_ui/picker_screens.py` and `pocketcode/cli/textual_ui/editor_screens.py`: modal screen classes
- `pocketcode/cli/textual_ui/shared.py`: constants, helper functions, and immutable UI state dataclasses

Core state owned by the app includes:

- the engine and shared CLI context
- the current view (`chat`, `control`, or `run`)
- right-panel visibility
- theme name and workspace view
- active run handle
- pending interaction request
- live run status and recent run events

### UI Pipeline

The current Textual UI pipeline is intentionally layered:

1. reducer-backed state in `store.py` owns structural UI state and transient runtime state, and now includes pure helpers for reducing ordered action batches instead of only one action at a time
2. selector helpers in `selectors.py` derive runtime-facing text blocks and summaries from that state
3. picker-model helpers in `picker_model_mixin.py` derive grouped skill and tool selection models shared across multiple flows
4. `ui_state_mixin.py` assembles `TextualUIState` from reducer state, selector output, picker models, and engine-backed choices
5. `widget_sync_mixin.py` applies `TextualUIState` to Textual widgets using cached updates to avoid redundant work
6. `rendering_mixin.py` handles runtime output flow, live event consumption, and the centralized render-commit helper that can refresh suggestions, hydrate engine snapshots, and re-render in one step or batch related updates into a single render pass
7. engine-mutating UI flows now use a dedicated transaction helper that always hydrates engine-backed state at commit time, so handlers choose intent once instead of repeating `hydrate_engine=True` at every call site
8. effect mixins and the modal coordinator mutate engine state or present screens, then trigger the render-commit path as needed; modal result handlers now batch modal close plus any follow-up commits into a single render transaction
- rendered output buffer and trimmed line count
- suggestion list for input completion
- cached UI state snapshots to avoid unnecessary redraws

### Layout

The app renders:

- a top bar with agent and LLM summary
- a main column with a view title, a content switcher, and the main input
- a right inspector panel
- a footer with key bindings

The content switcher exposes three views:

- `chat`: read-only output console
- `control`: immediate runtime controls such as workspace view, theme, active profile, LLM, session confirm default, and auto-confirm switch
- `run`: a structured preview of the last run summary and current live-run state

The right inspector panel shows:

- a summary card
- current session context
- saved session history
- available agent profiles
- skills as an inline grouped selector
- allowed tools as an inline grouped and nested selector
- prompt sources

Inspector selector behavior:

- the `Skills` list applies a session-scoped skill selection immediately when toggled
- the `Allowed Tools` list applies a session-scoped tool selection immediately when toggled
- fresh sessions seed those session-scoped skill and tool selections from the active agent profile file
- the `Skills` header `Save` button writes the current selection into the active workspace agent's `skills` field
- the `Allowed Tools` header `Save` button writes the current effective tool scope into the active workspace agent's `tools` field
- tool groups and subgroups are derived from tool metadata, preferring the tool source path under `tools/`
- when every tool is selected, the effective tool scope is unrestricted for that profile

The F6 Control Center includes a `Sessions` category that can start a fresh session, resume saved history, delete a saved non-active session, or clear all previous sessions while keeping the active session.

### Themes And Workspace Views

Built-in themes are:

- `ocean`
- `forest`
- `ember`

Each built-in theme resolves through a token palette that currently defines application background, primary and muted text, layered surfaces, border, accent, info, success, warning, error, and input-focus colors. The Textual screen CSS and the semantic output renderer both consume the same palette selection.

Built-in workspace views are:

- `balanced`
- `chat_focus`
- `control_desk`
- `minimal`
- `review`

Workspace view changes both the default content view and whether the right inspector panel is visible.

The main chat console is rendered through a Rich-capable log surface rather than a plain text area. Current semantic output block kinds are:

- `assistant`
- `code`
- `user`
- `runtime`
- `info`
- `warning`
- `error`
- `tool_call`
- `tool_result`

Assistant and user messages render as bordered panels under the active theme. Assistant responses that contain fenced code blocks are decomposed into prose panels plus syntax-highlighted code panels. Fenced `diff` blocks render through a dedicated diff view with line-level add/remove styling. Tool calls and tool results render as dedicated panels, while runtime, info, warning, and error entries render as themed inline log records. The plain-text transcript is still preserved in runtime state for clipboard copy and other text-only flows.

The `run` view now uses the same Rich-capable rendering path as the main chat console. Instead of a plain text dump, the run preview presents semantic overview and summary blocks, including YAML-formatted run metadata and recent live events.

The right-side inspector panel now follows the same pattern for its summary, session context, saved sessions, and prompt-source panes. Those sections render semantic Rich blocks rather than plain text areas, while the profile list, skill selection list, and tool selection list remain interactive list widgets.

Long code, diff, YAML, text-preview, and tool-result panels are now compacted at render time. The underlying runtime state and plain-text transcript remain unchanged, but the visible Rich panels show only the leading portion of oversized content and annotate the panel with a truncation subtitle such as the number of displayed versus total lines.

Compacted Rich blocks can be toggled between compact and expanded rendering with `Ctrl+E`. The toggle now targets the selected compactable block inside the focused Rich surface instead of expanding an entire surface at once, so a single long run-summary block can be expanded without forcing the rest of the run preview or inspector pane open.

Focus can be moved across the currently visible Rich surfaces with `Ctrl+Up` and `Ctrl+Down`. Within the focused Rich surface, `Ctrl+Left` and `Ctrl+Right` move between compactable blocks. The selected compactable block is rendered with an accent border and a prefixed title before `Ctrl+E` expands or restores it.

The header now includes a live navigation strip that reports the current target panel, the selected compactable block position within that panel, and whether that block is in compact or expanded mode.

The header navigation strip now stays strictly keyboard-oriented: it reports the focused panel, current compactable block position, and compact-versus-expanded state without duplicating mouse-specific hints.

When a hovered compactable block exists, a separate hint strip now appears just above the footer with the mouse-specific click and wheel guidance. That keeps the header compact while still surfacing pointer behavior near the command/footer region.

That navigation strip now follows actual Textual focus changes on Rich surfaces, not only the custom panel-navigation shortcuts. If focus moves directly into or out of a Rich panel, the header updates to match the new target surface.

Mouse interaction now participates in the same selection model. Clicking inside a Rich surface focuses that surface and selects the compactable block whose rendered panel actually occupies the clicked line when that measurement is available, falling back to proportional selection only if the render span cache is unavailable. Wheel scrolling over a Rich surface updates the selected block from the rendered viewport center using the same span data.

When the pointer moves over a compactable block, that block now shows a lightweight hover affordance before selection: the title is prefixed and the panel border switches to the secondary highlight color, with an added subtitle hint that the block can be clicked to select.

Terminal font sizing remains outside PocketCoder's control. The terminal emulator owns font family and font size globally, so the Textual UI can theme color, emphasis, borders, padding, and layout, but it cannot apply true per-widget font sizes.

### Keyboard Shortcuts

Current bindings are:

- `Tab`: complete the current input from the suggestion list
- `F3`: open the edit asset picker
- `F4`: open the clone asset picker
- `F5`: open the global view selector for `chat`, `control`, and `run`
- `F6`: open the main asset/control picker
- `Ctrl+Up`: focus the previous visible Rich surface
- `Ctrl+Down`: focus the next visible Rich surface
- `Ctrl+Left`: select the previous compactable block in the focused Rich surface
- `Ctrl+Right`: select the next compactable block in the focused Rich surface
- `F10`: toggle the right inspector panel
- `Ctrl+E`: expand or restore the selected compacted block in the focused Rich surface
- `Ctrl+Shift+A`: copy full output buffer
- `Ctrl+Y`: copy the last assistant response
- `Ctrl+R`: reload runtime
- `Ctrl+L`: clear output
- `Ctrl+Q`: quit

There is no current `F2` binding.

### Textual-Only Slash Commands

These commands are available only from the Textual input box:

- `/copy`: copy the last assistant response to the clipboard
- `/copy-all`: copy the full visible console output to the clipboard
- `/view`: open the popup view selector
- `/view list|show|switch <chat|control|run>`: inspect or change the active Textual view

Outside the Textual interface, the shared command layer prints a message explaining that these commands are UI-only.

### Input Handling

The main input field handles three cases:

- when a runtime interaction is pending, input is treated as the reply to that interaction
- when the text starts with `/`, it is executed as a slash command
- otherwise it starts a normal engine request with `bridge_user_input=True`

Command execution in Textual is wrapped with `redirect_stdout()` so the shared command handler can continue to print plain text while the UI captures that output and appends it to the output panel.

### Run Event Drain

The Textual app installs a `0.1s` interval timer that drains events from the active `RunHandle`.

Event handling responsibilities:

- append formatted lifecycle lines to the output console
- update live run status such as `running`, `waiting_for_input`, `stopping`, `failed`, or `idle`
- swap the main input placeholder to show required prompt text
- record recent events for the Run view
- write the final assistant output on `run_completed`
- clear busy state and run handles on completion, failure, or cancellation

### Picker And Editor Surfaces

The Textual UI contains modal screens and picker flows for higher-level editing tasks.

Current capabilities implemented across `pocketcode/cli/textual_ui/` include:

- selecting the active agent profile
- selecting a mode
- selecting a global LLM override
- selecting a workspace view
- toggling skills, including grouped skill toggles
- editing allowed tools for a profile, including selectable groups and subgroups
- editing per-tool confirmation policy
- cloning the current agent, mode, or LLM profile
- deleting workspace-backed agent, mode, or LLM assets
- saving, loading, and deleting selection presets
- editing and saving system settings

These are UI conveniences over engine methods. The Textual app maintains a reducer-backed CLI state snapshot, hydrates it from engine/session state, and renders widgets from that snapshot via one-way data flow.

## Textual Persistence Model

The Textual UI persists defaults and reusable presets into `runtime.textual` in `pocketcode.yml`, but live inspector tool and skill selections are session-scoped and are stored in the active saved-session snapshot instead.

Persisted settings currently include:

- `theme_name`
- `workspace_view`
- `default_skills`
- `selection_presets`
- `last_used.active_profile`
- `last_used.active_mode`
- `last_used.global_llm_profile`
- `last_used.session_confirmation_default`
- `last_used.auto_confirm_tools`

Important behavior:

- empty `last_used` sections are removed from config
- preset snapshots are normalized before save and when loaded back
- session files hold live skill selections, tool selections, and session confirmation overrides for the active session
- registry-backed tool refs inside preset snapshots and saved session confirmation maps are persisted in canonical dotted form
- deleting a workspace asset also cleans invalid references from selection presets and last-used state

## System Settings

`PocketCodeEngine.get_system_settings()` exposes the settings used by the Textual shell on startup.

Current values returned are:

- `theme_name`
- `workspace_view`
- `default_agent`
- `default_llm_profile`

`save_system_settings()` writes these values back into the runtime and LLM sections of `pocketcode.yml`, then reloads LLM runtime state.

When the Textual system-settings editor opens, it normalizes legacy `plugin::resource` agent ids from config to the registry's canonical `plugin.resource` form so older saved defaults continue to load without crashing the agent select widget.

The same normalization also happens inside `PocketCodeEngine` when system settings are read, applied, and saved, so `runtime.default_agent` cannot drift back to an incompatible form after startup.

Other engine control surfaces that accept flow or agent ids also normalize typed references such as `flow:core.react` and `agent:core.react` before lookup, so CLI and TUI paths resolve through the same canonical registry form.

## Output Model

The basic CLI writes directly to stdout.

The Textual UI stores output lines in memory and renders them into the chat console. It trims retained history to a maximum of `400` lines and prepends a notice when older lines have been discarded.

The Textual app separately tracks:

- the full current output buffer after trimming
- the number of trimmed lines
- the last assistant response for clipboard copy

## Implementation Map

Primary implementation files:

- `pocketcode/main.py`: startup flags, interface selection, one-shot execution, basic CLI loop, live event draining
- `pocketcode/cli/command_handler.py`: shared slash-command parsing, aliases, and engine mutation commands
- `pocketcode/cli/runtime_events.py`: human-readable runtime event formatting
- `pocketcode/cli/user_interaction.py`: console formatting and parsing for structured interaction requests
- `pocketcode/cli/textual_app.py`: stable Textual UI import surface and compatibility facade
- `pocketcode/cli/textual_ui/`: split Textual shell implementation, modal screens, pickers, editors, run monitor, and persistence actions
- `pocketcode/cli/completers.py`: small prompt-toolkit completer helpers that are currently not wired into the default startup path

## Current Non-Goals And Boundaries

The current CLI implementation does not provide:

- a prompt-toolkit REPL as the default basic shell
- a separate command protocol for Textual; it intentionally reuses the shared command handler
- persistent session context for `/context`; only Textual selection state and related runtime settings are persisted
- a startup flag for directly selecting an agent profile

When updating CLI behavior, keep this document in sync with `pocketcode/main.py`, `pocketcode/cli/textual_app.py`, and the implementation modules under `pocketcode/cli/textual_ui/`.
