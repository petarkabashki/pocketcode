# Tasks: Agent Default Profiles

**Feature**: `001-agent-default-profiles` | **Branch**: `001-agent-default-profiles`
**Input**: [plan.md](plan.md) · [spec.md](spec.md) · [data-model.md](data-model.md) · [contracts/agent-profile-yaml.md](contracts/agent-profile-yaml.md)

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Parallelisable — operates on a different file or logically independent section; no dependency on in-progress tasks in the same phase
- **[USn]**: Belongs to User Story *n* from spec.md
- All file paths are workspace-relative

---

## Phase 1: Setup

**Purpose**: Create the new source file scaffold so all subsequent tasks have a landing zone.

- [X] T001 Create `pocketcode/core/agent_profile_manager.py` with module docstring, top-level imports (`logging`, `pathlib.Path`, `typing`, `yaml`), and an empty `AgentProfileManager` class stub

**Checkpoint**: `pocketcode/core/agent_profile_manager.py` exists and is importable with no errors.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Data models, the `AgentProfileManager` API, plugin-manager integration, and engine wiring. **No user-story work can begin until this phase is complete.**

- [X] T002 Add `AgentProfile` dataclass (all 9 fields: `name`, `agent`, `description`, `llm_profile`, `extra_prompts`, `tools`, `tool_confirmation`, `source`, `source_path`) above `AgentDefinition` in `pocketcode/core/runtime_models.py`
- [X] T003 Add `default_agent_profile: AgentProfile | None = None` as the last field of `AgentDefinition` in `pocketcode/core/runtime_models.py` (depends on T002)
- [X] T004 Implement `AgentProfileManager.__init__(workspace_root: Path)` storing `_workspace_profiles_dir = workspace_root / ".pocketcode" / "agent-profiles"` and initialising `_profiles: Dict[str, AgentProfile] = {}` in `pocketcode/core/agent_profile_manager.py`
- [X] T005 Implement `AgentProfileManager.load()` step 1 — store `self._agent_definitions = agent_definitions`; clear `_profiles`; for each `AgentDefinition`, if `default_agent_profile` is set register it (source="plugin"); otherwise synthesise `AgentProfile(source="synthesised", name=qualified_agent_name, agent=qualified_agent_name, llm_profile=defn.llm_profile, tools=defn.tools, extra_prompts=[], tool_confirmation={})` and register it in `pocketcode/core/agent_profile_manager.py`
- [X] T006 Implement `AgentProfileManager.load()` step 2 — scan `_workspace_profiles_dir/*.yaml` alphabetically; for each file parse YAML, construct `AgentProfile(source="workspace", source_path=file_path)`; on name collision with existing entry emit `WARNING` naming both sources and let workspace file win; register in `_profiles` in `pocketcode/core/agent_profile_manager.py`
- [X] T007 [P] Implement `AgentProfileManager.get(name: str) -> AgentProfile | None` and `AgentProfileManager.list() -> List[AgentProfile]` (sorted by name) in `pocketcode/core/agent_profile_manager.py`
- [X] T008 [P] Implement `AgentProfileManager.save(profile: AgentProfile) -> None` — auto-create `_workspace_profiles_dir` if absent; serialise profile to YAML dict; write to `profile.source_path` in `pocketcode/core/agent_profile_manager.py`
- [X] T009 Implement `AgentProfileManager.clone(src_name: str, new_name: str) -> AgentProfile` — look up source, raise `ValueError` if not found; copy all fields, assign `name=new_name`, `source="workspace"`, `source_path=_workspace_profiles_dir / f"{new_name}.yaml"`; raise `ValueError` if target file already exists; call `save()` then `reload()` with current agent definitions in `pocketcode/core/agent_profile_manager.py`
- [X] T010 [P] Update `_register_agent_definition()` in `pocketcode/core/plugin_manager.py` — after all existing fields are read, check `raw_agent_dict.get("default_agent_profile")`; if present and is `dict`, construct `AgentProfile(source="plugin", agent=qualified_name, name=block.get("name") or qualified_name, …all remaining fields per the field rules table in contracts/agent-profile-yaml.md §1…)` and assign to `definition.default_agent_profile`; log `DEBUG`; if absent leave `None`
- [X] T011 Wire `AgentProfileManager` into `pocketcode/core/engine.py` — after `PluginManager.load()` instantiate `self._agent_profile_manager = AgentProfileManager(self._workspace_root)`; call `.load(dict(self._plugins.agents))`; add `self.active_agent_profile: AgentProfile | None = None`; add `set_active_agent_profile(name: str | None)` method that looks up profile by name (raises `ValueError` if not found), sets attribute
- [X] T012 Modify `engine.set_agent(name)` in `pocketcode/core/engine.py` — after setting `self.current_agent`, resolve the agent's default profile name: read `self._plugins.agents[name].default_agent_profile.name` if `default_agent_profile` is set (covers the case where the plugin declared a custom `name`), else fall back to the qualified agent name itself; call `self.set_active_agent_profile(resolved_name)` (depends on T011)
- [X] T013 Add `"active_agent_profile": self.active_agent_profile.name if self.active_agent_profile else None` to `engine.status()` return dict; inject `active_agent_profile` object into `shared_store` at the start of `process_request()` in `pocketcode/core/engine.py` (depends on T011)
- [X] T014 Update `engine.reload()` in `pocketcode/core/engine.py` — call `self._agent_profile_manager.reload(dict(self._plugins.agents))`; re-apply active profile by name if it still exists, else fall back to current agent's default profile (depends on T011, T012, T013)

