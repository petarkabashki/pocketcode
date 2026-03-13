# CLI And Textual UI

This document is the canonical reference for PocketCoder's command-line surface and Textual UI as implemented today.

It covers:

- startup and interface selection
- shared command parsing and runtime behavior
- request execution and live event streaming
- Textual UI layout, controls, persistence, and implementation boundaries

For load order and runtime precedence, see `architecture.md`. For Markdown asset file formats and validation behavior, see `markdown_assets.md`. For agent and skill semantics, see `agent_system.md` and `modes_and_skills.md`.

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
3. Run workspace-migration preflight and automatically rewrite unsupported workspace state into canonical forms when needed.
4. Resolve configuration from `./pocketcode.yml` in the workspace root.
5. Configure logging to `pocketcode.log` and optionally stderr/stdout.
6. Construct `PocketCodeEngine(config=config, workspace_root=os.getcwd())`.
7. Apply startup overrides such as flow, global LLM, and auto-confirm.
8. Choose one of the runtime interfaces: one-shot, basic interactive, or Textual.

## Startup Flags

Current supported startup flags are:

- `--flow <flow_name|auto>`: select the initial flow, or clear explicit selection with `auto`
- `--llm <profile_name>`: apply a global LLM override before the first request
- `--prompt "..."`: run one request non-interactively and exit
- `--auto-confirm-tools`: force tool execution approval regardless of runtime defaults
- `--migrate-workspace`: rewrite unsupported workspace state to canonical forms and exit

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
- `pocketcode/cli/textual_ui::run_textual_cli()` is the Textual entrypoint
- the app owns the screen state, input routing, a small set of runtime popups, and the live run monitor
- the Textual implementation now keeps two reducer-backed state slices: `TextualCliState` for layout, theme, active view, and engine snapshot, and `TextualRuntimeState` for run status, pending input prompts, console history, the main input placeholder, and the currently presented modal kind/title
- the runtime console state now stores both plain-text transcript lines and semantic output blocks so the interactive chat pane can render theme-aware Rich content without changing copy/export behavior
- runtime-derived console text, inspector summary text, modal labels, context/session summaries, prompt summaries, and run preview text are now computed through selector helpers in `pocketcode/cli/textual_ui/selectors.py` so the rendering mixin mostly binds derived values into widgets instead of formatting those runtime strings inline
- `TextualUIState` construction now lives in `pocketcode/cli/textual_ui/ui_state_mixin.py`, which assembles the view model from reducer state, selector outputs, and engine snapshots before the rendering mixin applies it to widgets
- cached widget updates, view switching, and `TextualUIState` application now live in `pocketcode/cli/textual_ui/widget_sync_mixin.py` so the rendering mixin focuses on runtime output flow and live event handling
- render commits now flow through a single helper in `pocketcode/cli/textual_ui/rendering_mixin.py`, which can optionally refresh input suggestions, hydrate reducer-backed engine snapshots, and then apply the rebuilt `TextualUIState`; that layer also supports batched commits plus engine-mutation transactions so multi-step updates can merge into one reducer-and-render pass
- slash-command execution and run-event consumption update runtime UI state before the renderer reapplies derived widget values
- Textual side effects are now funneled through dedicated helpers for command execution, request startup, pending-input resolution, and active-run draining so widget event handlers remain thin orchestration code
- modal and picker presentation is now centralized behind a modal coordinator helper so `push_screen`, callback wrapping, error handling, reducer-backed modal open/close dispatch, and post-close UI resync happen in one place instead of being duplicated across view mixins; modal dismissal now participates in the same batched render-commit path as follow-up result handlers
- slash commands still route through `handle_command()` so the command layer remains shared with the basic CLI
- the Textual shell is now runtime-focused: it no longer exposes workspace editing, cloning, deletion, or system-settings mutation flows

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
- shell-level commands still execute directly inside the shared dispatcher
- non-shell command dispatch now has an extension hook through engine-backed command providers
- provider-backed commands return structured command results, while the CLI layer remains responsible for printing user-facing output
- existing built-in command handlers are still intentionally thin wrappers over engine methods

