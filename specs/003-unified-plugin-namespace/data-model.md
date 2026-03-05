# Data Model: Unified Plugin Namespace Architecture

**Phase**: 1 (Design) | **Feature**: `003-unified-plugin-namespace` | **Date**: 2026-03-05

---

## Entity Overview

| Entity | Identifier | Owner | Registered In |
|---|---|---|---|
| Plugin | `name` (str) | \u2014 | `PluginManager.plugin_roots` |
| Tool | `plugin_name.tool_name` | Plugin | `NamespaceRegistry[Callable]` |
| Agent | `plugin_name.agent_name` | Plugin | `NamespaceRegistry[AgentDefinition]` |
| Prompt | `plugin_name.prompt_name` | Plugin | `NamespaceRegistry[str]` |
| LLM Profile | `profile_name` (unqualified) | Plugin | `PluginManager.llm_profiles` |
| ParsedManifest | file path | \u2014 | Transient (load time only) |
| NamespaceRegistry | \u2014 | Runtime | `RegistryHolder._registry` |

---

## Plugin

The fundamental organisational unit. Every resource is owned by exactly one Plugin.

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | `str` | YES | Authoritative namespace identifier. Must be unique across all loaded plugins. Declared in manifest; plugin directory name is fallback only. |
| `root` | `Path` | YES | Absolute path to the plugin directory. All relative paths in the manifest resolve against this. |
| `schema_version` | `int` | YES | Must be `1` for new manifests; `0` for shim-loaded `agent.yaml` (one-cycle compat). |
| `description` | `str` | NO | Human-readable purpose of the plugin. |

**Validation rules**:
- `name` must match `[a-zA-Z0-9_]+` (no dots \u2014 dots are the namespace separator).
- Two plugins with the same `name` \u2192 hard `ERROR`; second plugin skipped.
- `name` declared in manifest overrides the directory name; directory name used only when `name` key is absent.

---

## Tool

A callable capability owned by a plugin and registered in the `tools` NamespaceRegistry.

| Field | Type | Required | Notes |
|---|---|---|---|
| `qualified_name` | `str` | YES | `plugin_name.tool_name` \u2014 the primary lookup key. |
| `local_name` | `str` | YES | Key as declared in the plugin manifest `tools:` section. |
| `plugin` | `str` | YES | Owning plugin name. |
| `impl` | `Callable \| Type` | YES | The loaded tool class or callable instance. |
| `reference` | `str` | YES | Raw manifest reference: `module.Class` or `path.py:Class`. |

**Validation rules**:
- `local_name` must be unique within the owning plugin.
- `qualified_name` must be globally unique \u2014 collision is a hard error at load time.
- If the implementation file is missing or the class cannot be loaded, the tool is skipped (log `ERROR`); other tools in the plugin continue loading.

---

## Agent

A PocketFlow `Flow` owned by a plugin. Spans from a single-node LLM call to a multi-agent orchestration pipeline.

| Field | Type | Required | Notes |
|---|---|---|---|
| `qualified_name` | `str` | YES | `plugin_name.agent_name`. |
| `local_name` | `str` | YES | Key as declared in the plugin manifest `agents:` section. |
| `plugin` | `str` | YES | Owning plugin name. |
| `description` | `str` | NO | Human-readable purpose. |
| `module` | `str` | YES | Relative path to the Python file containing the factory (e.g., `agents/koder_agent.py`). |
| `entry_fn` | `str` | YES | Name of the zero-argument factory function that constructs and returns the PocketFlow `Flow`. |
| `flow_instance` | `Flow \| None` | runtime | Populated by calling `entry_fn()` at registration time. `None` until loaded. |
| `llm_profile` | `str \| None` | NO | LLM profile name passed to the factory via shared store or closure. |
| `tools` | `list[str]` | NO | Tool references used by this agent (local or qualified). Resolved against the NamespaceRegistry at runtime. |
| `prompts` | `dict[str, str]` | NO | Named prompt references within this agent's definition. Values are file paths relative to plugin root or qualified prompt names. |

**State transitions**: Agent moves from `unloaded` \u2192 `registered` (factory called, `Flow` stored) \u2192 `active` (session running) \u2192 `registered` (session complete). During hot-reload: sessions hold a reference to the pre-reload `AgentDefinition`; new sessions get the new definition after the registry swap.

