# Research: Unified Plugin Namespace Architecture

**Phase**: 0 — Pre-implementation research  
**Feature**: 003-unified-plugin-namespace  
**Date**: 2026-03-05  
**Status**: Complete — all NEEDS CLARIFICATION resolved

---

## Topic 1 — Namespace Registry Design

### Decision
Three-tier internal store: nested `{plugin → {name → impl}}` + flat `{"plugin.name" → impl}` + bare-name reverse index `{"name" → ["plugin.name", ...]}`.

### Rationale
Neither nested-only nor flat-only covers all three access patterns without O(n) scans. The `_bare` reverse index is the key third structure — it makes unqualified lookup O(1) and gives immediate cardinality for the warn-vs-error decision (FR-006) without scanning any plugin dict at resolve time.

| Store | Type | Purpose |
|---|---|---|
| `_ns` | `Dict[str, Dict[str, T]]` | Source of truth; plugin-grouped enumeration |
| `_flat` | `Dict[str, T]` | `"plugin.name"` → O(1) qualified lookup |
| `_bare` | `Dict[str, list[str]]` | `"name"` → qualifying keys list; ambiguity detection |

### Unqualified backward-compat resolution (FR-006)
```
ref has "."  →  _flat lookup (hard error if missing)
ref has none →
    context_plugin local check first (FR-004)
    _bare[ref] missing           → KeyError
    len(_bare[ref]) == 1         → WARNING, resolve
    len(_bare[ref]) >  1         → ERROR, raise AmbiguousReference
```

### Plugin namespace collision (FR-005/FR-010)
Caught in `PluginManager.load()` before any `register()` calls. Two plugins with the same declared name → `ERROR`, second plugin skipped.

### Qualified name collision
Caught inside `register()` when `qname` already exists in `_flat` → `RegistryError` raised, caller logs `ERROR` and skips the plugin.

### Alternatives considered
- Nested-only: rejected — O(plugins) for qualified lookup
- Flat-only: rejected — O(all_keys) for plugin-grouped listing; no atomic scope clear

---

## Topic 2 — Snapshot-Isolation Hot-Reload (FR-011)

### Decision
CPython reference-counting + single `threading.Lock` protecting the active registry pointer. In-flight sessions capture a local reference via `holder.get()` at session start; they drain naturally against the pre-reload snapshot without any manual bookkeeping.

### Rationale
Python's GC keeps the old registry object alive as long as any local variable references it. Session-start code stores `registry = holder.get()` once; the entire `Flow.run(shared)` call uses that frozen reference. After the atomic swap, new sessions get the new snapshot; old sessions complete uninterrupted.

### Rebuild sequence
```
(a) BUILD    new_pm = PluginManager(config, root)
             new_pm.load()      # full reload — outside lock; slow I/O

(b) SWAP     with _registry_lock:
                 _active_registry = new_pm   # single GIL-atomic store

(c) DISCARD  old_pm = None      # refcount → 0 when last session completes
```

### Watchdog double-fire
Editors emit 2–3 `inotify` events per save. Handled by the existing `_debounced_enqueue` (500 ms timer keyed per plugin root) plus a `_rebuild_in_progress` threading Event flag that coalesces concurrent rebuild requests. No watchdog config changes needed.

### Anti-pattern to avoid
`holder.get().agents[name]` inside the session loop re-reads the live pointer after a swap. Correct pattern: `registry = holder.get()` **once** at session start.

### Alternatives considered
- Freeze/drain (wait for all sessions before swapping): rejected — blocks new sessions during rebuild; degrades UX
- No protection: rejected — spec (FR-011) explicitly requires in-flight session safety

---

## Topic 3 — Manifest Migration (schema_version + agent.yaml shim)

### Decision
- Unified `plugin.yaml` with `schema_version: 1` (int) as required first key. Hard error (`ManifestSchemaError`) if absent or unrecognised → plugin skipped.
- `agent.yaml` detected by filename → `WARNING` log with step-by-step migration instructions → compatibility shim loads tools and prompts; `agents:` left empty (second `WARNING` emitted); returns `schema_version=0` sentinel.
- Legacy sections (`components:`, `workflows:`, `node_definitions:`, `flows:`, `modes:`) in any `plugin.yaml` → `WARNING` per section, section ignored.

### Rationale
Strict validation at load time gives plugin authors immediate, actionable feedback. The `schema_version=0` sentinel on shim-loaded manifests lets callers branch without re-inspecting the filename. Single `ManifestSchemaError` type stays catchable by the existing broad `except Exception` in `PluginManager` while remaining targetable in tests.

### Agent factory pattern (FR-012)
Every agent entry in `agents:` MUST declare:
```yaml
agents:
  coder:
    module: agents/coder_agent.py   # relative to plugin root
    entry_fn: create_flow            # zero-arg factory returning PocketFlow Flow
```
`load_manifest()` validates the presence of both fields and raises `ManifestSchemaError` if either is absent from an agent block.

