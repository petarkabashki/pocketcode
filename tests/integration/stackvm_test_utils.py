import time
from pathlib import Path
from typing import Iterable, Sequence

from pocketcode.core.engine import PocketCodeEngine


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_ROOT = REPO_ROOT / "examples"
EXAMPLE_NAMESPACE_ROOTS = [path for path in sorted(EXAMPLES_ROOT.iterdir()) if path.is_dir()]


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
    plugin_root = workspace_root / plugin_name
    vm_dir = plugin_root / "vm"
    plugin_root.mkdir(parents=True)
    vm_dir.mkdir(parents=True)

    write_fixture(
        plugin_root,
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
    workspace_paths: Iterable[str | Path] | None = None,
) -> PocketCodeEngine:
    resolved_workspace_paths = [str(path) for path in EXAMPLE_NAMESPACE_ROOTS]
    if workspace_paths is not None:
        resolved_workspace_paths = []
        for raw_path in workspace_paths:
            candidate = Path(raw_path)
            namespace_markers = ("*.md", "*.prompt.md", "*.tool.py")
            has_namespace_assets = candidate.is_dir() and any(
                next(candidate.glob(pattern), None) is not None
                for pattern in namespace_markers
            )
            if candidate.is_dir() and not has_namespace_assets:
                resolved_workspace_paths.extend(str(path) for path in sorted(candidate.iterdir()) if path.is_dir())
                continue
            resolved_workspace_paths.append(str(candidate))
        resolved_workspace_paths.extend(str(path) for path in EXAMPLE_NAMESPACE_ROOTS)

    config = {
        "llm": {"providers": {}, "profiles": {}},
        "runtime": {
            "workspace_paths": resolved_workspace_paths,
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
