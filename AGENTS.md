Always update the documentation to be consistent with the codebase and reflect all changes.

`docs/` is the canonical documentation set and must be kept up to date with the current implementation.

Keep comprehensive, up-to-date canonical documentation in `docs/` covering the architecture, design, implementation details, and runtime behavior of the system.

Keep code and documentation files limited to around 500 lines where practical; when a file grows beyond that, split it functionally into appropriately named files and folders.

- Treat `docs/` plus the codebase as the single source of truth for current behavior.
- Treat `specs/` only as historical incremental design history that may be out of date.
- If code changes, update the relevant files in `docs/` in the same change.
- If a spec conflicts with the implementation, do not "fix" the docs to match the spec; document the implementation and, if useful, note that the spec is historical.
- Prefer documenting current load order, precedence rules, schemas, commands, and runtime behavior over planned or aspirational behavior.
- Add mermaid or dot diagrams in documentation, examples, and markdown-based agents to illustrate behaviour, architecture and structure.
- Add descriptive use-case scenarios to illustrate the different stackvm patterns in docs and examples

Always for python load the local python environment by running `source` on .venv/bin/activate

---

Implementation details belong in `docs/`, not in this instruction file.

Use these canonical docs:

- `docs/agent_system.md` for agent profile fields, precedence, schemas, commands, and key files
- `docs/architecture.md` for runtime loading and resolution order
- `docs/configuration.md` for workspace paths and config structure
- `docs/cli.md` for the command and Textual UI surface
- `docs/pocketflow_agents.md` for the flow versus profile model

--- 
NEVER EVER keep api keys outside the .env file, but use environment variables and substitution or templating instead