### Canonical `plugin.yaml` v1 structure
```yaml
schema_version: 1
name: coder
description: Expert developer focused on implementation.

tools:
  write_to_file: tools/filesystem.py:WriteToFileTool
  git_diff: tools/git.py:GitDiffTool

agents:
  coder:
    description: Code implementation specialist.
    module: agents/coder_agent.py
    entry_fn: create_flow
    llm_profile: gemini_default
    tools:
      - write_to_file       # local; resolved within this plugin first
      - core.read_file      # qualified cross-plugin reference
    prompts:
      system: prompts/system.md

prompts:
  system: prompts/system.md

llm_profiles:
  gemini_default:
    provider: gemini
    model: gemini-2.0-flash
```

### Alternatives considered
- Silent migration (load agent.yaml without warning): rejected — spec requires explicit WARNING (FR-006/FR-005 observability)
- Integer vs string version: integer chosen — simpler comparison, no semver overhead at this stage

---

## Topic 4 — Core Tool Physical Relocation

### Decision
**Option A**: Move implementations into `pocketcode/plugins/core/tools/`. Replace `pocketcode/tools/*.py` with thin re-export wrappers.

### Rationale
| Criterion | Option A (chosen) | Option B (wrappers in core, impl in tools/) | Option C (symlinks) |
|---|---|---|---|
| `pocketcode/tools/` importable? | YES — wrappers forward all symbols | YES | YES |
| Core plugin self-contained? | **YES** | NO — depends on external package | PARTIAL |
| Circular imports? | NO | NO | NO |
| Cross-platform? | YES | YES | NO — Windows CI breaks |

Option B violates SC-006 (core plugin not self-contained). Option C fails on Windows CI runners.

### Backward-compat wrapper pattern
```python
# pocketcode/tools/filesystem.py (after migration)
"""Backward-compatibility re-export."""
from pocketcode.plugins.core.tools.filesystem import (  # noqa: F401
    ReadFileTool, WriteToFileTool, ListFilesTool,
    CreateDirectoryTool, GlobFilesTool,
)
```

### Critical detail: `execute_shell_command`
`system.py` exports a bare function `execute_shell_command` (not a Tool class) consumed by:
- Historical note: `pocketcode/tools/git.py` once existed as an intra-package wrapper; the current codebase exposes git tools directly from the `pocketcode.tools` package.
- `pocketcode/plugins/coder/tools/git.py` (cross-plugin import)

The wrapper in `pocketcode/tools/system.py` MUST re-export `execute_shell_command` alongside `ExecuteCommandTool`. This note is historical: git tooling no longer lives in `pocketcode/plugins/core/tools/git.py`; the current canonical implementation is `.pocketcode/plugins/workspace_git/tools/git.py`.

### `plugin.yaml` tool reference format after migration
```yaml
tools:
  read_file: tools/filesystem.py:ReadFileTool   # file-relative to plugin root
```

### Migration checklist
1. Create `pocketcode/plugins/core/tools/__init__.py` (empty)
2. Copy each tool file into `pocketcode/plugins/core/tools/`; update intra-plugin imports to use `pocketcode.plugins.core.tools.*`
3. Replace `pocketcode/tools/*.py` with re-export wrappers
4. Update `pocketcode/plugins/core/plugin.yaml` tool entries to use `tools/X.py:ClassName` references
5. Add `schema_version: 1` to `plugin.yaml`; migrate `components:` blocks to `agents:` entries
6. Run `pytest tests/integration/` — must pass without test modifications (SC-001)
7. Verify `from pocketcode.tools.system import execute_shell_command` resolves in a fresh interpreter

---

## Resolution Summary

| NEEDS CLARIFICATION | Resolution |
|---|---|
| Namespace Registry internal structure | Three-tier store (`_ns` + `_flat` + `_bare`) |
| Hot-reload session protection mechanism | CPython refcount + `threading.Lock` atomic swap (B) |
| Manifest schema versioning | `schema_version: 1` required int field, `ManifestSchemaError` on failure |
| Agent graph declaration format | `module:` + `entry_fn:` YAML keys pointing to Python factory (A) |
| Core tool relocation strategy | Option A — move to `core/tools/`; `pocketcode/tools/` becomes wrappers |
| Plugin trust model | Trusted-only; no sandboxing in scope |
| Observability format | Python `logging` at `WARNING`/`ERROR` level to stderr |


**Phase**: 0 — Pre-implementation research  
**Feature**: 003-unified-plugin-namespace  
**Date**: 2026-03-05

---

## Codebase Inventory (relevant consumers of `pocketcode.tools.*`)

| Consumer | Import |
|---|---|
| `pocketcode/core/tool_runtime.py` | `from pocketcode.tools.user_input import ConfirmUserInputTool` |
| Historical `pocketcode/tools/git.py` | `from pocketcode.tools.system import execute_shell_command` (intra-package) |
| `pocketcode/plugins/coder/tools/git.py` | `from pocketcode.tools.system import execute_shell_command` |
| `pocketcode/plugins/core/plugin.yaml` | dotted paths: `pocketcode.tools.filesystem.ReadFileTool`, etc. |
| `tests/integration/` | **No direct imports from `pocketcode.tools.*`** — only `pocketcode.core.*` |

