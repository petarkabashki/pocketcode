from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from pocketcode.core.markdown_assets import load_markdown_asset_document
from pocketcode.core.stackvm_parser import parse_stackvm_source, serialize_stackvm_ast, strip_stackvm_comments
from pocketcode.core.stackvm_stdlib_manifest import resolve_stackvm_stdlib_module_alias
from pocketcode.core.stackvm_lockfile import is_remote_ref, resolve_remote_ref

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StackVmModuleImport:
    target_name: str
    alias: str


@dataclass
class StackVmModuleDefinition:
    ref: str
    source_path: Path | None
    source: str
    ast: list[Any]
    module_name: str | None = None
    compatibility_prefix: str | None = None
    local_names: set[str] = field(default_factory=set)
    explicit_exports: set[str] = field(default_factory=set)
    imports: list[StackVmModuleImport] = field(default_factory=list)
    export_names: set[str] = field(default_factory=set)


STACKVM_MODULE_FORMS = {
    "module",
    "export",
    "import",
}


def load_stackvm_program_source(
    *,
    vm_source: str | None,
    vm_entry: str | None,
    vm_module: str | None,
    vm_modules: Sequence[str] | None,
    vm_module_prefixes: dict[str, str] | None,
    vm_file: str | None,
    vm_files: Sequence[str] | None,
    base_dir: Path,
    search_roots: Sequence[Path] = (),
) -> tuple[str, list[str]]:
    sections: list[str] = []
    source_files: list[str] = []
    module_definitions: list[StackVmModuleDefinition] = []
    refs: list[str] = []
    if vm_modules:
        refs.extend(str(item).strip() for item in vm_modules if str(item).strip())
    if vm_module:
        refs.append(str(vm_module).strip())
    if vm_files:
        refs.extend(str(item).strip() for item in vm_files if str(item).strip())
    if vm_file:
        refs.append(str(vm_file).strip())

    prefix_map = {
        str(key).strip(): str(value).strip()
        for key, value in (vm_module_prefixes or {}).items()
        if str(key).strip() and str(value).strip()
    }
    seen_paths: set[Path] = set()
    for ref in refs:
        path = _resolve_stackvm_ref(ref=ref, base_dir=base_dir, search_roots=search_roots)
        if path in seen_paths:
            continue
        seen_paths.add(path)
        source_files.append(str(path))
        source = _read_stackvm_file(path)
        module_definitions.append(
            _build_module_definition(
                ref=ref,
                source=source,
                source_path=path,
                compatibility_prefix=prefix_map.get(ref),
            )
        )

    inline_source = str(vm_source or "").strip()
    if inline_source:
        module_definitions.append(
            _build_module_definition(
                ref="<inline>",
                source=inline_source,
                source_path=None,
                compatibility_prefix=None,
            )
        )
    if vm_entry and not module_definitions:
        logger.debug("StackVM flow uses entry '%s' without preloaded source.", vm_entry)

    sections.extend(_link_stackvm_modules(module_definitions))
    return "\n\n".join(section for section in sections if section).strip(), source_files


def _resolve_stackvm_ref(*, ref: str, base_dir: Path, search_roots: Sequence[Path]) -> Path:
    cleaned = str(ref or "").strip()
    if not cleaned:
        raise ValueError("Empty StackVM source reference.")

    roots = [base_dir.resolve(), *(Path(root).resolve() for root in search_roots)]
    stdlib_alias_path = resolve_stackvm_stdlib_module_alias(cleaned, search_roots=roots)
    if stdlib_alias_path is not None:
        return stdlib_alias_path
        
    if is_remote_ref(cleaned):
        return resolve_remote_ref(cleaned, base_dir)
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