**Validation rules**:
- Both `module` and `entry_fn` are required. Missing either \u2192 `ManifestSchemaError`, agent skipped.
- `tools` list entries are resolved lazily at session start (not at load time) to allow forward references.
- An orchestrating agent (e.g., micromanager) is architecturally identical \u2014 its `Flow` contains `Node`s that call `registry.agents.resolve(\"plugin.sub_agent\")` and run their `flow_instance`.

---

## Prompt

A named text resource owned by a plugin.

| Field | Type | Required | Notes |
|---|---|---|---|
| `qualified_name` | `str` | YES | `plugin_name.prompt_name`. |
| `local_name` | `str` | YES | Key as declared in the `prompts:` section. |
| `plugin` | `str` | YES | Owning plugin name. |
| `content` | `str` | YES | Full text content, loaded from file at registration time. |
| `source_path` | `Path` | YES | Absolute path to the source `.md` file. |

**Validation rules**:
- If the prompt file is missing, the prompt is skipped (log `ERROR`); other prompts in the plugin continue loading.
- Cross-plugin prompt references use qualified form: `plugin_name.prompt_name`.

---

## ParsedManifest

Transient dataclass produced by `load_manifest()`. Consumed by `PluginManager` and discarded after registration.

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `int` | `1` for native; `0` for shim-loaded `agent.yaml`. |
| `name` | `str` | Plugin name. |
| `description` | `str` | \u2014 |
| `plugin_root` | `Path` | Absolute path to plugin directory. |
| `tools` | `Dict[str, str]` | `{local_name: reference}` |
| `agents` | `Dict[str, Dict[str, Any]]` | `{local_name: {module, entry_fn, ...}}` |
| `prompts` | `Dict[str, str]` | `{local_name: relative_file_path}` |
| `llm_profiles` | `Dict[str, Dict[str, Any]]` | `{profile_name: config_dict}` |

---

## NamespaceRegistry

The runtime structure that maps qualified names to loaded implementations. One instance per resource type (`tools`, `agents`, `prompts`).

### Internal structure

```
_ns   : Dict[str, Dict[str, T]]   # {plugin \u2192 {name \u2192 impl}}   \u2190 source of truth
_flat : Dict[str, T]              # {"plugin.name" \u2192 impl}      \u2190 O(1) qualified lookup
_bare : Dict[str, list[str]]      # {"name" \u2192 ["plugin.name"]}  \u2190 O(1) unqualified + ambiguity
```

### Python API skeleton

```python
class RegistryError(Exception): ...

class NamespaceRegistry(Generic[T]):
    def register(self, plugin: str, name: str, impl: T) -> None: ...
    def unregister_plugin(self, plugin: str) -> None: ...
    def resolve(self, ref: str, *, context_plugin: str | None = None) -> T: ...
    def list_all(self) -> list[str]: ...
    def list_by_plugin(self, plugin: str) -> dict[str, T]: ...
    def plugins(self) -> list[str]: ...
    def items(self) -> Iterator[tuple[str, T]]: ...
    def __contains__(self, ref: str) -> bool: ...
    def snapshot(self) -> NamespaceRegistry[T]: ...
```

Full implementation skeleton is in [contracts/registry-api.md](contracts/registry-api.md).

### Instantiation in PluginManager

```python
self.tools:    NamespaceRegistry[Callable]         = NamespaceRegistry()
self.agents:   NamespaceRegistry[AgentDefinition]  = NamespaceRegistry()
self.prompts:  NamespaceRegistry[str]              = NamespaceRegistry()
self.llm_profiles: Dict[str, Dict[str, Any]]       = {}  # unqualified; single namespace
```

### Collision detection

| Scenario | Behaviour |
|---|---|
| Two plugins with same `name` | `ERROR` at `PluginManager.load()`, second plugin skipped entirely |
| `register()` called with existing `_flat` key | `RegistryError` raised; `PluginManager` logs `ERROR`, skips that plugin |
| Same local name across two different plugins | Silent at `register()` time; `_bare[name]` grows to length 2; `ERROR` deferred to `resolve()` call |

### Hot-reload (FR-011)

1. Build `new_pm = PluginManager(...)` and call `new_pm.load()` **outside** any lock.
2. Acquire `_registry_lock`; assign `_active_registry = new_pm`; release lock.
3. Set `old_pm = None`. CPython refcount frees the old object when the last in-flight session completes.
4. New sessions call `holder.get()` and receive `new_pm`. In-flight sessions retain their local reference to `old_pm` and run to completion uninterrupted.

---

## Entity Relationship Diagram

