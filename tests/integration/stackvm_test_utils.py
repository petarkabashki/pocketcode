import time
import shutil
from pathlib import Path
from typing import Iterable, Sequence

from pocketcode.core.engine import PocketCodeEngine
from pocketcode.core.markdown_assets import load_markdown_asset_document
from pocketcode.core.stackvm_loader import load_stackvm_program_source


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_ROOT = REPO_ROOT / "examples"
EXAMPLE_NAMESPACE_ROOTS = [path for path in sorted(EXAMPLES_ROOT.iterdir()) if path.is_dir()]


def write_fixture(workspace_root: Path, filename: str, lines: list[str]) -> None:
    (workspace_root / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_temp_stackvm_namespace(
    workspace_root: Path,
    *,
    namespace_dir_name: str,
    namespace_name: str,
    namespace_description: str,
    flow_name: str,
    flow_description: str,
    flow_body_lines: Sequence[str],
    vm_lines: Sequence[str],
) -> tuple[Path, str]:
    namespace_root = workspace_root / namespace_name
    vm_dir = namespace_root / "vm"
    namespace_root.mkdir(parents=True)
    vm_dir.mkdir(parents=True)

    write_fixture(
        namespace_root,
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
    return namespace_root, f"{namespace_name}.{flow_name}"


def make_example_engine(
    workspace_root: Path,
    default_agent: str,
    *,
    workspace_paths: Iterable[str | Path] | None = None,
) -> PocketCodeEngine:
    shared_vm_root = REPO_ROOT / "vm"
    if shared_vm_root.is_dir():
        shutil.copytree(shared_vm_root, workspace_root / "vm", dirs_exist_ok=True)

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


def load_example_linked_vm_source(example_name: str, *vm_refs: str) -> str:
    example_root = EXAMPLES_ROOT / example_name
    source, _ = load_stackvm_program_source(
        vm_source=None,
        vm_entry="decide",
        vm_module=None,
        vm_modules=vm_refs,
        vm_module_prefixes=None,
        vm_file=None,
        vm_files=None,
        base_dir=example_root,
        search_roots=(REPO_ROOT, example_root),
    )
    return source


def load_example_asset_vm_source(example_name: str, markdown_name: str) -> str:
    example_root = EXAMPLES_ROOT / example_name
    document = load_markdown_asset_document(example_root / markdown_name)
    metadata = document.front_matter
    source, _ = load_stackvm_program_source(
        vm_source=metadata.get("vm_source"),
        vm_entry=metadata.get("vm_entry"),
        vm_module=metadata.get("vm_module"),
        vm_modules=metadata.get("vm_modules"),
        vm_module_prefixes=metadata.get("vm_module_prefixes"),
        vm_file=metadata.get("vm_file"),
        vm_files=metadata.get("vm_files"),
        base_dir=example_root,
        search_roots=(REPO_ROOT, example_root),
    )
    return source
