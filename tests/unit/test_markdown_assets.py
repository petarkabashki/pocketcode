from __future__ import annotations

from pathlib import Path

from pocketcode.core.markdown_assets import (
    compile_markdown_flow_definition,
    compile_markdown_tool_definition,
    load_markdown_asset_document,
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


def test_compile_markdown_flow_definition_collects_graph_metadata(tmp_path: Path):
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
    assert compiled["metadata"]["markdown_graphs"][0]["language"] == "mermaid"


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