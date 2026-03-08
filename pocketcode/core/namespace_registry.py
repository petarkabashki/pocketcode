from __future__ import annotations

import copy
import logging
import threading
from collections import defaultdict
from typing import TYPE_CHECKING, Dict, Generic, Iterator, List, Optional, TypeVar

from pocketcode.core.reference_syntax import parse_reference

if TYPE_CHECKING:
    # Avoid circular import at runtime; PluginManager imports NamespaceRegistry
    from pocketcode.core.plugin_manager import PluginManager  # noqa: F401

T = TypeVar("T")
logger = logging.getLogger(__name__)


class RegistryError(Exception):
    """
    Raised for any unresolvable or ambiguous registry operation:
    - Qualified name collision on register()
    - Resource not found on resolve()
    - Ambiguous unqualified reference on resolve()
    """


class NamespaceRegistry(Generic[T]):
    """
    Unified namespace registry for plugin resources (tools / agents / prompts).

    Three-tier internal structure:
        _ns   : Dict[str, Dict[str, T]]        # {plugin → {name → impl}}
        _flat : Dict[str, T]                   # {"plugin.name" → impl}
        _bare : Dict[str, List[str]]           # {"name" → ["plugin.name"]}

    Usage::

        reg: NamespaceRegistry[MyType] = NamespaceRegistry()
        reg.register("core", "read_file", ReadFileTool)
        impl = reg.resolve("core.read_file")
        impl = reg.resolve("read_file", context_plugin="core")  # local resolution
    """

    def __init__(self) -> None:
        self._ns: Dict[str, Dict[str, T]] = {}
        self._flat: Dict[str, T] = {}
        self._bare: Dict[str, List[str]] = defaultdict(list)

    def _normalize_ref(self, ref: str) -> str:
        return parse_reference(ref).as_registry_key()

    # ── Writing API ──────────────────────────────────────────────────────────

    def register(self, plugin: str, name: str, impl: T) -> None:
        """Register a resource. Raises RegistryError on qualified-name collision."""
        qname = f"{plugin}.{name}"
        if qname in self._flat:
            raise RegistryError(
                f"Qualified name collision: '{qname}' already registered. "
                f"Cannot register from '{plugin}'."
            )
        self._ns.setdefault(plugin, {})[name] = impl
        self._flat[qname] = impl
        self._bare[name].append(qname)

    def unregister_plugin(self, plugin: str) -> None:
        """Remove all resources owned by *plugin*. Used during hot-reload rebuild."""
        for name in list(self._ns.get(plugin, {})):
            qname = f"{plugin}.{name}"
            self._flat.pop(qname, None)
            owners = self._bare.get(name, [])
            if qname in owners:
                owners.remove(qname)
            if not owners:
                self._bare.pop(name, None)
        self._ns.pop(plugin, None)

    # ── Reading API ──────────────────────────────────────────────────────────

    def resolve(self, ref: str, *, context_plugin: Optional[str] = None) -> T:
        """
        Resolve a qualified (``"plugin.name"`` or ``"plugin::name"``) or unqualified
        (``"name"``) reference.

        Resolution rules:
            - ``"plugin::name"`` is normalised to ``"plugin.name"`` before lookup.
            - ``"plugin.name"`` → direct ``_flat`` lookup; ``RegistryError`` if missing.
            - ``"name"`` with *context_plugin* → tries local plugin first, then global.
            - ``"name"`` (1 owner) → ``WARNING`` log; resolves.
            - ``"name"`` (2+ owners) → ``RegistryError``.
            - ``"name"`` (0 owners) → ``RegistryError``.
        """
        return self._flat[self.qualify(ref, context_plugin=context_plugin)]

    def qualify(self, ref: str, *, context_plugin: Optional[str] = None) -> str:
        """Resolve *ref* to its qualified ``plugin.name`` form."""
        ref = self._normalize_ref(ref)

        if not ref:
            raise RegistryError("Resource not found: ''")

        if "." in ref:
            if ref not in self._flat:
                raise RegistryError(f"Resource not found: '{ref}'")
            return ref

        # FR-004: intra-plugin local resolution first
        if context_plugin:
            local_qname = f"{context_plugin}.{ref}"
            if local_qname in self._flat:
                return local_qname

        owners = self.owners_for(ref)
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
            return qname
        raise RegistryError(
            f"Ambiguous unqualified reference '{ref}': owned by "
            + ", ".join(f"'{q}'" for q in owners)
            + ". Use a qualified name."
        )

    def has_local(self, plugin: str, name: str) -> bool:
        """Return True when *plugin* owns *name*."""
        return f"{plugin}.{name}" in self._flat

    def owners_for(self, name: str) -> List[str]:
        """Return qualified owners for an unqualified bare name."""
        return list(self._bare.get(name, []))

    # ── Enumeration API ──────────────────────────────────────────────────────

    def list_all(self) -> List[str]:
        """All qualified names, sorted. O(n log n)."""
        return sorted(self._flat.keys())

    def list_by_plugin(self, plugin: str) -> Dict[str, T]:
        """All {name: impl} for resources owned by *plugin*."""
        return dict(self._ns.get(plugin, {}))

    def plugins(self) -> List[str]:
        """All registered plugin namespaces, sorted."""
        return sorted(self._ns.keys())

    def items(self) -> Iterator[tuple]:
        """Iterator of (qualified_name, impl) pairs."""
        return iter(self._flat.items())

    def __contains__(self, ref: str) -> bool:
        """True if qualified name exists OR if a bare name has ≥1 owner.

        This supports both:
        - ``"plugin.name" in registry`` → exact qualified lookup
        - ``"plugin::name" in registry`` → normalised to ``"plugin.name"``
        - ``"name" in registry`` → True if registered under any plugin
        """
        ref = self._normalize_ref(ref)
        if "." in ref:
            return ref in self._flat
        return bool(self._bare.get(ref))

    def __len__(self) -> int:
        return len(self._flat)

    # ── Dict-compat API (backward-compat during migration) ───────────────────
    # Callers that previously used self.tools["name"] or self.agents.get("name")
    # will continue working. T030 migrates them to use .resolve() explicitly.

    def get(self, ref: str, default: Optional[T] = None) -> Optional[T]:  # type: ignore[override]
        """Dict-compat: resolve *ref*, return *default* on miss or ambiguity."""
        try:
            return self.resolve(ref)
        except RegistryError:
            return default

    def __getitem__(self, ref: str) -> T:
        """Dict-compat: resolve *ref*. Raises ``KeyError`` on miss (wraps RegistryError)."""
        try:
            return self.resolve(ref)
        except RegistryError as exc:
            raise KeyError(str(exc)) from exc

    def keys(self):  # type: ignore[override]
        """Dict-compat: all qualified names (e.g. 'core.read_file')."""
        return self._flat.keys()

    def values(self):  # type: ignore[override]
        """Dict-compat: all registered implementations."""
        return self._flat.values()

    # ── Snapshot API (FR-011 Hot-Reload) ─────────────────────────────────────

    def snapshot(self) -> NamespaceRegistry[T]:
        """
        Return a deep copy of this registry for atomic hot-reload swap.

        Pattern::

            new_reg = NamespaceRegistry()
            for plugin, name, impl in load_all_plugins():
                new_reg.register(plugin, name, impl)
            holder.swap(new_pm)          # atomic pointer swap
        """
        clone: NamespaceRegistry[T] = NamespaceRegistry()
        clone._ns = copy.deepcopy(self._ns)
        clone._flat = copy.deepcopy(self._flat)
        clone._bare = copy.deepcopy(self._bare)
        return clone


class RegistryHolder:
    """
    Thread-safe wrapper that holds the active PluginManager snapshot.

    Session-start code calls ``get()`` ONCE and stores result in a local variable.
    The entire ``flow.run(shared)`` call uses that frozen reference.

    Critical anti-pattern (NEVER do inside a session loop)::

        # WRONG — re-reads live pointer; breaks mid-session swap safety
        holder.get().tools.resolve("core.read_file")

    Correct session pattern::

        # RIGHT — snapshot captured once at session start
        registry = holder.get()
        flow = registry.agents.resolve("coder::coder").flow_instance
        flow.run(shared)
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._registry: Optional[object] = None  # PluginManager at runtime

    def get(self) -> object:
        """Read active registry. Fast path — no lock needed (GIL-safe)."""
        return self._registry  # type: ignore[return-value]

    def swap(self, new_registry: object) -> None:
        """Atomically replace the active registry snapshot."""
        with self._lock:
            self._registry = new_registry