```
Plugin ──owns──\u25ba Tool       (1:many)
Plugin ──owns──\u25ba Agent      (1:many)
Plugin ──owns──\u25ba Prompt     (1:many)
Plugin ──owns──\u25ba LLM Profile (1:many)

Agent ──references──\u25ba Tool      (by qualified name, resolved at session start)
Agent ──references──\u25ba Prompt    (by qualified name, resolved at load time)
Agent ──references──\u25ba Agent     (as PocketFlow sub-flow, by qualified name)

NamespaceRegistry[Tool]    \u2190── registered by ──\u25ba PluginManager
NamespaceRegistry[Agent]   \u2190── registered by ──\u25ba PluginManager
NamespaceRegistry[str]     \u2190── registered by ──\u25ba PluginManager (prompts)

ParsedManifest ─\u25ba consumed by ─\u25ba PluginManager (transient; discarded after load)
RegistryHolder ─\u25ba holds active ─\u25ba PluginManager (snapshot-swap on hot-reload)
```



```
_ns   : Dict[str, Dict[str, T]]   # {plugin → {name → impl}}   ← source of truth
_flat : Dict[str, T]              # {"plugin.name" → impl}      ← O(1) qualified lookup
_bare : Dict[str, list[str]]      # {"name" → ["plugin.name"]}  ← O(1) unqualified + ambiguity
```

**Why not just one?**

| Option | Verdict | Fatal gap |
|--------|---------|-----------|
| Nested only `{plugin: {name: impl}}` | Rejected | Qualified lookup is O(plugins); no bare-name index |
| Flat only `{"plugin.name": impl}` | Rejected | Plugin-grouped enumeration requires O(all_keys) scan; no atomic scope clear per plugin |
| Both nested + flat | Accepted | Covers all access patterns; rebuilt together atomically |

The `_bare` reverse index is the critical third structure: it makes unqualified lookup O(1) *and* gives immediate cardinality for ambiguity detection without scanning `_flat`.

---

## 2. Backward-Compatible Unqualified Lookup

`_bare` maps every registered local name to a list of qualified keys that carry it.
Resolution at call time:

```
ref contains "."  →  direct _flat lookup (hard error if missing)
ref has no "."    →
    _bare[ref] missing          → KeyError (resource not found)
    len(_bare[ref]) == 1        → WARNING (log qualifying form), return impl
    len(_bare[ref]) >  1        → ERROR   (list all owners), raise AmbiguousReference
```

No scanning of plugins at resolve-time. Reverse index is built incrementally during `register()`.

---

## 3. Python Class Skeleton