def _read_stackvm_file(path: Path) -> str:
    if path.suffix.lower() == ".md":
        document = load_markdown_asset_document(path)
        vm_sections = [
            block.content.strip()
            for block in document.find_blocks(languages=("vm", "stackvm"))
            if block.content.strip()
        ]
        if vm_sections:
            return "\n\n".join(vm_sections).strip()
        # T011, T028: If this is an asset with front matter but no VM blocks, 
        # return empty string to avoid treating body text as VM code.
        if document.front_matter:
            return ""
        return document.body.strip()
    return strip_stackvm_comments(path.read_text(encoding="utf-8")).strip()


def _build_module_definition(
    *,
    ref: str,
    source: str,
    source_path: Path | None,
    compatibility_prefix: str | None,
) -> StackVmModuleDefinition:
    ast = parse_stackvm_source(source) if source.strip() else []
    module_name = _find_declared_module_name(ast)
    if compatibility_prefix:
        logger.warning(
            f"StackVM loader is using deprecated compatibility_prefix '{compatibility_prefix}' for '{ref}'. "
            "Please add an explicit 'module {name}' declaration to the source."
        )
    if module_name and compatibility_prefix and module_name != compatibility_prefix:
        raise ValueError(
            f"StackVM module '{ref}' declares module name '{module_name}' but flow compatibility prefix is "
            f"'{compatibility_prefix}'."
        )

    local_names = _collect_local_names(ast)
    explicit_exports = _collect_module_exports(ast)
    imports = _collect_module_imports(ast)
    effective_module_name = module_name or (str(compatibility_prefix or "").strip() or None)
    export_names = set(explicit_exports)
    if effective_module_name and not module_name:
        export_names = set(local_names)

    unknown_export_names = sorted(name for name in explicit_exports if name not in local_names)
    if unknown_export_names:
        raise ValueError(
            f"StackVM module '{ref}' exports unknown local names: {', '.join(unknown_export_names)}."
        )

    import_aliases = {entry.alias for entry in imports}
    collisions = sorted(import_aliases & local_names)
    if collisions:
        raise ValueError(
            f"StackVM module '{ref}' imports aliases that collide with local definitions: {', '.join(collisions)}."
        )

    if (explicit_exports or imports) and not effective_module_name:
        raise ValueError(
            f"StackVM module '{ref}' uses import/export forms without declaring a module name."
        )

    return StackVmModuleDefinition(
        ref=ref,
        source_path=source_path,
        source=source,
        ast=ast,
        module_name=effective_module_name,
        compatibility_prefix=str(compatibility_prefix).strip() or None,
        local_names=local_names,
        explicit_exports=explicit_exports,
        imports=imports,
        export_names=export_names,
    )


def _link_stackvm_modules(modules: list[StackVmModuleDefinition]) -> list[str]:
    if not modules:
        return []

    module_name_to_ref: dict[str, str] = {}
    exported_symbol_table: dict[str, str] = {}
    dependency_graph: dict[str, set[str]] = {}

    for module in modules:
        module_ref = module.ref
        module_name = str(module.module_name).strip() if module.module_name else ""
        if module_name:
            if module_name in module_name_to_ref and module_name_to_ref[module_name] != module_ref:
                raise ValueError(
                    f"StackVM module name '{module_name}' is declared by both '{module_name_to_ref[module_name]}' "
                    f"and '{module_ref}'."
                )
            module_name_to_ref[module_name] = module_ref

        if not module_name:
            continue
        for export_name in module.export_names:
            qualified_name = _qualify_name(export_name, prefix=module_name)
            prior = exported_symbol_table.get(qualified_name)
            if prior and prior != module_ref:
                raise ValueError(
                    f"StackVM export '{qualified_name}' is declared by both '{prior}' and '{module_ref}'."
                )
            exported_symbol_table[qualified_name] = module_ref

    for module in modules:
        module_ref = module.ref
        module_name = str(module.module_name).strip() if module.module_name else ""
        dependency_graph[module_ref] = set()
        for imported in module.imports:
            dependency_name = imported.target_name.rsplit(".", 1)[0]
            if imported.target_name not in exported_symbol_table:
                raise ValueError(
                    f"StackVM module '{module_ref}' imports unknown symbol '{imported.target_name}'."
                )
            dependency_ref = module_name_to_ref.get(dependency_name)
            if dependency_ref and dependency_ref != module_ref:
                dependency_graph[module_ref].add(dependency_ref)
        if module_name and module.ref in dependency_graph[module_ref]:
            dependency_graph[module_ref].remove(module.ref)

    _validate_module_cycles(dependency_graph)

    sections: list[str] = []
    for module in modules:
        rewritten_ast = _rewrite_linked_module_ast(module, exported_symbol_table=exported_symbol_table)
        serialized = serialize_stackvm_ast(rewritten_ast).strip()
        if serialized:
            sections.append(serialized)
    return sections