`execute_shell_command` is a bare function (not a tool class) exported from `system.py` and consumed by two separate `git.py` files. It must survive as an importable symbol after the move.

---

## Option Evaluation

| Criterion | A — Move to core plugin; `pocketcode/tools/` becomes re-export wrappers | B — Keep in `pocketcode/tools/`; create thin wrappers in `core/tools/` | C — Keep in `pocketcode/tools/`; symlink into `core/tools/` |
|---|---|---|---|
| `pocketcode/tools/` importable? | **YES** — wrappers forward all public symbols | **YES** — original files unchanged | **YES** — symlinks resolve normally |
| Core plugin self-contained? | **YES** — implementations and registrations colocated | **NO** — plugin depends on external `pocketcode.tools.*` package; violates SC-006 | **PARTIAL** — files physically shared via OS links; directory appears self-contained but is not |
| Circular imports? | **NO** — wrappers only import from the plugin; no reverse dependency | **NO** | **NO** |
| Cross-platform? | **YES** | **YES** | **NO** — Windows requires elevated privileges for symlinks; breaks `pip install -e .` and git checkout on most CI runners |

---

## Recommendation: Option A

**Move implementations into `pocketcode/plugins/core/tools/`. Replace `pocketcode/tools/*.py` with thin re-export wrappers.**

**Rationale:**

Option B keeps the core plugin dependent on an external package (`pocketcode.tools`), meaning it cannot operate alone — this directly violates SC-006 ("core plugin is fully self-contained"). Option C is eliminated by the cross-platform constraint; the spec targets Linux/macOS dev workstations but CI runners and Windows contributors would break.

Option A is the only choice where the core plugin's directory contains both the canonical implementation and the registration entry, satisfying SC-006 and FR-002. The `pocketcode/tools/` wrappers are one-liners using `from … import *` or explicit re-exports, so all existing callers (`tool_runtime.py`, `coder/tools/git.py`, and any future code referencing the old path) continue to work with zero changes.

**One implementation detail required attention at the time**: the intra-package import inside `pocketcode/tools/git.py` (`from pocketcode.tools.system import execute_shell_command`) became a no-op concern once `git.py` was turned into a wrapper. This is now superseded by the current architecture, where the canonical implementation lives in `.pocketcode/plugins/workspace_git/tools/git.py` and the `pocketcode.tools` package exports those classes directly.

---

## Exact File Content Pattern (Option A)

### Canonical implementation (new location)

```python
# Historical example: pocketcode/plugins/core/tools/git.py  (superseded by .pocketcode/plugins/workspace_git/tools/git.py)
try:
    from pocketcode.plugins.core.tools.system import execute_shell_command
except ImportError:
    from pocketcode.tools.system import execute_shell_command  # fallback during transition
```

### Backward-compat re-export wrapper

```python
# pocketcode/tools/filesystem.py  (after migration — full file content)
"""Backward-compatibility re-export. Canonical implementation in pocketcode/plugins/core/tools/filesystem.py."""
from pocketcode.plugins.core.tools.filesystem import (  # noqa: F401
    ReadFileTool,
    WriteToFileTool,
    ListFilesTool,
    CreateDirectoryTool,
    GlobFilesTool,
)

__all__ = [
    "ReadFileTool",
    "WriteToFileTool",
    "ListFilesTool",
    "CreateDirectoryTool",
    "GlobFilesTool",
]
```

```python
# pocketcode/tools/system.py  (after migration — must also re-export execute_shell_command)
"""Backward-compatibility re-export. Canonical implementation in pocketcode/plugins/core/tools/system.py."""
from pocketcode.plugins.core.tools.system import (  # noqa: F401
    ExecuteCommandTool,
    execute_shell_command,  # consumed by coder/tools/git.py and tool_runtime transitively
)

__all__ = ["ExecuteCommandTool", "execute_shell_command"]
```

The same wrapper pattern applies to `git.py`, `search.py`, and `user_input.py` — export every public symbol the module currently exposes so that `from pocketcode.tools.X import Y` continues to resolve for any caller.

---

## Migration Checklist (for tasks.md)

1. Copy (not move) each tool file into `pocketcode/plugins/core/tools/` and update intra-plugin imports to use the new package path.
2. Replace `pocketcode/tools/*.py` with re-export wrappers (one per file).
3. Update `plugin.yaml` tool registrations to use file-relative references (e.g., `tools/filesystem.py:ReadFileTool`) as the target manifest format.
4. Verify `pocketcode/plugins/core/tools/__init__.py` exists (can be empty) so the directory is a valid package.
5. Run `pytest tests/integration/` — must pass without modifying test files (SC-001).
6. Confirm `from pocketcode.tools.system import execute_shell_command` still resolves in a fresh interpreter (backward compat for `coder/tools/git.py`).
