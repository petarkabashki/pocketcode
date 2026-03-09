import time
from pathlib import Path
from typing import Iterable, Sequence

from pocketcode.core.engine import PocketCodeEngine


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_ROOT = REPO_ROOT / "examples"


def write_fixture(workspace_root: Path, filename: str, lines: list[str]) -> None:
    (workspace_root / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_temp_stackvm_plugin(
    workspace_root: Path,
    *,
    plugin_dir_name: str,
    plugin_name: str,
    plugin_description: str,
    flow_name: str,
    flow_description: str,
    flow_body_lines: Sequence[str],
    vm_lines: Sequence[str],
) -> tuple[Path, str]:
    plugin_root = workspace_root / plugin_dir_name
    flows_dir = plugin_root / "flows"
    vm_dir = plugin_root / "vm"
    flows_dir.mkdir(parents=True)
    vm_dir.mkdir(parents=True)

    write_fixture(
        plugin_root,
        "plugin.yaml",
        [
            "schema_version: 1",
            f"name: {plugin_name}",
            f"description: {plugin_description}",
            "flows:",
            f"  {flow_name}:",
            f"    markdown: flows/{flow_name}.md",
        ],
    )
    write_fixture(
        flows_dir,
        f"{flow_name}.md",
        [
            "---",
            f"name: {flow_name}",
            f"description: {flow_description}",
            "vm_entry: decide",
            "vm_modules:",
            "  - vm/router",
            "---",
            "",
            *flow_body_lines,
        ],
    )
    write_fixture(vm_dir, "router.vm", list(vm_lines))
    return plugin_root, f"{plugin_name}.{flow_name}"


def make_example_engine(
    workspace_root: Path,
    default_agent: str,
    *,
    plugin_paths: Iterable[str | Path] | None = None,
) -> PocketCodeEngine:
    resolved_plugin_paths = [str(EXAMPLES_ROOT)]
    if plugin_paths is not None:
        resolved_plugin_paths = [str(Path(path)) for path in plugin_paths]
        resolved_plugin_paths.append(str(EXAMPLES_ROOT))

    config = {
        "llm": {"providers": {}, "profiles": {}},
        "runtime": {
            "plugin_paths": resolved_plugin_paths,
            "default_agent": default_agent,
            "auto_confirm_tools": True,
            "require_tool_confirmation": False,
        },
    }
    return PocketCodeEngine(config=config, workspace_root=workspace_root)


def request_context() -> dict:
    return {"files": set(), "folders": set(), "urls": set(), "snippets": {}}


def wait_for_new_interaction_request(handle, events, seen_request_ids, attempts: int = 80):
    for _ in range(attempts):
        batch = handle.drain_events()
        events.extend(batch)
        for event in batch:
            if event.get("type") != "interaction_requested":
                continue
            request_id = str(event.get("request_id") or "")
            if request_id in seen_request_ids:
                continue
            seen_request_ids.add(request_id)
            return event
        time.sleep(0.01)
    return None
