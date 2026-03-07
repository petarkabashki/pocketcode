# Research: CLI Consistency Cleanup

## Decision 1: Split universal command help from interface-specific discovery

- Decision: Keep a single universal command/help surface for commands that work across CLI entry points, and move retained interface-only commands into interface-local discovery surfaces.
- Rationale: The main defect behind the feature is that universal help/suggestions currently advertise commands that only work in Textual UI. A shared universal surface plus interface-local discovery removes ambiguity without deleting useful interface-only behavior.
- Alternatives considered:
  - Keep one mixed help surface with labels. Rejected because it preserves ambiguity in completion and primary help output.
  - Remove all interface-only commands. Rejected because some commands remain useful within Textual UI and do not need to be deleted if their scope is made explicit.

## Decision 2: Use agent-centered public terminology and remove workflow wording

- Decision: Standardize user-facing CLI terminology around `agent`, `agent profile`, `mode`, and other currently used concepts, and remove `workflow` from public CLI output and routing terminology.
- Rationale: The spec explicitly chose `agent` as the primary public term and rejected ongoing workflow wording because it no longer reflects the supported model. Consistent terminology across startup, status, help, and docs is required to reduce user confusion.
- Alternatives considered:
  - Keep both flow/workflow terms and explain the difference. Rejected because the current issue is terminology drift, not lack of documentation.
  - Center everything on `flow` rather than `agent`. Rejected by clarification decision in favor of agent-centered language.

## Decision 3: Remove deprecated routing and terminology adapters in the same feature

- Decision: Remove internal compatibility helpers and routing adapters that only exist to translate old CLI terminology or deprecated command paths.
- Rationale: The feature is explicitly scoped to remove obsolete compatibility artifacts, not merely hide them. Leaving old adapters behind would preserve maintenance cost and risk future drift even if user-facing help is cleaned up.
- Alternatives considered:
  - Keep internal adapters and only change user-facing surfaces. Rejected because the clarification chose full removal in the same feature.
  - Remove only provably unused adapters. Rejected because the feature intentionally includes old terminology/routing cleanup, even when currently reachable internally.

## Decision 4: Treat CLI help and command discovery as a tested contract

- Decision: Add or update tests so command help, command availability, alias routing, and terminology changes are verified alongside existing handler behavior.
- Rationale: The existing CLI tests already cover portions of command handling, but they do not fully protect help text, startup wording, or the boundary between universal and interface-specific command discovery. This feature changes user-facing contract surfaces and therefore needs direct test coverage.
- Alternatives considered:
  - Rely on existing unit tests only. Rejected because they do not cover the reviewed drift areas.
  - Test only implementation behavior and not help/discovery output. Rejected because the feature’s core value is contract consistency, not only routing logic.

## Decision 5: Keep the cleanup scoped to the existing package layout

- Decision: Implement the cleanup in the existing `pocketcode/main.py`, `pocketcode/cli/*.py`, `pocketcode/core/engine.py`, and adjacent docs/tests without introducing a new command subsystem.
- Rationale: The constitution prefers minimalist orchestration. The repo already has a central command handler and Textual interception point; cleanup should simplify these paths rather than replace them with a new architecture.
- Alternatives considered:
  - Introduce a new command registry package or separate abstraction layer first. Rejected because it expands scope beyond the spec and risks turning cleanup into a rewrite.
  - Touch only docs/tests and leave code structure intact. Rejected because the spec explicitly requires compatibility-helper removal and public-contract alignment.