**Checkpoint**: `AgentProfileManager` fully functional; switching agents auto-loads a profile; `engine.status()` includes `active_agent_profile`.

---

## Phase 3: User Story 1 — Use an Agent Through Its Default Profile (Priority: P1) 🎯 MVP

**Goal**: Every agent activation automatically applies its default agent profile, governing LLM selection, tool availability, extra system prompt content, and tool confirmation policies during each turn.

**Independent Test**: Run `/agent core::react`; status shows `Profile: core::react`; the agent resolves its LLM from the profile; a write tool without an explicit session override follows the profile's confirmation policy.

- [X] T015 [P] [US1] Insert LLM tier 4.5 in `_resolve_llm_profile()` in `pocketcode/core/agent_runtime.py` — between the dynamic-override tier and the agent-definition tier; read `active_agent_profile` from `shared_store`; if `profile and profile.agent == agent_name and profile.llm_profile`: return `profile.llm_profile`
- [X] T016 [P] [US1] Implement profile tool filtering in `pocketcode/core/agent_runtime.py` — after `resolve_tools_for_agent()`, if `active_agent_profile.tools is not None` intersect the resolved tool list with `profile.tools`; excluded tools are removed from the LLM context description and denied at execution
- [X] T017 [P] [US1] Implement `extra_prompts` injection in `pocketcode/core/agent_runtime.py` — during system prompt assembly, if `profile.extra_prompts` is non-empty, resolve each path: (1) relative to `profile.source_path.parent` if set, (2) relative to `workspace_root / ".pocketcode"`; read file contents and append to `shared["_agent_system_prompt"]`; log `WARNING` and skip any path that resolves to a non-existent file
- [X] T018 [US1] Insert confirmation tier 1.5 in `_resolve_confirmation_policy()` in `pocketcode/core/tool_runtime.py` — after the session `[agent][tool]` tier (tier 1); check `profile.tool_confirmation.get("overrides", {}).get(tool_name)` and return if present
- [X] T019 [US1] Insert confirmation tier 4.5 in `_resolve_confirmation_policy()` in `pocketcode/core/tool_runtime.py` — after the session `[agent].default` tier (tier 4); check `profile.tool_confirmation.get("default")` and return if present; update the method docstring to document the full 10-tier order
- [X] T019b [US1] Add an execution-time tool allowlist guard in `pocketcode/core/tool_runtime.py` — **before** resolving the confirmation policy, if `active_agent_profile.tools is not None` and `tool_name` is not in `profile.tools`, immediately return a denied result without prompting the user; update docstring to note that the allowlist check precedes all confirmation tiers (enforces FR-008 and SC-003)

