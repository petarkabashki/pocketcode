# Pocketcode

Pocketcode is an extensible terminal AI coding assistant built around PocketFlow.

## What Changed

Pocketcode now uses a small plugin-first core:

- Plugins declare tools, prompts, and flows in `plugin.yaml`.
- Flows are the primary runtime unit and are implemented as PocketFlow `Flow` factories.
- Flow prompts live in external Markdown files with `{{ include:path.md }}` support.
- Flows support Python `pre`, `steps`, and `post` handlers alongside LLM and deterministic execution modes.
- Agents can override LLM selection, tool allowlists, extra prompts, and confirmation policy for a flow.
- Modes are Markdown-backed session presets that resolve into an ephemeral active agent profile.
- Skills are Markdown-backed capability packs that can append prompt guidance and contribute extra tools for the current session.
- Tool definitions and routing payloads are exchanged with LLMs as YAML.
- CLI now uses a multi-pane Textual workspace for interactive mode.
- Runtime-driven user interaction now uses a structured protocol that supports free-form text, buttons, radio groups, and checklists from both the basic CLI and the Textual UI.
- CLI switches flow, agent, and LLM profile at runtime from both commands and UI controls.
- The runtime supports flow handoff and per-flow/per-handoff LLM overrides.
- Gemini provider is implemented with the `google.genai` package (`google-genai` dependency).

## Built-In Runtime

- The package-owned `core` plugin lives under `pocketcode/plugins/core/`
- Repo-shipped workspace plugins live under `.pocketcode/plugins/`
- The default flow is `core::react`
- `.pocketcode/plugins/workspace_builder/` ships a dedicated authoring agent for creating and editing workspace plugin resources plus workspace-level assets such as tools, prompts, skills, and agents.
- Shared filesystem tool behavior is implemented once in `pocketcode/plugins/core/tools/filesystem.py`; plugin-local filesystem modules re-export that canonical implementation to avoid drift.
- Structured file operation tools now also live in `pocketcode/plugins/core/tools/file_ops.py`, covering interactive file/folder selection, line/pattern-based extraction, staged replacements with diff previews, and explicit apply/cancel steps.
- Git and context elephant store tools now live in separate workspace plugins at `.pocketcode/plugins/workspace_git/` and `.pocketcode/plugins/workspace_context/`; built-in flows reference those workspace plugins explicitly. The remaining public compatibility surface is the `pocketcode.tools` package exports, while `pocketcode.plugins.core.tools.context_elephant_store_tools` remains only as a compatibility shim for context-elephant imports.

## Workspace Resources

Pocketcode also loads workspace-local resources from the workspace root:

- `.pocketcode/plugins/`: workspace plugin folder discovered through `runtime.plugin_paths`
- `.pocketcode/plugins/workspace_builder/`: example repo-shipped workspace plugin for authoring `plugin.yaml`, flows, prompts, agents, tools, skills, and other `.pocketcode/` assets
- `.pocketcode/agents/`: workspace agent YAML files
- `.pocketcode/modes/`: workspace Markdown mode files
- `.pocketcode/skills/`: workspace skill folders containing `SKILL.md` plus optional `tools/`, `scripts/`, `references/`, and `assets/`
- `.pocketcode/skills/pocketcode-workspace-builder/`: umbrella skill pack for the workspace builder, with focused companion skills for PocketFlow graphs, plugin authoring, profiles/prompts, tools/runtime, and workspace assets
- `.pocketcode/tools/`: shared Python tools auto-registered under the `workspace` namespace
- `.pocketcode/prompts/`: shared prompt files registered under the `workspace` namespace and usable as fallback prompt files for plugin agents and agent `extra_prompts`

For shared workspace tools, Pocketcode auto-discovers public tool exports from Python files in `.pocketcode/tools/`. A module can expose tools either through a `TOOLS` export or through public top-level callables / `BaseTool` classes.
The repo now ships `.pocketcode/tools/file_ops.py` as the reference pattern for workspace tool re-exports, making the same file selection and staged editing tools available as `workspace::select_filesystem_entry`, `workspace::extract_text`, `workspace::stage_text_replace`, `workspace::apply_staged_edit`, and `workspace::cancel_staged_edit`.

## Discovery Controls

Pocketcode supports two ways to make discovered resources unavailable without deleting them:

- Rename any discovered file or folder so one path component contains `.disabled`.
- Add gitignore-style rules to `.pocketcodeignore`.