The dispatcher returns `"__exit__"` only for `/exit` and `/quit`. All other commands communicate by printing to stdout.

## Command Layers

The implemented command architecture now distinguishes between a small shell command layer and provider-backed ACP-style commands.

Resolution order is:

1. shell/app commands implemented directly in `pocketcode/cli/command_handler.py`
2. active-agent exported provider commands exposed through the engine
3. root exported provider commands exposed through the engine
4. unknown command fallback

Current shell/app commands are intentionally narrow and include lifecycle, inspection, and interface controls such as:

- `/help`
- `/quit`
- `/exit`
- `/reload`
- `/debug`
- `/stop`
- `/cancel`

Provider-backed commands are intended for runtime behaviors that may eventually be supplied by the root command host, the active agent, or delegated subagents. The initial runtime hook is implemented, but no new provider-only slash command families are canonical yet.

The current root provider now exports these command groups:

- `/memory <show|trim [keep_last]|compact [keep_last]>`
- `/checkpoint <list|save <name>|show <name>|restore <name>>`

Only agent commands declared with visibility `exported` participate in slash-command discovery. Agent commands declared as `delegated` or `private` are available only through engine-level invocation paths used by parent agents or future ACP surfaces.

Even for slash-triggered commands, the runtime now builds an internal structured invocation envelope before control reaches active-agent command targets. The CLI still accepts plain slash syntax, but nested command delegation no longer depends only on raw strings once execution enters the engine/runtime layer.

The CLI currently remains text-first: provider-backed command output is still printed from the `output` field. Structured command `payload` and result `data` are now part of the internal runtime contract, but they are not yet surfaced as a first-class interactive CLI syntax. Workspace asset authoring and other mutable configuration editing are no longer part of the shared shell command surface; those flows are expected to move through ACP/provider commands or direct file edits.

## Universal Commands

The shared command layer exposes these primary command groups:

- `/help`
- `/list`
- `/set`
- `/flow`
- `/prompts`
- `/agent`
- `/stackvm`
- `/skill`
- `/context`
- `/confirm`
- `/session`
- `/reload`
- `/debug`
- `/stop`
- `/cancel`
- `/status`
- `/exit`
- `/quit`

Plural convenience commands map to `/list` scopes:

- `/flows`
- `/agents`
- `/skills`
- `/llms`
- `/tools`
- `/prompts`

`/agent` is now inspection-only from the CLI: `list`, `show`, and `switch` remain, while clone/edit/tool-policy mutation flows were removed. `/skill` is similarly inspection-only: `list` and `show` remain, while enable/disable mutation flows were removed.

### Aliases

Short aliases are normalized as follows:

- `/ls` -> `/list`
- `/ag` -> `/agent`
- `/ap` -> `/agent`
- `/lm` -> `/llm`
- `/lf` -> `/llm-flow`
- `/la` is removed; use `/llm-flow`
- `/lh` -> `/llm-handoff`
- `/st` -> `/status`
- `/c` -> `/cancel`
- `/r` -> `/reload`
- `/q` -> `/quit`

## Listing Commands

`/list` supports these scopes:

- `flows`
- `prompts`
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
- `skills`: prints skills grouped by top-level prefix and marks enabled entries
- `prompts`: lists registered prompt assets
- `llms`: lists available LLM profiles and marks the global override
- `tools`: resolves tool descriptions for the requested flow, or the current flow if none is supplied

`/tools` requires either an explicit flow name or an active flow selection.

## Selection And Override Commands

There is no longer a shared `/asset` shell command family. Workspace asset scaffolding, cloning, and editing must be done either through ACP/provider commands or by editing the files directly under the workspace resource roots documented in `configuration.md` and `markdown_assets.md`.

## StackVM Commands

Syntax:

```text
/stackvm list [flows|scripts]
/stackvm create flow <name> [--entry <word>] [--agent <agent_name>]
/stackvm create script <name> [--entry <word>]
/stackvm create agent <agent_name> <flow_name>
/stackvm inspect <flow|script|agent> <target> [--entry <word>]
/stackvm run <flow|script|agent> <target> [--input <text>] [--entry <word>] [--debug]
/stackvm debug <flow|script|agent> <target> [--input <text>] [--entry <word>]
/stackvm alter <flow|script|agent> <target> <source_file>
```