**Checkpoint**: User Story 1 is independently functional — agent activation, LLM override, tool filtering, extra prompts, and confirmation tiers all work via the active agent profile.

---

## Phase 4: User Story 2 — View, Switch, and Clone Profiles from the CLI (Priority: P2)

**Goal**: Full `/agent-profile` command surface in the CLI: list, show, switch, clone, plus `--agent-profile` flag on `/agent`.

**Independent Test**: Create `.pocketcode/agent-profiles/react-lite.yaml`; run `/agent-profile list` to see it; `/agent-profile show react-lite` to inspect; `/agent-profile switch react-lite` to activate — all without restarting, and status bar updates to reflect the active profile name.

- [X] T020 [US2] Add `elif first_token == "agent-profile":` dispatch branch in `pocketcode/cli/command_handler.py` and implement `_handle_agent_profile_command(parts, engine, cli_context)` stub that routes to sub-command handlers by `parts[1]`; handle unknown sub-commands with a helpful error listing valid commands
- [X] T021 [US2] Implement `/agent-profile list` in `_handle_agent_profile_command()` in `pocketcode/cli/command_handler.py` — iterate `engine._agent_profile_manager.list()`; print one line per profile: `name`, target `agent`, `llm_profile` (or `"-"`), `source`
- [X] T022 [P] [US2] Implement `/agent-profile show <name>` in `pocketcode/cli/command_handler.py` — call `engine._agent_profile_manager.get(name)` and pretty-print all fields (description, llm_profile, tools, extra_prompts, tool_confirmation, source, source_path); print clear error if name not found
- [X] T023 [US2] Implement `/agent-profile switch <name>` in `pocketcode/cli/command_handler.py` — call `engine.set_active_agent_profile(name)`; if `profile.agent != engine.current_agent` print a warning naming the agent that will become active and also call `engine.set_agent(profile.agent)`; confirm new active profile in output
- [X] T024 [P] [US2] Implement `/agent-profile clone <src> <new>` in `pocketcode/cli/command_handler.py` — call `engine._agent_profile_manager.clone(src, new)`; print the path of the created file; catch `ValueError` and print a user-friendly error message (not found / already exists)
- [X] T025 [US2] Add `--agent-profile <name>` flag parsing to the existing `/agent` handler in `pocketcode/cli/command_handler.py` — after `engine.set_agent()` sets the default profile, if `--agent-profile` was provided call `engine.set_active_agent_profile(profile_name)` to override; handle flag before and after the agent name
- [X] T026 [P] [US2] Add `AgentProfileCompleter(Completer)` in `pocketcode/cli/completers.py` — on each `get_completions()` call read `engine._agent_profile_manager.list()` and yield `Completion` for each profile name; used for `/agent-profile show`, `/agent-profile switch`, `/agent-profile clone` argument positions
- [X] T027 [US2] Wire `AgentProfileCompleter` into the main input completer setup in `pocketcode/cli/textual_app.py` alongside the existing completers (depends on T026)
- [X] T028 [US2] Update `_update_status()` in `pocketcode/cli/textual_app.py` — read `status.get("active_agent_profile")` (fallback `"-"`); insert `| Profile: {profile}` segment between the Agent segment and the LLM segment in the status bar format string

**Checkpoint**: User Stories 1 AND 2 are both independently functional — agents activate via profiles, and the full `/agent-profile` CLI surface works.

---

## Phase 5: User Story 3 — Define a Custom Workspace Profile (Priority: P3)

**Goal**: A user can create `.pocketcode/agent-profiles/<name>.yaml`, reload, and activate it with correct field parsing, error tolerance, and full tool/confirmation enforcement.

**Independent Test**: Manually create `.pocketcode/agent-profiles/react-safe.yaml`; run `/reload`; run `/agent-profile switch react-safe`; invoke a write tool and confirm the `confirm` policy is prompted; invoke `core::delete_file` and confirm it is denied without a prompt.