`.disabled` behavior:

- Works for plugins, workspace agents, modes, skills, prompts, tools, and plugin-local `agents/`, `prompts/`, `tools/`, and flow modules.
- If any parent folder contains `.disabled`, everything under it is skipped.

`.pocketcodeignore` behavior:

- Workspace-owned resources under `.pocketcode/` use: `<workspace>/.pocketcode/.pocketcodeignore`
- Built-in `core` and external plugin roots use: `<workspace>/.pocketcodeignore`
- Supports blank lines, `#` comments, glob patterns, directory rules with trailing `/`, and `!` re-includes.

Examples:

```gitignore
# .pocketcode/.pocketcodeignore
tools/*.py
!tools/keep.py
skills/old-skill/
```

```gitignore
# workspace root .pocketcodeignore
core/prompts/drafts/
my_external_plugin/tools/*.py
```

## Configuration

Main config file: `./pocketcode.yml` (required in workspace root)

Key sections:

- `llm.providers`: provider credentials/settings
- `llm.profiles`: named LLM configs used by agents/internal flows
- `llm.default_profile`: default profile name
- `runtime`: flow defaults, internal runtime flow, plugin paths, and tool confirmation policy

Supported providers:

- `gemini` (via `google.genai`)
- OpenAI-compatible: `openai`, `openrouter`, `xai`, `requesty`

Provider entries can be either a plain API key string or an object:

```yaml
llm:
  providers:
    gemini:
      api_key: ${GEMINI_API_KEY}
      use_vertexai: false
      # Set use_vertexai: true for Vertex AI (OAuth/ADC), then also set:
      # project: your-gcp-project-id
      # location: global
    openrouter:
      api_key: ${OPENROUTER_API_KEY}
      base_url: https://openrouter.ai/api/v1
  profiles:
    gemini_default:
      provider: gemini
      model: gemini-2.5-pro-preview-02-25
  default_profile: gemini_default
```

Gemini auth behavior:

- `use_vertexai: false` (default): uses Gemini Developer API with `api_key`
- `use_vertexai: true`: uses Vertex AI and requires OAuth/ADC credentials (API keys are not accepted by Vertex endpoints)

Default OpenAI-compatible base URLs:

- `openai`: OpenAI SDK default
- `openrouter`: `https://openrouter.ai/api/v1`
- `xai`: `https://api.x.ai/v1`
- `requesty`: `https://router.requesty.ai/v1`

Tool confirmation policy supports `allow|confirm|deny` at multiple levels:

- Global defaults: `runtime.tool_confirmation`
- Global per-tool rules: `runtime.tool_confirmation.tool_policies`
- Global per-flow defaults and per-flow tool rules: `runtime.tool_confirmation.agent_policies`
- Session overrides via `/confirm ...` commands

Default behavior is confirmation-first (`confirm`) unless you explicitly override it in config or via CLI (`--auto-confirm-tools`).

LLM routing supports layered overrides for multi-flow and nested flows:

- handoff-level (`source_flow->target_flow`) in config and CLI
- flow-level in config and CLI
- global CLI override and defaults

Precedence is: CLI flow > config flow > CLI global > dynamic handoff/flow choice > active agent > flow default > `llm.default_profile`.

## CLI Commands

Universal commands:

- `/list <flows|prompts|modes|skills|agents|llms|tools>`
- `/set <flow|llm|llm-flow|llm-handoff> ...`
- `/flow <flow_name|auto> [--agent <agent_name>]`
- `/mode <list|show|switch|clear> ...`
- `/skill <list|show|enable|disable> ...`
- `/prompts`
- `/agent <list|show|switch|clone|edit|tools|policy> ...`
- `/stop`, `/cancel`
- `/reload`, `/status`
- `/context ...`
- `/confirm ...`

Textual-only commands:

- `/copy`: copy the last assistant response
- `/copy-all`: copy the full response console output

Textual-only commands are intentionally excluded from universal `/help` output and shared prompt suggestions.

Startup flags:

- `--flow <flow_name|auto>` selects the initial flow.
- `--llm <profile_name>` sets the global LLM override.
- `--prompt "..."` runs one request non-interactively.
- `--workflow` and the deprecated `--agent` startup alias are no longer supported.

Compatibility aliases remain available:

- `/flows`, `/prompts`, `/agents`, `/llms`, `/tools`
- Short aliases: `/ls`, `/ag`, `/ap`, `/lm`, `/lf`, `/la`, `/lh`, `/st`, `/c`, `/r`, `/q`

Listing behavior:

- `/agent list` and `/list agents` show named agent profiles only; synthesised flow-default profiles are excluded.
- `/skill list` and `/list skills` show individual skills grouped by their top-level name prefix, such as `azure`, `pocketcode`, or `pocketflow`.

Textual keyboard shortcuts:

- `Tab`: complete current prompt input
- `F1`, `F2`, `F5`: switch `Chat`, `Control`, and `Run` views
- `F3`: open the asset editor picker
- `F4`: open the asset clone picker
- `F6`: open the popup asset picker for active flow, agent profile, LLM override, workspace mode, theme, and session confirmation; use arrow keys plus `Enter` to choose
- `F10`: toggle the right inspector panel
- `Alt+1`, `Alt+2`, `Alt+5`: fallback view switching
- `Ctrl+R`: reload runtime
- `Ctrl+L`: clear output
- `Ctrl+Shift+A`: copy full response console output
- `Ctrl+Y`: copy last assistant response
- `Ctrl+Q`: quit Textual UI
- searchable selection popups support `Ctrl+Down` to jump into the list, `Ctrl+Up` to return to search, and `Space` to toggle the highlighted entry

Interactive workspace views:

- `Chat`: conversation and command entry
- `Control`: runtime/session selectors and toggles for workspace mode, theme, active agent profile, global LLM override, and session confirmation
- `Control`: includes popup pickers for profile, LLM, skills, tools, tool policies, session confirmation, and system settings
- top header chips mirror the current `Agent` and `LLM` selection
- `Control` selectors apply only to live user selections; placeholder values used during refresh are ignored so flow/agent cycling does not re-enter itself
- `Run`: inspect the latest runtime path, effective LLM/agent state, token usage, cost, and live in-flight runtime events while a request is still running
- flow/agent/tool metadata is reused across a single UI refresh so switching the active flow stays responsive
- the Textual client now derives one UI snapshot per refresh and applies only changed widget state, instead of imperatively rebuilding each pane in multiple passes

Inspector panels:

- `Session Context`: current context counts and the active file/folder/url/snippet list
- `Agents For Active Flow`: quick agent switcher
- `Active Tools`: effective tool scope after agent filtering
- `Prompt Sources`: flow prompt sources plus agent extra prompts
- the left navigation pane is scrollable, matching the right inspector pane

Interactive workspace presets:

- `Balanced`: chat-first layout with both side panels visible
- `Chat Focus`: larger chat area with the left navigator hidden
- `Control Desk`: opens directly into the form-driven control surface
- `Minimal`: pure chat canvas with both side panels hidden
- `Review`: jumps to the run inspector for runtime/debugging work

Theme presets:

- `Ocean`: blue/cyan high-contrast default
- `Forest`: green terminal-inspired workspace
- `Ember`: warm orange/brown review-focused palette

Agent editing in the Textual UI:

- plugin and synthesised agents are read-only until cloned to a workspace agent
- workspace-backed agents can edit `llm_profile`, tool allowlists, per-tool confirmation overrides, confirmation defaults, and `extra_prompts`
- tool allowlists, tool policy overrides, and skills now use a three-step model: `Apply` saves a persisted last-used runtime selection, `Reset` clears the last-used override and falls back to defaults, and `Save as Default` writes the current state into the default config
- last-used tool allowlists, tool policy overrides, and skill selections are reloaded automatically on startup
- tools and prompts can be changed from lists, toggles, policy selectors, and text boxes instead of editing YAML manually

Modes and skills:

- modes live in `.pocketcode/modes/*.md` and use YAML front matter plus Markdown body
- the mode body becomes inline system-prompt text for an ephemeral active profile
- front matter can select a `flow` or base `agent`, override `llm_profile`, set `tools`, `extra_prompts`, and `tool_confirmation`
- skills live in `.pocketcode/skills/<name>/SKILL.md`
- a skill can add prompt guidance, reference extra prompt files, and contribute extra tool modules from `tools/*.py`
- skill-provided tools are registered under the `skill.<skill_name>.*` namespace while the skill is enabled

Mode example:

```md
---
name: review
description: Review mode
flow: core::react
llm_profile: gemini_default
tool_confirmation:
  default: confirm
---
Focus on bugs, regressions, and missing tests.
```

