# Contract: NamespaceRegistry Python API

**Date**: 2026-03-05 | **Feature**: 003-unified-plugin-namespace | **Status**: Approved

---

## Purpose

`NamespaceRegistry[T]` is the runtime structure that replaces the current flat `dict` fields in `PluginManager` (`self.tools`, `self.agents`). It provides O(1) qualified lookup, O(1) unqualified ambiguity detection, plugin-grouped enumeration, and atomic snapshot-swap for hot-reload.

Three typed registry instances are created per `PluginManager`:

```python
self.tools:    NamespaceRegistry[Callable]         = NamespaceRegistry()
self.agents:   NamespaceRegistry[AgentDefinition]  = NamespaceRegistry()
self.prompts:  NamespaceRegistry[str]              = NamespaceRegistry()
self.llm_profiles: Dict[str, Dict[str, Any]]       = {}  # unqualified; flat dict retained
```

---

## Exceptions

```python
class RegistryError(Exception):
    """
    Raised for any unresolvable or ambiguous registry operation:
    - Qualified name collision on register()
    - Resource not found on resolve()
    - Ambiguous unqualified reference on resolve()
    """
```

---

## Internal Structure

```
_ns   : Dict[str, Dict[str, T]]        # {plugin → {name → impl}}   — source of truth
_flat : Dict[str, T]                   # {"plugin.name" → impl}      — O(1) qualified lookup
_bare : Dict[str, List[str]]           # {"name" → ["plugin.name"]}  — O(1) bare + ambiguity
```

**Invariant**: `_flat` and `_bare` are always consistent with `_ns`. Never modify them directly — always go through `register()` / `unregister_plugin()`.

---

## Full Class Signature

```python
from __future__ import annotations

import copy
import logging
from collections import defaultdict
from typing import Dict, Generic, Iterator, List, Optional, TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


class NamespaceRegistry(Generic[T]):
    """
    Unified namespace registry for plugin resources (tools / agents / prompts).

    Usage:
        reg: NamespaceRegistry[MyType] = NamespaceRegistry()
        reg.register("core", "read_file", ReadFileTool)
        impl = reg.resolve("core.read_file")
        impl = reg.resolve("read_file", context_plugin="core")  # local resolution
    """

    def __init__(self) -> None:
        self._ns: Dict[str, Dict[str, T]] = {}
        self._flat: Dict[str, T] = {}
        self._bare: Dict[str, List[str]] = defaultdict(list)
```

---

## Writing API

### `register(plugin, name, impl) → None`

Register a resource. Raises `RegistryError` on qualified-name collision.

```python
def register(self, plugin: str, name: str, impl: T) -> None:
    qname = f"{plugin}.{name}"
    if qname in self._flat:
        raise RegistryError(
            f"Qualified name collision: '{qname}' already registered. "
            f"Cannot register from '{plugin}'."
        )
    self._ns.setdefault(plugin, {})[name] = impl
    self._flat[qname] = impl
    self._bare[name].append(qname)
```

**Caller contract**: `PluginManager` must catch `RegistryError`, log at `ERROR` level, and skip the offending plugin entirely.

### `unregister_plugin(plugin) → None`

Remove all resources owned by `plugin`. Used internally during hot-reload rebuild (clear old plugin before re-registering from new snapshot).

```python
def unregister_plugin(self, plugin: str) -> None:
    for name in list(self._ns.get(plugin, {})):
        qname = f"{plugin}.{name}"
        self._flat.pop(qname, None)
        owners = self._bare.get(name, [])
        if qname in owners:
            owners.remove(qname)
        if not owners:
            self._bare.pop(name, None)
    self._ns.pop(plugin, None)
```

---

## Reading API

### `resolve(ref, *, context_plugin=None) → T`

Resolve a qualified (`"plugin.name"`) or unqualified (`"name"`) reference.