- [X] T029 [US3] Implement error handling in workspace YAML parsing inside `AgentProfileManager.load()` in `pocketcode/core/agent_profile_manager.py` — catch `yaml.YAMLError` and `KeyError`; skip files with malformed YAML or missing required fields (`name`, `agent`); emit a specific `WARNING` per skipped file naming the file path and the reason; all remaining profiles continue to load normally
- [X] T030 [P] [US3] Implement `_profile_to_yaml_dict(profile: AgentProfile) -> dict` private helper in `pocketcode/core/agent_profile_manager.py` — maps all `AgentProfile` fields to a YAML-serialisable `dict` matching the workspace file schema from `contracts/agent-profile-yaml.md`; update `save()` to call this helper instead of inlining serialisation logic

**Checkpoint**: All three user stories are independently functional — agents activate via profiles, CLI management commands work, and custom workspace YAML files are loaded, validated, and enforced correctly.

---

## Phase 6: Tests & Polish

**Purpose**: Unit test suites and documentation updates that span all user stories.

- [X] T031 [P] Write `tests/unit/test_agent_profile_manager.py` with 8 test classes: `TestAgentProfileSynthesis`, `TestAgentProfilePluginDeclared`, `TestWorkspaceProfileLoading`, `TestWorkspaceProfileCollisionWarning`, `TestAgentProfileClone`, `TestInvalidProfileYaml` (matching plan.md Step 10); `TestBackwardCompatibilityNoDefaultAgentProfileBlock` (agent with no `default_agent_profile` key in plugin.yaml loads without error and synthesises a default profile — SC-005); `TestLoadPerformance` (load 20 synthetic YAML files from `tmp_path` and assert completion within 1 s — SC-004); use `tmp_path` for all file I/O and `caplog` for log assertions
- [X] T032 [P] Write `tests/unit/test_agent_profile_resolution.py` with 6 test classes matching plan.md Step 10: `TestLlmProfileTierOrder`, `TestToolFilteringWithProfile`, `TestToolFilteringInheritAll`, `TestConfirmationTierProfileOverride`, `TestConfirmationTierProfileDefault`, `TestExtraPromptsResolution` — mock `shared_store` to inject active profiles
- [X] T033 Update `AGENTS.md` to document the agent profile system: concept overview, `AgentProfile` fields, `/agent-profile` CLI commands, YAML schema reference for both plugin.yaml inline block and workspace files, status bar format, and LLM/confirmation tier positions

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — **BLOCKS all user-story phases**
- **Phase 3 (US1)**: Depends on Phase 2 completion — no dependency on US2/US3
- **Phase 4 (US2)**: Depends on Phase 2 completion — no dependency on US1/US3 (though benefits from US1)
- **Phase 5 (US3)**: Depends on Phase 2; depends on T006 (workspace scanning) and T008 (save) from Phase 2 — independently testable from US1/US2
- **Phase 6 (Tests & Polish)**: Depends on all implementation phases being complete

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — no dependency on US2 or US3
- **US2 (P2)**: Can start after Phase 2 — may use US1 output but independently testable; T023 (`switch`) calls `set_active_agent_profile()` which is a Phase 2 deliverable
- **US3 (P3)**: Primarily implemented in Phase 2 (workspace loading) and US1 (enforcement); Phase 5 tasks add robustness and serialisation only

### Within Each Phase

- Phase 2: T002 → T003 → {T004, T010 in parallel} → T005 → {T006, T007, T008 in parallel} → T009 → {T011} → T012 → T013 → T014
- Phase 3: T015, T016, T017 can run in parallel (different functions in agent_runtime.py); T018 → T019 sequential (same function in tool_runtime.py)
- Phase 4: T020 → T021, T022, T023, T024 (sequential sub-commands); T025 parallel with sub-commands; T026 parallel with command_handler tasks; T027 → T028 sequential (same file)
- Phase 6: T031 ‖ T032 ‖ T033 all in parallel

---

## Parallel Opportunities Per User Story

### Phase 2 (Foundational)

```bash
# After T005 (load step 1), launch in parallel:
T006  # workspace YAML scanning
T007  # get() and list() methods
T008  # save() method

# After T002 and T003, launch in parallel with T004:
T010  # plugin_manager.py reads default_agent_profile (different file)
```

