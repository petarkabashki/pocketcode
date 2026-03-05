# Data Model: PocketFlow Agents and Plugin Factory

**Feature**: [002-pocketflow-agents](../spec.md)
**Date**: 2026-03-05

## 1. Entity Definitions

### Plugin Class
The core container for plugin resources, returned by the `get_plugin()` factory.
- `name`: string (Unique slug for the plugin)
- `description`: string (Short purpose description)
- `agents`: `Dict[str, Union[Flow, AsyncFlow]]` (Mapping of names to PocketFlow flows)
- `tools`: `List[Union[Callable, BaseTool]]` (List of functions or Tool instances)
- `prompts`: `Dict[str, str]` (Mapping of names to prompt strings/templates)
- `metadata`: `Dict[str, Any]` (Version, author, license, etc.)

### PluginContext Class
A lightweight object injected into the `shared` dictionary of a Flow to provide easy access to the plugin's local resources.
- `plugin_name`: string
- `tools`: `Dict[str, ToolProxy]` (Bound versions of the plugin's tools)
- `prompts`: `Dict[str, str]` (The plugin's local prompts)
- `get_prompt(name: str) -> str`: Method to retrieve a prompt with fallback/injection logic.
- `call_tool(name: str, **kwargs) -> Any`: Method to invoke a local tool through the runtime.

---

## 2. Relationships

- **PluginManager** 1 —> * **Plugin** (Discovered and held in memory)
- **Plugin** 1 —> * **Flow** (Each plugin can expose multiple programmatic agents)
- **Flow** 1 —> * **Node** (Standard PocketFlow structure)
- **Node** <— uses — **PluginContext** (Provided via `shared["_plugin"]`)

---

## 3. Data Flow

### 1. Initialization Phase
1. `PluginManager.load()` iterates through plugin directories.
2. For each directory `D`:
   a. Try to import `D` as a module.
   b. Look for `get_plugin()` in `importlib.import_module(D.name)`.
   c. Call `get_plugin(**config)` to get a `Plugin` instance.
   d. Register the plugin's agents, tools, and prompts in the global registries.

### 2. Execution Phase
1. User selects an agent `A` from plugin `P`.
2. `AgentRuntime` identifies `A` as a `PocketFlowAgent`.
3. `AgentRuntime` creates a `PluginContext` for `P`.
4. `AgentRuntime` initializes a `shared` dictionary and sets `shared["_plugin"] = PluginContext`.
5. `AgentRuntime` runs `A.run(shared)`.

---

## 4. State Transitions (Agents)

- **not-started**: Agent registered but not active.
- **running**: Flow is executing nodes.
- **waiting-for-tool**: Node is awaiting a tool result (optional, if using async).
- **completed**: Flow reached a leaf node and returned a final action.
- **error**: Flow crashed or an unhandled exception occurred in a node.