Skill example:

```md
---
name: python-testing
description: Pytest test loop
tools:
  - core.read_file
extra_prompts:
  - references/style.md
---
Reproduce failures first, then patch minimally.
```

Output box behavior:

- output text is selectable with mouse/keyboard
- copy selected text with your terminal copy shortcut (for example `Ctrl+Shift+C`)
- the TUI retains only the most recent 400 output lines and inserts a trim notice once older history is dropped, which keeps long sessions responsive
- background runs now append lifecycle updates as they happen, including agent turns, LLM calls, tool execution, handoffs, and confirmation waits

Live request handling:

- the Textual client now starts requests on a background run handle instead of waiting for a single blocking `process_request()` call to finish
- the main input stays available during a run so it can answer runtime prompts and tool confirmations without falling back to raw terminal `input()`
- the main input now accepts `/stop` or `/cancel` while a run is active and requests cooperative cancellation of the current run
- `execute_command` now uses a managed subprocess path, so stop requests can terminate the underlying OS command; broader hard-stop design notes live in `docs/run_cancellation.md`
- runtime progress is surfaced through a queued event stream today, which also provides the execution seam needed for future token/delta streaming
- the fallback basic CLI and one-shot `--prompt` mode now print runtime events as they happen, including tool calls, handoffs, handoff returns, agent transition decisions, and cancellation state

Prompt suggestions include universal commands, flows, agents, and LLM profiles.

Textual-only commands stay discoverable through Textual-local help and shortcuts instead of the shared suggestion list.

Header rows:

- the top header now only shows the active `Agent` and `LLM`
- runtime flow details stay in the inspector and run view instead of a dedicated header row

Context counts and item details now live in the right-hand inspector instead of the top strip.

Terminal font size note:

- Pocketcode can change colors, density, emphasis, borders, and layout inside the TUI
- the current TUI uses an extra-compact header/footer/sidebar layout with tighter gaps and narrower panels to reduce visual bulk
- actual font size is still controlled by your terminal emulator rather than the app
- if you need physically smaller characters, reduce the font size or zoom level in your terminal emulator

Optional cost pricing map:

```yaml
runtime:
  llm_pricing:
    gemini-2.5-flash:
      input_per_1k: 0.000075
      output_per_1k: 0.00030
```

## Plugin + Workflow Authoring

See: `docs/plugin_architecture.md`

## Quick Start

1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -e .
   ```
3. Set environment variable:
   ```bash
   export GEMINI_API_KEY=...
   ```
   If your shell or `.env` has `GOOGLE_GENAI_USE_VERTEXAI=True`, either remove it or set `llm.providers.gemini.use_vertexai: true` and configure ADC + project/location.
4. Run:
   ```bash
   pocketcode
   ```

## Non-Interactive Usage

- Interactive chat mode requires interactive stdin.
- If stdout is not a TTY, Pocketcode falls back to the basic line-based CLI.
- For scripts/CI/non-interactive stdin, run a single request and exit:
  ```bash
  pocketcode --prompt "Summarize the current workspace"
  ```
- You can also pipe one-shot input without `--prompt`:
  ```bash
  echo "Summarize the current workspace" | pocketcode
  ```

## Plugin Authoring

Plugins follow the unified plugin model (003-unified-plugin-namespace):

- Workspace plugins live in `.pocketcode/plugins/<name>/`.
- The only package-owned plugin is `pocketcode/plugins/core/`.
- Declare everything in `plugin.yaml` with `schema_version: 1`.
- Tools are declared as `local_name: "tools/file.py:ClassName"`.
- Flows are declared with `module:` + `entry_fn:` pointing to a zero-arg Python
  factory that returns a PocketFlow `Flow`.
- Top-level `prompts:` entries are loaded into the plugin prompt registry.
- All resources are addressable as `plugin_name.resource_name`.

Quick example:

```yaml
# .pocketcode/plugins/my_plugin/plugin.yaml
schema_version: 1
name: my_plugin
description: My custom plugin.

tools:
  my_tool: "tools/my_tool.py:MyTool"

flows:
  my_agent:
    module: "flows/my_agent.py"
    entry_fn: "create_flow"
    tools: [my_tool]
```

Full walkthrough: [`specs/003-unified-plugin-namespace/quickstart.md`](specs/003-unified-plugin-namespace/quickstart.md)