### Phase 3 (US1)

```bash
# After Phase 2 is complete, launch together:
T015  # LLM tier 4.5 in agent_runtime.py
T016  # tool filtering in agent_runtime.py
T017  # extra_prompts in agent_runtime.py
# Then sequentially:
T018 → T019  # confirmation tiers 1.5 and 4.5 in tool_runtime.py (same function)
```

### Phase 4 (US2)

```bash
# T020 must come first (stub); then:
T021 → T022 → T023 → T024  # sub-commands (same function, sequential)
T025  # --agent-profile flag (separate handler, parallel with sub-commands)
T026  # AgentProfileCompleter in completers.py (parallel with command_handler tasks)
# After T026:
T027 → T028  # textual_app.py wiring (sequential, same file)
```

### Phase 6 (Tests & Polish)

```bash
# All three in parallel:
T031  # test_agent_profile_manager.py
T032  # test_agent_profile_resolution.py
T033  # AGENTS.md documentation
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002–T014) — **critical, blocks everything**
3. Complete Phase 3: US1 (T015–T019)
4. **STOP and VALIDATE**: Run `/agent core::react` and confirm profile, LLM, tools, confirmation policies all work
5. Run `pytest tests/ -v` to confirm backward compatibility

### Incremental Delivery

1. Phase 1 + Phase 2 → Foundation ready; all agents activate via synthesised profiles
2. Phase 3 (US1) → Profile LLM/tool/prompt/confirmation enforcement active — **MVP deliverable**
3. Phase 4 (US2) → Full CLI management surface — list, show, switch, clone
4. Phase 5 (US3) → Workspace profile files with error handling and serialisation polish
5. Phase 6 → Tests + documentation

### Parallel Team Strategy

After Phase 2 completes:

- Developer A: Phase 3 (US1) — `agent_runtime.py`, `tool_runtime.py`
- Developer B-1: Phase 4 T020–T025 (US2 commands) — `command_handler.py`
- Developer B-2: Phase 4 T026–T028 (US2 completers + status bar) — `completers.py`, `textual_app.py`
- Developer C: Phase 5 (US3 robustness) — `agent_profile_manager.py`

---

## Summary

| Phase | Tasks | Files Modified | Parallelisable |
|-------|-------|---------------|----------------|
| 1 — Setup | T001 | `agent_profile_manager.py` (new) | — |
| 2 — Foundational | T002–T014 (13) | `runtime_models.py`, `agent_profile_manager.py`, `plugin_manager.py`, `engine.py` | T006‖T007‖T008; T010‖T004 |
| 3 — US1 | T015–T019b (6) | `agent_runtime.py`, `tool_runtime.py` | T015‖T016‖T017 |
| 4 — US2 | T020–T028 (9) | `command_handler.py`, `completers.py`, `textual_app.py` | T026 ‖ T020–T025 |
| 5 — US3 | T029–T030 (2) | `agent_profile_manager.py` | T030 ‖ Phase 4 |
| 6 — Tests & Polish | T031–T033 (3) | `test_agent_profile_manager.py` (new), `test_agent_profile_resolution.py` (new), `AGENTS.md` | T031‖T032‖T033 |
| **Total** | **34** | **9 source files · 2 new test files · 1 doc** | |

---

## Verification

```bash
# After Phase 2:
python -c "from pocketcode.core.agent_profile_manager import AgentProfileManager; print('OK')"

# After Phase 3 (US1):
source .venv/bin/activate && pocketcode
# /agent core::react   → status shows "Profile: core::react"

# After Phase 4 (US2):
# /agent-profile list
# /agent-profile show core::react
# /agent-profile clone core::react react-safe
# /agent-profile switch react-safe

# Full test suite (after Phase 6):
pytest tests/unit/test_agent_profile_manager.py -v
pytest tests/unit/test_agent_profile_resolution.py -v
pytest tests/ -v   # all existing tests must still pass (backward compat)

# Quickstart validation:
# Follow quickstart.md steps 1–8 end-to-end
```
