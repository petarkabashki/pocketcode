from __future__ import annotations

from pathlib import Path

from pocketcode.core.markdown_assets import (
    compile_markdown_agent_definition,
    compile_markdown_flow_definition,
    compile_markdown_tool_definition,
    load_markdown_asset_document,
    serialize_markdown_agent_definition,
)


def test_markdown_asset_document_expands_includes_and_parses_blocks(tmp_path: Path):
    root = tmp_path / "assets"
    root.mkdir(parents=True, exist_ok=True)
    (root / "shared.md").write_text("Shared section.\n", encoding="utf-8")
    (root / "flow.md").write_text(
        """---
name: review
llm_profile: fast
---
Intro.

{{ include:shared.md }}

```yaml spec
tools:
  - core.read_file
```

```mermaid graph
graph TD
  A --> B
```
""",
        encoding="utf-8",
    )

    document = load_markdown_asset_document(root / "flow.md")

    assert document.front_matter["name"] == "review"
    assert "Intro." in document.body
    assert "Shared section." in document.body
    assert len(document.blocks) == 2
    assert str(root / "shared.md") in document.sources


def test_compile_markdown_flow_definition_ignores_graph_blocks_as_execution_metadata(tmp_path: Path):
    flow_file = tmp_path / "review.md"
    flow_file.write_text(
        """---
module: flows/review.py
entry_fn: create_flow
---
Review prompt.

```mermaid graph
graph TD
  start --> finish
```
""",
        encoding="utf-8",
    )

    document = load_markdown_asset_document(flow_file)
    compiled = compile_markdown_flow_definition(document, default_name="review")

    assert compiled["module"] == "flows/review.py"
    assert compiled["entry_fn"] == "create_flow"
    assert compiled["prompt"] == "Review prompt."
    assert "metadata" not in compiled or "markdown_graphs" not in compiled.get("metadata", {})


def test_compile_markdown_tool_definition_reads_schema_block(tmp_path: Path):
    tool_file = tmp_path / "grep.md"
    tool_file.write_text(
        """---
handler: grep.py:run_grep
description: Search for text
execution_mode: inline
---

```yaml schema
type: object
properties:
  query:
    type: string
required:
  - query
```
""",
        encoding="utf-8",
    )

    document = load_markdown_asset_document(tool_file)
    compiled = compile_markdown_tool_definition(document, default_name="grep")

    assert compiled.name == "grep"
    assert compiled.handler == "grep.py:run_grep"
    assert compiled.schema["properties"]["query"]["type"] == "string"


def test_compile_markdown_flow_definition_collects_vm_source_blocks(tmp_path: Path):
    flow_file = tmp_path / "vm-flow.md"
    flow_file.write_text(
        """---
name: vm-flow
description: StackVM flow
---
Prompt text.

```vm
"hello from vm" answer
```
""",
        encoding="utf-8",
    )

    document = load_markdown_asset_document(flow_file)
    compiled = compile_markdown_flow_definition(document, default_name="vm-flow")

    assert compiled["execution_mode"] == "vm"
    assert compiled["vm_source"] == '"hello from vm" answer'


def test_compile_markdown_agent_definition_maps_extends_to_base_agent(tmp_path: Path):
    agent_file = tmp_path / "review.agent.md"
    agent_file.write_text(
        """---
name: review.safe
extends: core.review
---
Use a stricter review bar.
""",
        encoding="utf-8",
    )

    document = load_markdown_asset_document(agent_file)
    compiled = compile_markdown_agent_definition(document, default_name="review.safe")

    assert compiled["base_agent"] == "core.review"
    assert compiled["inline_prompt"] == "Use a stricter review bar."


