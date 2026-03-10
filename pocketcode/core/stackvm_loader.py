from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

from pocketcode.core.markdown_assets import load_markdown_asset_document
from pocketcode.core.stackvm_parser import strip_stackvm_comments

logger = logging.getLogger(__name__)


def load_stackvm_program_source(
    *,
    vm_source: str | None,
    vm_entry: str | None,
    vm_module: str | None,
    vm_modules: Sequence[str] | None,
    vm_file: str | None,
    vm_files: Sequence[str] | None,
    base_dir: Path,
    search_roots: Sequence[Path] = (),
) -> tuple[str, list[str]]:
    sections: list[str] = []
    source_files: list[str] = []
    refs: list[str] = []
    if vm_modules:
        refs.extend(str(item).strip() for item in vm_modules if str(item).strip())
    if vm_module:
        refs.append(str(vm_module).strip())
    if vm_files:
        refs.extend(str(item).strip() for item in vm_files if str(item).strip())
    if vm_file:
        refs.append(str(vm_file).strip())

    seen_paths: set[Path] = set()
    for ref in refs:
        path = _resolve_stackvm_ref(ref=ref, base_dir=base_dir, search_roots=search_roots)
        if path in seen_paths:
            continue
        seen_paths.add(path)
        source_files.append(str(path))
        sections.append(_load_stackvm_file(path))

    inline_source = str(vm_source or "").strip()
    if inline_source:
        sections.append(inline_source)
    if vm_entry and not sections:
        logger.debug("StackVM flow uses entry '%s' without preloaded source.", vm_entry)
    return "\n\n".join(section for section in sections if section).strip(), source_files


def _resolve_stackvm_ref(*, ref: str, base_dir: Path, search_roots: Sequence[Path]) -> Path:
    cleaned = str(ref or "").strip()
    if not cleaned:
        raise ValueError("Empty StackVM source reference.")

    roots = [base_dir.resolve(), *(Path(root).resolve() for root in search_roots)]
    raw_path = Path(cleaned)
    candidates: list[Path] = []
    if raw_path.is_absolute():
        candidates.append(raw_path.resolve())
    elif any(separator in cleaned for separator in ("/", "\\")) or raw_path.suffix in {".vm", ".md"}:
        for root in roots:
            direct = (root / cleaned).resolve()
            nested = (root / "vm" / cleaned).resolve()
            candidates.append(direct)
            candidates.append(nested)
            if raw_path.suffix not in {".vm", ".md"}:
                candidates.append(direct.with_suffix(".vm"))
                candidates.append(direct.with_suffix(".md"))
                candidates.append(nested.with_suffix(".vm"))
                candidates.append(nested.with_suffix(".md"))
    else:
        relative = Path(*cleaned.split("."))
        for root in roots:
            candidates.append((root / "vm" / relative).with_suffix(".vm").resolve())
            candidates.append((root / "vm" / relative).with_suffix(".md").resolve())
            candidates.append((root / relative).with_suffix(".vm").resolve())
            candidates.append((root / relative).with_suffix(".md").resolve())

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"StackVM source reference '{ref}' could not be resolved from {base_dir}.")


def _load_stackvm_file(path: Path) -> str:
    if path.suffix.lower() == ".md":
        document = load_markdown_asset_document(path)
        vm_sections = [
            block.content.strip()
            for block in document.find_blocks(languages=("vm", "stackvm"))
            if block.content.strip()
        ]
        if vm_sections:
            return "\n\n".join(vm_sections).strip()
        return document.body.strip()
    return strip_stackvm_comments(path.read_text(encoding="utf-8")).strip()