```python
def resolve(self, ref: str, *, context_plugin: Optional[str] = None) -> T:
    if "." in ref:
        impl = self._flat.get(ref)
        if impl is None:
            raise RegistryError(f"Resource not found: '{ref}'")
        return impl

    # FR-004: intra-plugin local resolution first
    if context_plugin:
        local = self._ns.get(context_plugin, {}).get(ref)
        if local is not None:
            return local

    owners = self._bare.get(ref, [])
    if not owners:
        raise RegistryError(f"Resource not found: '{ref}'")
    if len(owners) == 1:
        qname = owners[0]
        logger.warning(
            "Unqualified reference '%s' resolved to '%s'. "
            "Use the qualified form to silence this warning.",
            ref, qname,
        )
        return self._flat[qname]
    raise RegistryError(
        f"Ambiguous unqualified reference '{ref}': owned by "
        + ", ".join(f"'{q}'" for q in owners)
        + ". Use a qualified name."
    )
```

| `ref` form | Behaviour |
|---|---|
| `"plugin.name"` | Direct `_flat` lookup. `RegistryError` if missing. |
| `"name"` (with `context_plugin`) | Checks owning plugin first; falls through to global index. |
| `"name"` (1 owner) | `WARNING` log; resolves. |
| `"name"` (2+ owners) | `ERROR` log + `RegistryError`. |
| `"name"` (0 owners) | `RegistryError`. |

---

## Enumeration API

```python
def list_all(self) -> List[str]:
    """All qualified names, sorted. O(n log n)."""
    return sorted(self._flat.keys())

def list_by_plugin(self, plugin: str) -> Dict[str, T]:
    """All {name: impl} for resources owned by plugin. O(k) where k = resources."""
    return dict(self._ns.get(plugin, {}))

def plugins(self) -> List[str]:
    """All registered plugin namespaces, sorted."""
    return sorted(self._ns.keys())

def items(self) -> Iterator[tuple[str, T]]:
    """Iterator of (qualified_name, impl) pairs."""
    return iter(self._flat.items())

def __contains__(self, ref: str) -> bool:
    """True if qualified name exists. Does not trigger disambiguation."""
    return ref in self._flat

def __len__(self) -> int:
    return len(self._flat)
```

---

## Snapshot API (FR-011 Hot-Reload)

```python
def snapshot(self) -> NamespaceRegistry[T]:
    """
    Return a deep copy of this registry for atomic hot-reload swap.

    Pattern:
        new_reg = NamespaceRegistry()
        for plugin, name, impl in load_all_plugins():
            new_reg.register(plugin, name, impl)
        holder.swap(new_reg)          # atomic pointer swap
        # in-flight sessions hold the old snapshot; new sessions get new_reg
    """
    clone: NamespaceRegistry[T] = NamespaceRegistry()
    clone._ns   = copy.deepcopy(self._ns)
    clone._flat = copy.deepcopy(self._flat)
    clone._bare = copy.deepcopy(self._bare)
    return clone
```

---

## RegistryHolder (FR-011 Swap Coordinator)

```python
import threading

class RegistryHolder:
    """
    Thread-safe wrapper that holds the active PluginManager snapshot.

    Session-start code calls get() ONCE and stores result in a local variable.
    The entire flow.run(shared) call uses that frozen reference.
    """
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._registry: Optional[PluginManager] = None

    def get(self) -> PluginManager:
        """Read active registry. Fast path — no lock needed on read (GIL-safe)."""
        return self._registry  # type: ignore[return-value]

    def swap(self, new_registry: PluginManager) -> None:
        """Atomically replace the active registry snapshot."""
        with self._lock:
            self._registry = new_registry
```

**Critical anti-pattern** (NEVER do this inside a session loop):
```python
# WRONG — re-reads live pointer; breaks mid-session swap safety
holder.get().tools.resolve("core.read_file")
```

**Correct session pattern**:
```python
# RIGHT — snapshot captured once at session start
registry = holder.get()
flow = registry.agents.resolve("core.coder").flow_instance
flow.run(shared)  # entire session uses frozen `registry`
```

---

## Collision Behaviour Summary

| Scenario | Detection point | Log level | Plugin outcome |
|---|---|---|---|
| Two plugins declare same `plugin` name | `PluginManager.load()` before `register()` | `ERROR` | Second plugin skipped entirely |
| `register()` called with existing `qname` | `register()` | `ERROR` (caller logs) | Offending plugin skipped; earlier plugin retained |
| Same bare `name` from 2+ different plugins | `_bare` grows; caught at `resolve()` time | `ERROR` | Resolution fails; caller receives `RegistryError` |
| Unqualified reference, 1 owner | `resolve()` | `WARNING` | Resolved; deprecation warning emitted |
