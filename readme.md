# Pocketcode

Pocketcode is an extensible terminal AI coding assistant built around PocketFlow.

## What Changed

Pocketcode now uses a small plugin-first core:

- Plugins declare tools, prompts, and agents in `plugin.yaml`.
- Agents are the primary runtime unit and are implemented as PocketFlow `Flow` factories.
- Agent prompts live in external Markdown files with `{{ include:path.md }}` support.
- Agents support Python `pre`, `steps`, and `post` handlers alongside LLM and deterministic execution modes.
- Agent profiles can override LLM selection, tool allowlists, extra prompts, and confirmation policy.
- Tool definitions and routing payloads are exchanged with LLMs as YAML.
- CLI now uses a Textual TUI for interactive mode.
- CLI switches agent, agent profile, and LLM profile at runtime.
- The runtime supports agent handoff and per-agent/per-handoff LLM overrides.
- Gemini provider is implemented with the `google.genai` package (`google-genai` dependency).

## Built-In Runtime

- Built-in plugins live under `pocketcode/plugins/`
- The default agent is `core::react`

## Configuration

Main config file: `./pocketcode.yml` (required in workspace root)

Key sections:

- `llm.providers`: provider credentials/settings
- `llm.profiles`: named LLM configs used by agents/internal flows
- `llm.default_profile`: default profile name
- `runtime`: agent defaults, internal runtime flow, plugin paths, and tool confirmation policy

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
- Global per-agent defaults and per-agent tool rules: `runtime.tool_confirmation.agent_policies`
- Session overrides via `/confirm ...` commands

Default behavior is confirmation-first (`confirm`) unless you explicitly override it in config or via CLI (`--auto-confirm-tools`).

LLM routing supports layered overrides for multi-agent and nested flows:

- handoff-level (`source_agent->target_agent`) in config and CLI
- agent-level in config and CLI
- global CLI override and defaults

Precedence is: CLI agent > config agent > CLI global > dynamic handoff/agent choice > active agent profile > agent default > `llm.default_profile`.

## CLI Commands

- `/list <agents|llms|tools>`
- `/set <agent|llm|llm-agent|llm-handoff> ...`
- `/agent-profile <list|show|switch|clone> ...`
- `/reload`, `/status`
- `/context ...`
- `/confirm ...`

Compatibility aliases remain available:

- `/agents`, `/llms`, `/tools`
- `/agent`, `/llm`, `/llm-agent`, `/llm-handoff`
- Short aliases: `/ls`, `/ag`, `/ap`, `/lm`, `/la`, `/lh`, `/st`, `/r`, `/q`

Textual keyboard shortcuts:

- `Tab`: complete current prompt input
- `Ctrl+]`: switch to next agent
- `Ctrl+[`: switch global LLM override (cycles `none` + profiles)
- `Ctrl+T`: toggle top stats panel
- `Ctrl+Space`: complete current prompt input
- `Ctrl+Shift+A`: copy full response console output
- `Ctrl+Y`: copy last assistant response
- `Ctrl+Q`: quit Textual UI

Output box behavior:

- output text is selectable with mouse/keyboard
- copy selected text with your terminal copy shortcut (for example `Ctrl+Shift+C`)

Prompt suggestions include commands, agents, agent profiles, and LLM profiles.

Textual copy commands:

- `/copy`: copy the last assistant response
- `/copy-all`: copy the full response console output

Top stats panel includes:

- context stats (`files`, `folders`, `urls`, `snippets`, `snippet_chars`)
- aggregated token usage (`in`, `out`, `total`) for the latest request
- estimated USD cost (if pricing is configured)

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

- Each plugin lives in `pocketcode/plugins/<name>/`.
- Declare everything in `plugin.yaml` with `schema_version: 1`.
- Tools are declared as `local_name: "tools/file.py:ClassName"`.
- Agents are declared with `module:` + `entry_fn:` pointing to a zero-arg Python
  factory that returns a PocketFlow `Flow`.
- Top-level `prompts:` entries are loaded into the plugin prompt registry.
- All resources are addressable as `plugin_name.resource_name`.

Quick example:

```yaml
# pocketcode/plugins/my_plugin/plugin.yaml
schema_version: 1
name: my_plugin
description: My custom plugin.

tools:
  my_tool: "tools/my_tool.py:MyTool"

agents:
  my_agent:
    module: "agents/my_agent.py"
    entry_fn: "create_flow"
    tools: [my_tool]
```

Full walkthrough: [`specs/003-unified-plugin-namespace/quickstart.md`](specs/003-unified-plugin-namespace/quickstart.md)
