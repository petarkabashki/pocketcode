from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


RESOURCE_ROOT_HINTS = frozenset(
    {
        "agents",
        "hooks",
        "skills",
        "prompts",
        "tools",
        "llm-profiles",
        "state",
        "workspace.yaml",
    }
)
DEFAULT_RESOURCE_ROOT_DIRNAME = ".pocketcode"
PACKAGE_RESOURCE_ROOT_PARENT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ResourceRoot:
    name: str
    path: Path
    origin: str = "workspace"


def discover_resource_roots(workspace_root: str | Path) -> list[ResourceRoot]:
    discovered: list[ResourceRoot] = []
    seen: set[Path] = set()

    for resource_root in discover_package_resource_roots():
        if resource_root.path in seen:
            continue
        discovered.append(resource_root)
        seen.add(resource_root.path)

    root = Path(workspace_root).resolve()
    for resource_root in _discover_resource_roots_in(root, include_default=True, origin="workspace"):
        if resource_root.path in seen:
            continue
        discovered.append(resource_root)
        seen.add(resource_root.path)

    return discovered


def discover_package_resource_roots() -> list[ResourceRoot]:
    return _discover_resource_roots_in(PACKAGE_RESOURCE_ROOT_PARENT, include_default=False, origin="package")


def _discover_resource_roots_in(root: Path, *, include_default: bool, origin: str) -> list[ResourceRoot]:
    discovered: list[ResourceRoot] = []
    seen: set[Path] = set()

    default_root = root / DEFAULT_RESOURCE_ROOT_DIRNAME
    if include_default and _looks_like_resource_root(default_root):
        discovered.append(
            ResourceRoot(name=_resource_root_name(default_root), path=default_root.resolve(), origin=origin)
        )
        seen.add(default_root.resolve())

    for child in sorted(path for path in root.iterdir() if path.is_dir()):
        resolved_child = child.resolve()
        if resolved_child in seen:
            continue
        if not _looks_like_resource_root(child):
            continue
        discovered.append(ResourceRoot(name=_resource_root_name(child), path=resolved_child, origin=origin))
        seen.add(resolved_child)

    return discovered


def primary_resource_root(workspace_root: str | Path, resource_roots: list[ResourceRoot] | None = None) -> ResourceRoot:
    root = Path(workspace_root).resolve()
    discovered = resource_roots if resource_roots is not None else discover_resource_roots(root)
    workspace_discovered = [resource_root for resource_root in discovered if resource_root.origin == "workspace"]
    for resource_root in workspace_discovered:
        if resource_root.path.name == DEFAULT_RESOURCE_ROOT_DIRNAME:
            return resource_root
    if workspace_discovered:
        return workspace_discovered[0]
    default_root = root / DEFAULT_RESOURCE_ROOT_DIRNAME
    return ResourceRoot(name=_resource_root_name(default_root), path=default_root, origin="workspace")


def resource_root_for_path(path: str | Path, resource_roots: list[ResourceRoot]) -> ResourceRoot | None:
    resolved_path = Path(path).resolve()
    for resource_root in resource_roots:
        try:
            resolved_path.relative_to(resource_root.path)
        except ValueError:
            continue
        return resource_root
    return None


def resource_root_namespace(resource_root: ResourceRoot) -> str:
    return f"resource_root.{resource_root.name}"


def is_default_resource_root(resource_root: ResourceRoot) -> bool:
    return resource_root.path.name == DEFAULT_RESOURCE_ROOT_DIRNAME


def _looks_like_resource_root(path: Path) -> bool:
    if not path.is_dir():
        return False
    name = path.name
    if not name.startswith(".pocket"):
        return False
    for hint in RESOURCE_ROOT_HINTS:
        if (path / hint).exists():
            return True
    for child in path.iterdir():
        if child.is_dir() and child.name.startswith(("agent.", "hook.", "skill.", "tool.")):
            return True
    for child in path.iterdir():
        if not child.is_file():
            continue
        child_name = child.name
        if child_name.endswith((".agent.md", ".agent.yaml", ".hook.md", ".hook.yaml", ".tool.md", ".prompt.md", ".tool.py", ".md")):
            return True
    return False


def _resource_root_name(path: Path) -> str:
    name = path.name
    if name.startswith("."):
        name = name[1:]
    return name
