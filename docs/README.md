# Documentation

Current docs:

- [`plugin_architecture.md`](./plugin_architecture.md): active plugin/component/agent-composition authoring guide.
- Runtime note: agents are the primary runtime unit; internal graph flows execute through kind-specific PocketFlow runtime nodes in `pocketcode/core/runtime_nodes.py`.
- Agent note: agents support per-agent hooks, execution mode (`node|flow`), and policy-based handoffs (`return_to_caller`, `context_mode`).

Obsolete planning documents for the retired mode-flow architecture were removed.