def test_compile_markdown_agent_definition_preserves_commands(tmp_path: Path):
    agent_file = tmp_path / "review.agent.md"
    agent_file.write_text(
        """---
name: review.safe
flow: core.review
commands:
  - name: compact-now
    target: memory compact 1
    visibility: exported
    capabilities:
      - memory.compact
    payload_schema:
      type: object
    result_schema:
      type: object
    policy:
      confirmation: confirm
---
Use a stricter review bar.
""",
        encoding="utf-8",
    )

    document = load_markdown_asset_document(agent_file)
    compiled = compile_markdown_agent_definition(document, default_name="review.safe")

    assert compiled["commands"] == [
        {
            "name": "compact-now",
            "target": "memory compact 1",
            "visibility": "exported",
            "capabilities": ["memory.compact"],
            "payload_schema": {"type": "object"},
            "result_schema": {"type": "object"},
            "policy": {"confirmation": "confirm"},
        }
    ]


def test_compile_markdown_agent_definition_preserves_structured_command_targets(tmp_path: Path):
    agent_file = tmp_path / "review.agent.md"
    agent_file.write_text(
        """---
name: review.safe
flow: core.review
commands:
  - name: compact-via-review
    target:
      kind: agent_command
      agent: review.worker
      command: trim-delegated
      visibility: delegated
    visibility: exported
---
Use a stricter review bar.
""",
        encoding="utf-8",
    )

    document = load_markdown_asset_document(agent_file)
    compiled = compile_markdown_agent_definition(document, default_name="review.safe")

    assert compiled["commands"] == [
        {
            "name": "compact-via-review",
            "target": {
                "kind": "agent_command",
                "agent": "review.worker",
                "command": "trim-delegated",
                "visibility": "delegated",
            },
            "visibility": "exported",
        }
    ]


def test_compile_markdown_agent_definition_preserves_local_handler_targets(tmp_path: Path):
    agent_file = tmp_path / "review.agent.md"
    agent_file.write_text(
        """---
name: review.safe
flow: core.review
commands:
  - name: local-review
    target:
      kind: local_handler
      handler: review_local
    visibility: exported
---
Use a stricter review bar.
""",
        encoding="utf-8",
    )

    document = load_markdown_asset_document(agent_file)
    compiled = compile_markdown_agent_definition(document, default_name="review.safe")

    assert compiled["commands"] == [
        {
            "name": "local-review",
            "target": {
                "kind": "local_handler",
                "handler": "review_local",
            },
            "visibility": "exported",
        }
    ]


def test_serialize_markdown_agent_definition_writes_extends(tmp_path: Path):
    agent = type(
        "Agent",
        (),
        {
            "name": "review.safe",
            "flow": "core.review",
            "base_agent": "core.review",
            "description": "",
            "llm_profile": None,
            "skills": None,
            "tools": None,
            "commands": [],
            "extra_prompts": [],
            "tool_confirmation": {},
            "inline_prompt": "Use a stricter review bar.",
        },
    )()

    serialized = serialize_markdown_agent_definition(agent)

    assert "extends: core.review" in serialized


def test_serialize_markdown_agent_definition_writes_commands(tmp_path: Path):
    command = type(
        "AgentCommand",
        (),
        {
            "name": "compact-now",
            "target": "memory compact 1",
            "visibility": "exported",
            "description": "Compact the current session memory.",
            "capabilities": ["memory.compact"],
            "payload_schema": {"type": "object"},
            "result_schema": {"type": "object"},
            "policy": {"confirmation": "confirm"},
        },
    )()
    agent = type(
        "Agent",
        (),
        {
            "name": "review.safe",
            "flow": "core.review",
            "base_agent": None,
            "description": "",
            "llm_profile": None,
            "skills": None,
            "tools": None,
            "commands": [command],
            "extra_prompts": [],
            "tool_confirmation": {},
            "inline_prompt": "",
        },
    )()

    serialized = serialize_markdown_agent_definition(agent)

    assert "commands:" in serialized
    assert "name: compact-now" in serialized
    assert "target: memory compact 1" in serialized
    assert "payload_schema:" in serialized
    assert "result_schema:" in serialized
    assert "policy:" in serialized