```python
from __future__ import annotations

import copy
import logging
from collections import defaultdict
from typing import Dict, Generic, Iterator, List, Optional, TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


class RegistryError(Exception):
    """Raised on unresolvable or ambiguous reference."""


class NamespaceRegistry(Generic[T]):
    """
    Unified namespace registry for plugin resources (tools / agents / prompts).

    Internal invariant: _flat and _bare are always consistent with _ns.
    Never modify them individually — use register() and _rebuild_indices().
    """

    def __init__(self) -> None:
        self._ns: Dict[str, Dict[str, T]] = {}           # {plugin: {name: impl}}
        self._flat: Dict[str, T] = {}                    # {"plugin.name": impl}
        self._bare: Dict[str, List[str]] = defaultdict(list)  # {"name": ["p.name"]}

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def register(self, plugin: str, name: str, impl: T) -> None:
        """Register a resource. Hard error on qualified-name collision."""
        qname = f"{plugin}.{name}"
        if qname in self._flat:
            existing_plugin = qname.split(".")[0]
            raise RegistryError(
                f"Qualified name collision: '{qname}' already registered by "
                f"plugin '{existing_plugin}'. Cannot register from '{plugin}'."
            )
        self._ns.setdefault(plugin, {})[name] = impl
        self._flat[qname] = impl
        self._bare[name].append(qname)

    def unregister_plugin(self, plugin: str) -> None:
        """Remove all resources owned by *plugin* (used before hot-reload rebuild)."""
        for name in list(self._ns.get(plugin, {})):
            qname = f"{plugin}.{name}"
            self._flat.pop(qname, None)
            owners = self._bare.get(name, [])
            if qname in owners:
                owners.remove(qname)
            if not owners:
                self._bare.pop(name, None)
        self._ns.pop(plugin, None)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def resolve(
        self,
        ref: str,
        *,
        context_plugin: Optional[str] = None,
    ) -> T:
        """
        Resolve a qualified *or* unqualified reference.

        If *context_plugin* is given, bare names are first checked within that
        plugin before falling back to the global bare-name index (intra-plugin
        local resolution per FR-004).
        """
        if "." in ref:
            # Qualified path — O(1)
            impl = self._flat.get(ref)
            if impl is None:
                raise RegistryError(f"Resource not found: '{ref}'")
            return impl

        # Unqualified — check local plugin first (FR-004)
        if context_plugin:
            local_impl = self._ns.get(context_plugin, {}).get(ref)
            if local_impl is not None:
                return local_impl

        owners = self._bare.get(ref, [])
        if not owners:
            raise RegistryError(f"Resource not found: '{ref}'")
        if len(owners) == 1:
            qname = owners[0]
            logger.warning(
                "Unqualified reference '%s' resolved to '%s'. "
                "Use the qualified form to silence this warning.",
                ref,
                qname,
            )
            return self._flat[qname]
        # Ambiguous — hard error
        raise RegistryError(
            f"Ambiguous unqualified reference '{ref}': owned by "
            + ", ".join(f"'{q}'" for q in owners)
            + ". Use a qualified name."
        )

    # ------------------------------------------------------------------
    # Enumeration
    # ------------------------------------------------------------------

    def list_all(self) -> List[str]:
        """Return all qualified names sorted deterministically."""
        return sorted(self._flat.keys())

    def list_by_plugin(self, plugin: str) -> Dict[str, T]:
        """Return {name: impl} for all resources owned by *plugin*."""
        return dict(self._ns.get(plugin, {}))

    def plugins(self) -> List[str]:
        """Return sorted list of all registered plugin namespaces."""
        return sorted(self._ns.keys())

    def items(self) -> Iterator[tuple[str, T]]:
        """Iterate (qualified_name, impl) over all resources."""
        return iter(self._flat.items())

    def __contains__(self, ref: str) -> bool:
        return ref in self._flat

    # ------------------------------------------------------------------
    # Atomic snapshot-swap (FR-011)
    # ------------------------------------------------------------------

    def snapshot(self) -> "NamespaceRegistry[T]":
        """
        Return a deep copy suitable for atomic swap.

        Hot-reload pattern:
            new_reg = NamespaceRegistry()
            # ... populate new_reg from reloaded plugins ...
            atomic_ref.registry = new_reg   # single assignment, GIL-safe
            # in-flight sessions hold old snapshot; new sessions get new_reg
        """
        clone: NamespaceRegistry[T] = NamespaceRegistry()
        clone._ns = copy.deepcopy(self._ns)
        clone._flat = copy.deepcopy(self._flat)
        clone._bare = copy.deepcopy(self._bare)
        return clone
```

---

## 4. Collision Detection at Load Time

Collision detection is a property of `register()`, not a separate pass.

```
register(plugin, name, impl):
    qname = f"{plugin}.{name}"
    if qname in _flat:
        ERROR  "Qualified name collision: '{qname}'..."  ← hard error, caller skips plugin
    else:
        _ns[plugin][name]  = impl
        _flat[qname]       = impl
        _bare[name].append(qname)    ← bare list grows; ambiguity surfaced at resolve() time
```

**Key properties:**

- **Qualified collision** (same `plugin.name` registered twice) → `RegistryError` at load time. The `PluginManager` catches this and skips the offending plugin entirely, logging `ERROR`.
- **Bare-name ambiguity** (same local `name` from two *different* plugins) → `_bare[name]` grows to length 2+. This is *not* an error at registration time; it becomes an error only when code calls `resolve("name")` without qualification. This matches FR-005/FR-006: authors may intentionally have same-named resources in different namespaces, relying on qualified references.
- **Plugin-namespace collision** (two plugins with the same `plugin` string) → caught in `PluginManager.load()` before any `register()` calls; the second plugin is rejected.

---

## Design Summary

| Concern | Choice |
|---------|--------|
| Qualified lookup | `_flat["plugin.name"]` — O(1) |
| Plugin-grouped listing | `_ns["plugin"]` — O(resources_in_plugin) |
| Unqualified resolution | `_bare["name"]` reverse index — O(1) + cardinality check |
| Collision detection | At `register()` call, guards `_flat` key |
| Atomic hot-reload | `snapshot()` + single reference swap |
| Generic | `NamespaceRegistry[T]` — one class for tools, agents, prompts |

Instantiate three typed registries in `PluginManager`:

```python
self.tools:    NamespaceRegistry[Callable]         = NamespaceRegistry()
self.agents:   NamespaceRegistry[AgentDefinition]  = NamespaceRegistry()
self.prompts:  NamespaceRegistry[str]              = NamespaceRegistry()
```
