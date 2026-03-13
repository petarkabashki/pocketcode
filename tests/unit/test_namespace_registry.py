"""
Unit tests for NamespaceRegistry and RegistryHolder.

Covers all cases specified in T029:
  - register()               : success path
  - RegistryError            : qualified-name collision
  - resolve()                : qualified ref
  - resolve()                : unqualified, 1 owner → WARNING
  - resolve()                : unqualified, 2 owners → RegistryError
  - resolve()                : context_namespace local-first
  - unregister_namespace()      : removes all entries
  - snapshot()               : deep copy isolation
  - list_all()               : sorted qualified names
  - list_by_namespace()         : namespace-scoped dict
  - namespaces()             : sorted namespace list
  - __contains__             : membership check
  - items()                  : (qname, impl) iterator
  - RegistryHolder.get/swap  : thread-safe pointer swap

Prompt-registry coverage (NamespaceRegistry[str]):
  - resolve("namespace.name"): succeeds
  - resolve("missing")       : RegistryError when namespace not loaded
  - resolve("name") 1 owner  : WARNING emitted, resolves
  - resolve("name") 2 owners : RegistryError
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import pytest

from pocketcode.core.namespace_registry import NamespaceRegistry, RegistryError, RegistryHolder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool(tag: str = "tool") -> Any:
    """Return a distinct sentinel callable so registry values are distinguishable."""
    def _tool():
        return tag
    _tool.__name__ = tag
    return _tool


# ---------------------------------------------------------------------------
# register() — success
# ---------------------------------------------------------------------------

class TestRegisterSuccess:
    def test_single_namespace_single_resource(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        t = _make_tool("read_file")
        reg.register("core", "read_file", t)
        assert "core.read_file" in reg

    def test_multiple_namespaces_same_bare_name(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        a = _make_tool("a")
        b = _make_tool("b")
        reg.register("namespace_a", "tool", a)
        reg.register("namespace_b", "tool", b)
        assert "namespace_a.tool" in reg
        assert "namespace_b.tool" in reg

    def test_multiple_resources_one_namespace(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        reg.register("core", "read_file", _make_tool("r"))
        reg.register("core", "write_file", _make_tool("w"))
        assert len(reg) == 2

    def test_len_tracks_registrations(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        assert len(reg) == 0
        reg.register("p", "a", _make_tool())
        assert len(reg) == 1
        reg.register("p", "b", _make_tool())
        assert len(reg) == 2


# ---------------------------------------------------------------------------
# register() — collision (RegistryError)
# ---------------------------------------------------------------------------

class TestRegisterCollision:
    def test_same_namespace_same_name_raises(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        reg.register("core", "read_file", _make_tool())
        with pytest.raises(RegistryError, match="core.read_file"):
            reg.register("core", "read_file", _make_tool())

    def test_different_namespaces_same_qname_impossible(self):
        """Qualified names are 'namespace.name' and different namespaces may share a bare name."""
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        reg.register("a", "tool", _make_tool("a"))
        reg.register("b", "tool", _make_tool("b"))  # must NOT raise


# ---------------------------------------------------------------------------
# resolve() — qualified
# ---------------------------------------------------------------------------

class TestResolveQualified:
    def test_qualified_resolves_correct_impl(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        t = _make_tool("concrete_tool")
        reg.register("core", "read_file", t)
        assert reg.resolve("core.read_file") is t

    def test_qualified_different_namespaces(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        a = _make_tool("a")
        b = _make_tool("b")
        reg.register("namespace_a", "tool", a)
        reg.register("namespace_b", "tool", b)
        assert reg.resolve("namespace_a.tool") is a
        assert reg.resolve("namespace_b.tool") is b

    def test_qualified_missing_raises(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        with pytest.raises(RegistryError, match="core.missing"):
            reg.resolve("core.missing")

    def test_typed_qualified_reference_resolves(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        t = _make_tool("concrete_tool")
        reg.register("core", "read_file", t)
        assert reg.resolve("tool:core.read_file") is t

    def test_hash_qualified_reference_resolves(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        t = _make_tool("shared")
        reg.register("resource_root.pocketcode", "shared", t)
        assert reg.resolve("prompt:resource_root.pocketcode#shared") is t


# ---------------------------------------------------------------------------
# resolve() — unqualified, 1 owner → WARNING
# ---------------------------------------------------------------------------

class TestResolveUnqualifiedOneOwner:
    def test_emits_warning_and_resolves(self, caplog):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        t = _make_tool("sol")
        reg.register("core", "sole_tool", t)

        with caplog.at_level(logging.WARNING, logger="pocketcode.core.namespace_registry"):
            result = reg.resolve("sole_tool")

        assert result is t
        assert any("sole_tool" in record.message for record in caplog.records)
        assert any(record.levelname == "WARNING" for record in caplog.records)

    def test_resolves_correct_value(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        t = _make_tool()
        reg.register("abc", "mytool", t)
        assert reg.resolve("mytool") is t


# ---------------------------------------------------------------------------
# resolve() — unqualified, 2+ owners → RegistryError
# ---------------------------------------------------------------------------

class TestResolveUnqualifiedMultipleOwners:
    def test_two_owners_raises(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        reg.register("a", "tool", _make_tool("a"))
        reg.register("b", "tool", _make_tool("b"))
        with pytest.raises(RegistryError, match="Ambiguous"):
            reg.resolve("tool")

    def test_three_owners_raises(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        for letter in "abc":
            reg.register(letter, "tool", _make_tool(letter))
        with pytest.raises(RegistryError):
            reg.resolve("tool")

    def test_zero_owners_raises(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        with pytest.raises(RegistryError, match="not found"):
            reg.resolve("nonexistent")


# ---------------------------------------------------------------------------
# resolve() — context_namespace local-first
# ---------------------------------------------------------------------------

class TestResolveContextNamespace:
    def test_local_wins_over_global(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        local = _make_tool("local")
        other = _make_tool("other")
        reg.register("my_namespace", "tool", local)
        reg.register("other_namespace", "tool", other)

        result = reg.resolve("tool", context_namespace="my_namespace")
        assert result is local

    def test_local_resolve_no_warning_needed(self, caplog):
        """Local resolution shouldn't go through the unqualified path (no WARNING)."""
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        t = _make_tool()
        reg.register("my_namespace", "tool", t)

        with caplog.at_level(logging.WARNING, logger="pocketcode.core.namespace_registry"):
            result = reg.resolve("tool", context_namespace="my_namespace")

        assert result is t
        # No warning should be emitted for local resolution
        assert not any("tool" in r.message and r.levelname == "WARNING" for r in caplog.records)

    def test_falls_back_to_global_when_not_local(self, caplog):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        t = _make_tool()
        reg.register("other_namespace", "tool", t)

        with caplog.at_level(logging.WARNING, logger="pocketcode.core.namespace_registry"):
            result = reg.resolve("tool", context_namespace="my_namespace")  # local namespace doesn't own "tool"

        assert result is t  # resolved via global 1-owner path

    def test_context_namespace_ambiguous_global_still_raises(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        reg.register("a", "tool", _make_tool("a"))
        reg.register("b", "tool", _make_tool("b"))
        # context_namespace "c" has no local "tool" → falls to global → ambiguous
        with pytest.raises(RegistryError):
            reg.resolve("tool", context_namespace="c")

    def test_typed_unqualified_ref_uses_context_namespace(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        local = _make_tool("local")
        reg.register("my_namespace", "tool", local)

        result = reg.resolve("tool:tool", context_namespace="my_namespace")
        assert result is local


# ---------------------------------------------------------------------------
# unregister_namespace()
# ---------------------------------------------------------------------------

class TestUnregisterNamespace:
    def test_removes_all_resources(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        reg.register("core", "a", _make_tool("a"))
        reg.register("core", "b", _make_tool("b"))
        reg.register("other", "c", _make_tool("c"))

        reg.unregister_namespace("core")

        assert "core.a" not in reg
        assert "core.b" not in reg
        assert "other.c" in reg
        assert len(reg) == 1

    def test_bare_name_cleaned_up(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        reg.register("core", "tool", _make_tool())
        reg.unregister_namespace("core")

        with pytest.raises(RegistryError):
            reg.resolve("tool")

    def test_bare_name_still_resolves_from_other_namespace(self, caplog):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        t = _make_tool()
        reg.register("a", "tool", _make_tool())
        reg.register("b", "tool", t)
        reg.unregister_namespace("a")

        with caplog.at_level(logging.WARNING, logger="pocketcode.core.namespace_registry"):
            result = reg.resolve("tool")
        assert result is t  # now only 1 owner


class TestContains:
    def test_contains_accepts_typed_reference(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        reg.register("core", "read_file", _make_tool())

        assert "tool:core.read_file" in reg
        assert "tool:read_file" in reg

    def test_unregister_nonexistent_is_noop(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        reg.unregister_namespace("nonexistent")  # must not raise

    def test_unregister_clears_namespaces_list(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        reg.register("core", "tool", _make_tool())
        reg.unregister_namespace("core")
        assert "core" not in reg.namespaces()


# ---------------------------------------------------------------------------
# snapshot() — deep copy
# ---------------------------------------------------------------------------

class TestSnapshot:
    def test_snapshot_has_same_contents(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        t = _make_tool()
        reg.register("core", "tool", t)

        snap = reg.snapshot()
        assert snap.resolve("core.tool") is t

    def test_snapshot_is_independent(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        reg.register("core", "tool", _make_tool())

        snap = reg.snapshot()
        reg.unregister_namespace("core")  # modify original

        assert "core.tool" in snap   # snapshot unaffected
        assert "core.tool" not in reg

    def test_snapshot_original_unchanged(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        reg.register("core", "tool", _make_tool())

        snap = reg.snapshot()
        snap.unregister_namespace("core")  # modify snapshot

        assert "core.tool" in reg      # original unaffected


# ---------------------------------------------------------------------------
# list_all(), list_by_namespace(), namespaces(), __contains__(), items()
# ---------------------------------------------------------------------------

class TestEnumerationAPI:
    def _populated(self) -> NamespaceRegistry[Any]:
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        reg.register("b", "z", _make_tool("bz"))
        reg.register("a", "y", _make_tool("ay"))
        reg.register("a", "x", _make_tool("ax"))
        return reg

    def test_list_all_sorted(self):
        reg = self._populated()
        assert reg.list_all() == ["a.x", "a.y", "b.z"]

    def test_list_by_namespace_correct_entries(self):
        reg = self._populated()
        by_a = reg.list_by_namespace("a")
        assert set(by_a.keys()) == {"x", "y"}

    def test_list_by_namespace_empty_for_missing(self):
        reg = self._populated()
        assert reg.list_by_namespace("nonexistent") == {}

    def test_namespaces_sorted(self):
        reg = self._populated()
        assert reg.namespaces() == ["a", "b"]

    def test_contains_qualified(self):
        reg = self._populated()
        assert "a.x" in reg
        assert "a.missing" not in reg

    def test_items_yields_qname_impl_pairs(self):
        reg: NamespaceRegistry[Any] = NamespaceRegistry()
        t = _make_tool("concrete")
        reg.register("core", "tool", t)
        pairs = list(reg.items())
        assert ("core.tool", t) in pairs


# ---------------------------------------------------------------------------
# RegistryHolder — thread-safe pointer swap
# ---------------------------------------------------------------------------

class TestRegistryHolder:
    def test_initial_get_is_none(self):
        holder = RegistryHolder()
        assert holder.get() is None

    def test_swap_updates_get(self):
        holder = RegistryHolder()
        sentinel = object()
        holder.swap(sentinel)
        assert holder.get() is sentinel

    def test_multiple_swaps(self):
        holder = RegistryHolder()
        a = object()
        b = object()
        holder.swap(a)
        assert holder.get() is a
        holder.swap(b)
        assert holder.get() is b

    def test_concurrent_swap_is_safe(self):
        """100 concurrent swaps must not raise and leave a valid reference."""
        holder = RegistryHolder()
        holder.swap(object())
        errors: list[Exception] = []

        def _swap():
            try:
                holder.swap(object())
                _ = holder.get()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_swap) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert holder.get() is not None


# ---------------------------------------------------------------------------
# Prompt NamespaceRegistry[str] — all 4 spec-mandated cases
# ---------------------------------------------------------------------------

class TestPromptRegistry:
    """Uses NamespaceRegistry[str] to confirm generic typing works for prompts."""

    def test_qualified_resolve_succeeds(self):
        prompts: NamespaceRegistry[str] = NamespaceRegistry()
        prompts.register("core", "system", "You are a helpful assistant.")
        assert prompts.resolve("core.system") == "You are a helpful assistant."

    def test_registry_error_when_namespace_not_loaded(self):
        prompts: NamespaceRegistry[str] = NamespaceRegistry()
        with pytest.raises(RegistryError):
            prompts.resolve("missing_namespace.system")

    def test_unqualified_one_owner_emits_warning(self, caplog):
        prompts: NamespaceRegistry[str] = NamespaceRegistry()
        prompts.register("core", "system", "prompt text")

        with caplog.at_level(logging.WARNING, logger="pocketcode.core.namespace_registry"):
            result = prompts.resolve("system")

        assert result == "prompt text"
        assert any("system" in r.message and r.levelname == "WARNING" for r in caplog.records)

    def test_unqualified_two_or_more_owners_raises(self):
        prompts: NamespaceRegistry[str] = NamespaceRegistry()
        prompts.register("core", "system", "prompt A")
        prompts.register("coder", "system", "prompt B")

        with pytest.raises(RegistryError, match="Ambiguous"):
            prompts.resolve("system")