Behavior:

- `list` prints registered StackVM-backed flows plus standalone workspace scripts under `<primary_resource_root>/vm/`
- `create flow` writes a Markdown flow scaffold with `execution_mode: vm`, a default `vm_entry`, and an inline fenced `vm` block
- `create flow ... --agent <name>` also writes a workspace Markdown agent profile bound to that StackVM flow using the grouped `agent.<group>/...` convention
- `create script` writes a standalone `.vm` source file under `<primary_resource_root>/vm/`
- `create agent` writes a workspace Markdown agent profile that targets an existing StackVM flow using the grouped `agent.<group>/...` convention
- `inspect` compiles the target, prints token count, source contributors, validation warnings, and the expanded executable StackVM source
- `run` executes the requested target once through the normal agent runtime loop and prints the final output plus any recorded warning count
- `debug` is the same execution path as `run`, but also enables per-step VM tracing and prints the recorded stack snapshots after each literal push, quotation push, or word execution
- direct `run` and `debug` executions currently force `auto_confirm_tools=True` for that invocation so StackVM CLI runs do not block on tool confirmation prompts
- `alter flow` and `alter agent` delegate to the workspace Markdown asset updater
- `alter script` replaces a standalone `.vm` or `.md` script file from a local source file after compiling its VM body
- direct script execution defaults to the `main` entry word when `--entry` is not provided

Examples:

```text
/stackvm list
/stackvm create flow vm_triage --entry decide --agent reviewer.safe
/stackvm create script hello_world --entry main
/stackvm inspect flow resource_root.pocketcode.vm_triage
/stackvm debug script hello_world --input "ping"
/stackvm alter script hello_world ./drafts/hello_world.vm
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

`/llm-agent` has been removed. Use `/llm-flow`.

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
/agent help
```

Behavior:

- `/agent list` excludes synthesised defaults
- `/agent show` defaults to the active profile when no name is provided
- `/agent switch` activates an existing named profile
- CLI-level agent mutation commands were removed
- agent changes now go through ACP/provider commands or direct file edits

## Mode Commands

## Skill Commands

Current subcommands are:

```text
/skill list
/skill show <skill_name>
/skill help
```

Behavior:

- `/skill list` groups skills by top-level prefix derived from `-` or `.` separators
- `/skill show` prints tool refs, provided tools, extra prompts, references, scripts, assets, and source path
- CLI-level skill mutation commands were removed

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
/session show <session_id>
/session list
/session new [title...]
/session resume <session_id>
/session delete <session_id> --yes
/session clear-all --yes
/session clear-breakpoints <session_id> --yes
/session help
```

Behavior:

- saved sessions are workspace-local and backed by JSON files under `<runtime.storage.session_state_dir>/sessions/` (default: `.pocketstate/sessions/`)
- `/session show` prints the requested saved session, or the active one when no id is supplied
- `/session show` includes the saved debugger breakpoint count and the persisted breakpoint labels for that session
- `/session list` prints saved sessions with id, title, last-updated timestamp, active marker, and persisted debugger breakpoint count
- `/session new` creates a fresh active session without deleting earlier history
- `/session resume` restores the saved agent, profile, enabled skills, global LLM override, and session-scoped confirmation overrides
- `/session delete` requires `--yes`, refuses to delete the active session, and removes only the targeted saved session
- `/session clear-all` requires `--yes`, preserves the active session, and reports how many prior saved sessions were removed
- `/session clear-breakpoints` requires `--yes` and removes only the persisted debugger breakpoints from the targeted saved session

## Runtime Control Commands

- `/reload` rebuilds discovered resource roots, namespace registries, agents, tools, skills, and LLM profile mappings
- `/debug <request text>` is available in interactive CLI surfaces with debugger support and runs one request under an interactive step debugger
- `/stop` and `/cancel` request cooperative cancellation on the active run if one exists
- `/status` prints runtime flow, selected flow, active agent, skills, LLM overrides, default LLM, confirmation state, last-run runtime event and step counts, and any last-run StackVM validation warning codes recorded in `last_run_summary.vm_validation_warnings`
- `/status` also shows the count of session-persisted debugger breakpoints that will be restored onto the next debug run
- `/status steps`, `/status --steps`, `/status timeline`, or `/status --timeline` also print the recorded last-run step trace without the nested per-step detail payloads
- `/status verbose` or `/status --verbose` prints the same step trace plus the full warning messages, exact StackVM warning spans, and the recorded per-step detail payloads

`/stop` and `/cancel` only work when the interface passes an active run handle to the command layer.

The interactive debugger currently supports:

- `next` / `step`: run until the next pause-worthy runtime step completes
- `next <count>` / `step <count>`: run until that many pause-worthy runtime steps have completed
- `continue`: resume without pausing again until the run completes or is cancelled
- `until node <node_id>`: continue until a matching runtime node completion is observed
- `until agent <agent_name>`: continue until a pause-worthy event for that active agent is observed
- `until tool <tool_name>`: continue until a pause-worthy event involving that tool is observed
- `until event <event_type>`: continue until a matching pause-worthy runtime event is observed
- `until handoff`, `until error`, `until answer`, `until ask`: shorthands for common event stops
- `until when <path> == <value>` or `until when <path> != <value>`: continue until a simple condition over the paused event or live snapshot matches
- `break <node|agent|tool|event|when> ...`: add a persistent breakpoint using the same predicate surface as `until`
- `breaks`: list saved breakpoints for the active debug session
- `clear <breakpoint_id>` or `clear all`: remove one or all saved breakpoints
- `status`: print the paused event plus a compact live runtime snapshot
- `steps`: print the currently recorded step timeline
- `quit`: cancel the run

The debugger currently pauses after completed or instantaneous runtime steps:

- `node_completed`
- `agent_turn_completed`
- `llm_call_completed`
- `tool_finished`
- `handoff`
- `handoff_return`
- `final_answer`
- `ask_user`
- `runtime_error`

Condition paths for `until when` resolve against:

- the paused event with the explicit prefix `event.`
- the live snapshot with the explicit prefix `snapshot.`
- unprefixed paths first against the event, then against the snapshot

Examples:

- `until node review_route`
- `next 5`
- `until tool core.write_file`
- `until handoff`
- `until when pending_tool.name == "core.write_file"`
- `until when event.node_id == "review_route"`
- `until when snapshot.active_agent == "review.safe"`
- `break node review_route`
- `break when pending_tool.name == "core.write_file"`
- `breaks`
- `clear 2`

## Request Execution And Live Events

One-shot mode, the basic CLI, and the Textual UI all use the same request runner in `pocketcode/main.py` plus `engine.start_request(...)`.

Execution model:

1. Call `engine.start_request(user_input=..., cli_context=..., bridge_user_input=...)`.
2. Poll the `RunHandle` until `is_done`.
3. Drain runtime events continuously.
4. Print formatted runtime lifecycle lines using `pocketcode/cli/runtime_events.py`.
5. When bridging is enabled, resolve `interaction_requested` and `user_input_requested` events from console input.
6. Wait for final output and print the final assistant response.

Each run now also builds a canonical observability summary in `last_run_summary`:

- `runtime_event_count`: total runtime events seen by the request-level observer
- `step_count`: number of structured runtime steps recorded for the run
- `steps`: ordered step timeline entries with `index`, `kind`, `status`, `duration_ms`, `summary`, and compact `details`

The step observer currently records first-class steps for:

- agent turns
- LLM calls
- tool calls
- handoffs
- handoff returns
- runtime errors

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

When an event is associated with a structured runtime step, the formatted line is prefixed with `Step N:`. This gives both the basic CLI and one-shot mode a stable step-by-step execution view without switching into a separate debug command.

This event stream is shared with the Textual UI so both interfaces present the same lifecycle vocabulary and the same step numbering.

## Interactive Debugger

The basic interactive CLI and the Textual UI both expose `/debug <request text>` through the shared command layer.

Execution model:

1. Call `engine.start_request(..., debug=True)` so the request's `RunHandle` starts in step-debug mode.
2. Drain runtime events normally.
3. When the `RunHandle` reaches a pause-worthy runtime step, it blocks the worker thread after queueing that event.
4. The active interface renders the paused event plus a compact live snapshot from the engine's shared store.
5. The user issues debugger commands such as `next`, `continue`, `status`, `steps`, or `quit`.
6. Persistent breakpoints, when configured, can interrupt ordinary `continue` execution and are reported back on the paused event as the matched breakpoint id and label.

VM-backed runs emit the same structured runtime-step event stream used by the rest of the engine. The interactive debugger pauses on those runtime-step boundaries and shows the current active agent plus the latest runtime snapshot from shared store state.

Textual-specific behavior:

- `/debug <request text>` starts the run under the same `RunHandle` debugger used by the basic CLI
- when execution pauses, the app automatically switches to the `Run` view
- the run inspector now shows a dedicated `Debugger` block with pause status, active agent, active node, stop condition, breakpoint count, and live runtime counters
- the inspector summary also shows the count of session-persisted debugger breakpoints even when no debug run is currently attached
- the `Run` view also exposes direct debugger controls for `Next`, `Continue`, `Add Break`, `Clear Breaks`, `Status`, `Breaks`, and `Quit`
- `Add Break` opens a Textual picker and prompt flow so node, agent, tool, event, shorthand, and conditional breakpoints can be added without typing the raw `break ...` command
- each saved breakpoint is also rendered as its own selectable block in the `Run` inspector
- selecting a breakpoint block lets `Clear Selected` remove that specific breakpoint directly from the UI
- breakpoints added or cleared in Textual are now stored on the active saved session and are restored automatically on later `/debug` runs after session resume or app restart
- while paused, the main input accepts the same debugger commands as the basic CLI: `next`, `continue`, `until ...`, `break ...`, `breaks`, `clear ...`, `status`, `steps`, and `quit`
- Textual key bindings for debugger control are `F7` (`next`), `F8` (`continue`), `F9` (`add breakpoint`), `Ctrl+G` (`status`), `Ctrl+B` (`breaks`), `Ctrl+K` (`clear selected breakpoint`), and `Ctrl+Shift+B` (`clear all breakpoints`)

One-shot mode still exposes the same runtime step timeline and live event stream, but it does not provide an interactive pause/continue debugger surface.

## Textual UI Architecture

The Textual UI lives under `pocketcode/cli/textual_ui/`.

The main app class is `PocketCodeTextualApp(App[None])`.

Current module layout:

- `pocketcode/cli/textual_ui/app.py`: final `PocketCodeTextualApp` composition and `run_textual_cli()`
- `pocketcode/cli/textual_ui/base.py`: app shell, bindings, CSS, and layout composition
- `pocketcode/cli/textual_ui/debugger_mixin.py`: Textual debugger queueing, pause sync, and paused-command handling
- `pocketcode/cli/textual_ui/ui_state_mixin.py`: `TextualUIState` assembly from reducer state, selector outputs, and engine snapshots
- `pocketcode/cli/textual_ui/widget_sync_mixin.py`: cached widget updates, view switching, and `TextualUIState` application
- `pocketcode/cli/textual_ui/rendering_mixin.py`: runtime output flow and run-event updates
- `pocketcode/cli/textual_ui/selection_mixin.py`: runtime view selection flow
- `pocketcode/cli/textual_ui/interaction_mixin.py`: input handling, UI event handlers, and user actions
- `pocketcode/cli/textual_ui/picker_screens.py` and `pocketcode/cli/textual_ui/interaction_screens.py`: modal screen classes used for runtime popups
- `pocketcode/cli/textual_ui/shared.py`: constants, helper functions, and immutable UI state dataclasses

Core state owned by the app includes:

- the engine and shared CLI context
- the current view (`chat` or `run`)
- right-panel visibility
- theme name and workspace view
- active run handle
- pending interaction request
- live run status and recent run events
- live debugger state for the active paused debug run, derived from the current `RunHandle`
- debugger control-row visibility and enabled state in the `Run` view
- last-run structured step trace rendered from `last_run_summary.steps`

### UI Pipeline

The current Textual UI pipeline is intentionally layered:

1. reducer-backed state in `store.py` owns structural UI state and transient runtime state, and now includes pure helpers for reducing ordered action batches instead of only one action at a time
2. selector helpers in `selectors.py` derive runtime-facing text blocks and summaries from that state
3. `ui_state_mixin.py` assembles `TextualUIState` from reducer state, selector output, and engine-backed choices
4. `widget_sync_mixin.py` applies `TextualUIState` to Textual widgets using cached updates to avoid redundant work
5. `rendering_mixin.py` handles runtime output flow, live event consumption, and the centralized render-commit helper that can refresh suggestions, hydrate engine snapshots, and re-render in one step or batch related updates into a single render pass
6. effect mixins and the modal coordinator present runtime popups or mutate run state, then trigger the render-commit path as needed
- rendered output buffer and trimmed line count
- suggestion list for input completion
- cached UI state snapshots to avoid unnecessary redraws

### Layout

The app renders:

- a top bar with agent and LLM summary
- a main column with a view title, a content switcher, and the main input
- a right details panel
- a footer with key bindings

The content switcher exposes two views:

- `chat`: read-only output console
- `run`: a structured preview of the last run summary and current live-run state

The right details panel shows:

- a runtime summary card
- current session context
- session history
- prompt sources

The details panel is read-only. Runtime editing, cloning, profile mutation, and settings mutation are no longer part of the Textual shell.

### Themes And Workspace Views

Built-in themes are:

- `ocean`
- `forest`
- `ember`

Each built-in theme resolves through a token palette that currently defines application background, primary and muted text, layered surfaces, border, accent, info, success, warning, error, and input-focus colors. The Textual screen CSS and the semantic output renderer both consume the same palette selection.

Built-in workspace views are:

- `balanced`
- `chat_focus`
- `minimal`
- `review`

Textual startup always opens on the `chat` view. The saved workspace view still restores its layout traits, such as right-inspector visibility, and selecting a workspace view inside the UI switches to that preset's paired content view.

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

Assistant and user messages render as bordered panels under the active theme. Assistant responses that contain fenced code blocks are decomposed into prose panels plus syntax-highlighted code panels. Fenced `diff` blocks render through a dedicated diff view with line-level add/remove styling. Tool calls and tool results render as dedicated panels, while runtime, info, warning, and error entries render as themed inline log records. Tool-policy confirmation requests now render as dedicated collapsible panels that show the human question in the collapsed state and reveal `Args:` details only when expanded. LLM requests and LLM responses also render as dedicated one-line collapsible panels that expand to the full prompt or response body. The plain-text transcript is still preserved in runtime state for clipboard copy and other text-only flows.

The `run` view now uses the same Rich-capable rendering path as the main chat console. Instead of a plain text dump, the run preview presents semantic overview and summary blocks, including YAML-formatted run metadata, the recorded runtime event count, the structured step count, a dedicated step-timeline block rendered from `last_run_summary.steps`, StackVM authoring warnings from `last_run_summary.vm_validation_warnings` when present, and recent live events.

The right-side inspector summary also surfaces the last run's runtime event count, runtime step count, and any StackVM authoring warning codes when the active run summary recorded `vm_validation_warnings`.

The right-side details panel now follows the same pattern for its runtime summary, session context, session history, and prompt-source panes. Those sections render semantic Rich blocks and are read-only.

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
- `F2`: open the previous-entry picker for the main input box
- `F5`: open the global view selector for `chat` and `run`
- `Ctrl+P`: load the previous main-input entry
- `Ctrl+N`: move forward through recalled main-input entries
- `Ctrl+Up`: focus the previous visible Rich surface
- `Ctrl+Down`: focus the next visible Rich surface
- `Ctrl+Left`: select the previous compactable block in the focused Rich surface
- `Ctrl+Right`: select the next compactable block in the focused Rich surface
- `F10`: toggle the right details panel
- `Ctrl+E`: expand or restore the selected compacted block in the focused Rich surface
- `Ctrl+Shift+A`: copy full output buffer
- `Ctrl+Y`: copy the last assistant response
- `Ctrl+R`: reload runtime
- `Ctrl+L`: clear output
- `Ctrl+Q`: quit

### Textual-Only Slash Commands

These commands are available only from the Textual input box:

- `/copy`: copy the last assistant response to the clipboard
- `/copy-all`: copy the full visible console output to the clipboard
- `/view`: open the popup view selector
- `/view list|show|switch <chat|run>`: inspect or change the active Textual view

Outside the Textual interface, the shared command layer prints a message explaining that these commands are UI-only.

### Input Handling

The main input field handles three cases:

- when a runtime interaction is pending, input is treated as the reply to that interaction
- when the text starts with `/`, it is executed as a slash command
- otherwise it starts a normal engine request with `bridge_user_input=True`

The Textual shell keeps a persisted history of accepted main-input entries in `<runtime.storage.entry_history_dir>/textual_entry_history.json` by default. That history powers both the `F2` picker and the `Ctrl+P`/`Ctrl+N` recall path.

`runtime.textual.control_presentation` controls whether these higher-friction Textual controls render `inline` or as `modal` popups. In `modal` mode, pending `interaction_requested` and `user_input_requested` events open popup input screens and the debugger breakpoint-add flow uses popup pickers. In `inline` mode, pending runtime prompts render as on-screen controls above the chat log and run log, then collapse into a submitted summary after the input is accepted; single-choice prompts use the same list-style option surface as checklist prompts instead of a dropdown; debugger breakpoint controls also stay on-screen in the Run view.

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

### Popup Surfaces

The Textual UI still uses modal screens, but only for runtime-focused tasks.

Current capabilities implemented across `pocketcode/cli/textual_ui/` include:

- selecting the active Textual view
- recalling previous main-input entries from a picker or keyboard history
- answering pending runtime prompts through inline chat/run controls, with popup fallbacks where the runtime still requests them
- debugger breakpoint and debugger-status helper popups

Workspace and configuration authoring are intentionally out of scope for the Textual shell. Those tasks now belong in direct file edits or future provider/admin command surfaces.

## Textual Persistence Model

The Textual UI persists only startup-oriented defaults plus accepted-input history. It no longer exposes UI flows for saving presets or writing agent/tool selections back into workspace config.

Persisted settings currently include:

- `theme_name`
- `workspace_view`
- `control_presentation`
- `default_skills`
- `selection_presets`
- `last_used.active_profile`
- `last_used.global_llm_profile`
- `last_used.session_confirmation_default`
- `last_used.auto_confirm_tools`

Important behavior:

- empty `last_used` sections are removed from config
- Textual entry history is stored separately from `pocketcode.yml`
- the current runtime shell reads these values but does not expose Textual editors for them

## System Settings

`PocketCodeEngine.get_system_settings()` exposes the settings used by the Textual shell on startup.

Current values returned are:

- `theme_name`
- `workspace_view`
- `default_agent`
- `default_llm_profile`
- `control_presentation`

`save_system_settings()` writes these values back into the runtime and LLM sections of `pocketcode.yml`, then reloads LLM runtime state.

On startup, `workspace_view` restores the saved layout preset but does not override the initial `chat` surface. Interactive workspace-view changes inside Textual still switch to the preset's paired view.

The current Textual shell no longer exposes an in-app system-settings editor. Settings remain file-backed and are read on startup.

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
- `pocketcode/cli/textual_ui/__init__.py`: Textual UI package export surface
- `pocketcode/cli/textual_ui/`: split Textual shell implementation, modal screens, pickers, editors, run monitor, and persistence actions
- `pocketcode/cli/completers.py`: small prompt-toolkit completer helpers that are currently not wired into the default startup path

## Current Non-Goals And Boundaries

The current CLI implementation does not provide:

- a prompt-toolkit REPL as the default basic shell
- a separate command protocol for Textual; it intentionally reuses the shared command handler
- persistent session context for `/context`; only Textual selection state and related runtime settings are persisted
- a startup flag for directly selecting an agent profile

When updating CLI behavior, keep this document in sync with `pocketcode/main.py` and the implementation modules under `pocketcode/cli/textual_ui/`.