def _validate_module_cycles(dependency_graph: dict[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def _walk(node: str, stack: list[str]) -> None:
        if node in visited:
            return
        if node in visiting:
            cycle_start = stack.index(node)
            cycle = stack[cycle_start:] + [node]
            raise ValueError(f"StackVM module import cycle detected: {' -> '.join(cycle)}.")
        visiting.add(node)
        stack.append(node)
        for dependency in sorted(dependency_graph.get(node, ())):
            _walk(dependency, stack)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for module_ref in sorted(dependency_graph):
        _walk(module_ref, [])


def _find_declared_module_name(ast: list[Any]) -> str | None:
    found_name: str | None = None

    def _visit(items: list[Any]) -> None:
        nonlocal found_name
        index = 0
        while index < len(items):
            if _matches_module_decl(items, index):
                module_name = _literal_name(items[index])
                if found_name and module_name and found_name != module_name:
                    raise ValueError(
                        f"StackVM source declares multiple module names: '{found_name}' and '{module_name}'."
                    )
                found_name = module_name or found_name
                index += 2
                continue
            item = items[index]
            if isinstance(item, list):
                _visit(item)
            index += 1

    _visit(ast)
    return found_name


def _collect_module_exports(ast: list[Any]) -> set[str]:
    exports: set[str] = set()

    def _visit(items: list[Any]) -> None:
        index = 0
        while index < len(items):
            if _matches_export(items, index):
                export_name = _literal_name(items[index])
                if export_name:
                    exports.add(export_name)
                index += 2
                continue
            item = items[index]
            if isinstance(item, list):
                _visit(item)
            index += 1

    _visit(ast)
    return exports


def _collect_module_imports(ast: list[Any]) -> list[StackVmModuleImport]:
    imports: list[StackVmModuleImport] = []

    def _visit(items: list[Any]) -> None:
        index = 0
        while index < len(items):
            if _matches_import_alias(items, index):
                target_name = _literal_name(items[index])
                alias_name = _literal_name(items[index + 1])
                if target_name and alias_name:
                    imports.append(StackVmModuleImport(target_name=target_name, alias=alias_name))
                index += 3
                continue
            if _matches_import_plain(items, index):
                target_name = _literal_name(items[index])
                if target_name:
                    imports.append(
                        StackVmModuleImport(
                            target_name=target_name,
                            alias=target_name.rsplit(".", 1)[-1],
                        )
                    )
                index += 2
                continue
            item = items[index]
            if isinstance(item, list):
                _visit(item)
            index += 1

    _visit(ast)
    return imports


def _collect_local_names(ast: list[Any]) -> set[str]:
    names: set[str] = set()

    def _visit(items: list[Any]) -> None:
        index = 0
        while index < len(items):
            if _matches_define(items, index):
                name = _literal_name(items[index + 1])
                if name and not _is_qualified(name):
                    names.add(name)
                _visit(items[index])
                index += 3
                continue
            if _matches_defmacro_plain(items, index):
                params_node = items[index]
                template_node = items[index + 1]
                name = _literal_name(items[index + 2])
                if name and not _is_qualified(name):
                    names.add(name)
                _visit(params_node)
                _visit(template_node)
                index += 4
                continue
            if _matches_defmacro_syntax(items, index):
                params_node = items[index]
                template_node = items[index + 1]
                name = _literal_name(items[index + 3])
                if name and not _is_qualified(name):
                    names.add(name)
                _visit(params_node)
                _visit(template_node)
                index += 5
                continue
            item = items[index]
            if isinstance(item, list):
                _visit(item)
            index += 1

    _visit(ast)
    return names


def _rewrite_linked_module_ast(
    module: StackVmModuleDefinition,
    *,
    exported_symbol_table: dict[str, str],
) -> list[Any]:
    import_aliases = {entry.alias: entry.target_name for entry in module.imports}
    return _rewrite_prefixed_ast(
        module.ast,
        local_names=module.local_names,
        module_name=module.module_name,
        import_aliases=import_aliases,
        bound_params=set(),
        exported_symbol_table=exported_symbol_table,
    )


def _rewrite_prefixed_ast(
    items: list[Any],
    *,
    local_names: set[str],
    module_name: str | None,
    import_aliases: dict[str, str],
    bound_params: set[str],
    exported_symbol_table: dict[str, str],
) -> list[Any]:
    rewritten: list[Any] = []
    index = 0
    while index < len(items):
        if _matches_module_decl(items, index):
            index += 2
            continue
        if _matches_export(items, index):
            index += 2
            continue
        if _matches_import_alias(items, index):
            index += 3
            continue
        if _matches_import_plain(items, index):
            index += 2
            continue
        if _matches_define(items, index):
            quotation_node = items[index]
            name_node = items[index + 1]
            rewritten.extend(
                [
                    _rewrite_node(
                        quotation_node,
                        local_names=local_names,
                        module_name=module_name,
                        import_aliases=import_aliases,
                        bound_params=bound_params,
                        exported_symbol_table=exported_symbol_table,
                    ),
                    _qualify_literal_name(name_node, prefix=module_name),
                    items[index + 2],
                ]
            )
            index += 3
            continue
        if _matches_defmacro_plain(items, index):
            params_node = items[index]
            template_node = items[index + 1]
            name_node = items[index + 2]
            param_names = _macro_param_names(params_node)
            rewritten.extend(
                [
                    list(params_node),
                    _rewrite_node(
                        template_node,
                        local_names=local_names,
                        module_name=module_name,
                        import_aliases=import_aliases,
                        bound_params=bound_params | param_names,
                        exported_symbol_table=exported_symbol_table,
                    ),
                    _qualify_literal_name(name_node, prefix=module_name),
                    items[index + 3],
                ]
            )
            index += 4
            continue
        if _matches_defmacro_syntax(items, index):
            params_node = items[index]
            template_node = items[index + 1]
            name_node = items[index + 3]
            param_names = _macro_param_names(params_node)
            rewritten.extend(
                [
                    list(params_node),
                    _rewrite_node(
                        template_node,
                        local_names=local_names,
                        module_name=module_name,
                        import_aliases=import_aliases,
                        bound_params=bound_params | param_names,
                        exported_symbol_table=exported_symbol_table,
                    ),
                    items[index + 2],
                    _qualify_literal_name(name_node, prefix=module_name),
                    items[index + 4],
                ]
            )
            index += 5
            continue
        rewritten.append(
            _rewrite_node(
                items[index],
                local_names=local_names,
                module_name=module_name,
                import_aliases=import_aliases,
                bound_params=bound_params,
                exported_symbol_table=exported_symbol_table,
            )
        )
        index += 1
    return rewritten


def _rewrite_node(
    node: Any,
    *,
    local_names: set[str],
    module_name: str | None,
    import_aliases: dict[str, str],
    bound_params: set[str],
    exported_symbol_table: dict[str, str],
) -> Any:
    if isinstance(node, list):
        return _rewrite_prefixed_ast(
            node,
            local_names=local_names,
            module_name=module_name,
            import_aliases=import_aliases,
            bound_params=bound_params,
            exported_symbol_table=exported_symbol_table,
        )
    if not isinstance(node, tuple) or len(node) != 2:
        return node
    token_type, token_value = node
    if token_type != "sym":
        return node

    symbol_name = str(token_value)
    if symbol_name in bound_params:
        return node
    if symbol_name in import_aliases:
        return ("sym", import_aliases[symbol_name])
    if symbol_name in local_names:
        return ("sym", _qualify_name(symbol_name, prefix=module_name))
    if _is_qualified(symbol_name) and symbol_name in exported_symbol_table:
        return node
    return node


def _macro_param_names(node: Any) -> set[str]:
    if not isinstance(node, list):
        return set()
    return {
        str(item[1])
        for item in node
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "sym" and str(item[1]).strip()
    }


def _qualify_literal_name(node: Any, *, prefix: str | None) -> Any:
    if not isinstance(node, tuple) or len(node) != 2:
        return node
    token_type, token_value = node
    if token_type not in {"str", "sym"}:
        return node
    name = str(token_value).strip()
    if not name or _is_qualified(name):
        return node
    return (token_type, _qualify_name(name, prefix=prefix))


def _literal_name(node: Any) -> str:
    if isinstance(node, tuple) and len(node) == 2 and node[0] in {"str", "sym"}:
        return str(node[1]).strip()
    return ""


def _qualify_name(name: str, *, prefix: str | None) -> str:
    cleaned_name = str(name).strip()
    cleaned_prefix = str(prefix or "").strip()
    if not cleaned_name or not cleaned_prefix or _is_qualified(cleaned_name):
        return cleaned_name
    return f"{cleaned_prefix}.{cleaned_name}"


def _is_qualified(name: str) -> bool:
    return "." in str(name).strip()


def _matches_module_decl(items: list[Any], index: int) -> bool:
    return index + 1 < len(items) and _is_string_literal_name(items[index]) and _is_symbol(items[index + 1], "module")


def _matches_export(items: list[Any], index: int) -> bool:
    return index + 1 < len(items) and _is_string_literal_name(items[index]) and _is_symbol(items[index + 1], "export")


def _matches_import_plain(items: list[Any], index: int) -> bool:
    return (
        index + 1 < len(items)
        and _is_string_literal_name(items[index])
        and _is_symbol(items[index + 1], "import")
    )


def _matches_import_alias(items: list[Any], index: int) -> bool:
    return (
        index + 2 < len(items)
        and _is_string_literal_name(items[index])
        and _is_string_literal_name(items[index + 1])
        and _is_symbol(items[index + 2], "import")
    )


def _matches_define(items: list[Any], index: int) -> bool:
    return index + 2 < len(items) and isinstance(items[index], list) and _is_symbol(items[index + 2], "define")


def _matches_defmacro_plain(items: list[Any], index: int) -> bool:
    return (
        index + 3 < len(items)
        and isinstance(items[index], list)
        and isinstance(items[index + 1], list)
        and _is_literal_name(items[index + 2])
        and _is_symbol(items[index + 3], "defmacro")
    )


def _matches_defmacro_syntax(items: list[Any], index: int) -> bool:
    return (
        index + 4 < len(items)
        and isinstance(items[index], list)
        and isinstance(items[index + 1], list)
        and _is_symbol(items[index + 2], "syntax-quote")
        and _is_literal_name(items[index + 3])
        and _is_symbol(items[index + 4], "defmacro")
    )


def _is_symbol(node: Any, value: str) -> bool:
    return isinstance(node, tuple) and len(node) == 2 and node[0] == "sym" and str(node[1]) == value


def _is_literal_name(node: Any) -> bool:
    return isinstance(node, tuple) and len(node) == 2 and node[0] in {"str", "sym"} and bool(str(node[1]).strip())


def _is_string_literal_name(node: Any) -> bool:
    return isinstance(node, tuple) and len(node) == 2 and node[0] == "str" and bool(str(node[1]).strip())
