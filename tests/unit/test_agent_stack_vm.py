from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pocketcode.core.agent_stack_vm import (
    AgentStackVM,
    StackVmIllegalChildEffectError,
    StackVmExecutionResult,
    StackVmHostContext,
)
from pocketcode.core.session_manager import SessionManager
from pocketcode.core.stackvm_loader import load_stackvm_program_source


def test_load_stackvm_program_source_resolves_module_and_markdown_sources(tmp_path: Path):
    vm_root = tmp_path / "vm"
    vm_root.mkdir(parents=True, exist_ok=True)
    (vm_root / "common.vm").write_text('"common loaded" "common_message" store-set\n', encoding="utf-8")
    (vm_root / "tail.md").write_text(
        """---
name: tail
---

```vm
"tail loaded" "tail_message" store-set
```
""",
        encoding="utf-8",
    )

    source, source_files = load_stackvm_program_source(
        vm_source='"inline loaded" "inline_message" store-set',
        vm_entry=None,
        vm_module="common",
        vm_modules=[],
        vm_module_prefixes={},
        vm_file="vm/tail.md",
        vm_files=[],
        base_dir=tmp_path,
        search_roots=[tmp_path],
    )

    assert '"common loaded" "common_message" store-set' in source
    assert '"tail loaded" "tail_message" store-set' in source
    assert '"inline loaded" "inline_message" store-set' in source
    assert str(vm_root / "common.vm") in source_files
    assert str(vm_root / "tail.md") in source_files


def test_load_stackvm_program_source_resolves_slash_style_refs_without_suffix(tmp_path: Path):
    vm_root = tmp_path / "vm"
    vm_root.mkdir(parents=True, exist_ok=True)
    (vm_root / "router.vm").write_text('[ "resolved" answer ] "route" define\n', encoding="utf-8")

    source, source_files = load_stackvm_program_source(
        vm_source=None,
        vm_entry="route",
        vm_module="vm/router",
        vm_modules=[],
        vm_module_prefixes={},
        vm_file=None,
        vm_files=[],
        base_dir=tmp_path,
        search_roots=[tmp_path],
    )

    assert '[ "resolved" answer ] "route" define' in source
    assert str(vm_root / "router.vm") in source_files


def test_load_stackvm_program_source_applies_module_prefixes_to_user_words_and_macros(tmp_path: Path):
    vm_root = tmp_path / "vm"
    vm_root.mkdir(parents=True, exist_ok=True)
    (vm_root / "common.vm").write_text(
        '\n'.join(
            [
                '[ "base" ] "payload-data" define',
                '[ value ] [ value common.decorate ] "wrap" defmacro',
                '[ value ] [ [ value unquote ] common.decorate ] syntax-quote "emit" defmacro',
                '[ "value:" swap concat ] "decorate" define',
                '[ payload-data ] "message" define',
            ]
        ),
        encoding="utf-8",
    )

    source, _ = load_stackvm_program_source(
        vm_source=None,
        vm_entry="route",
        vm_module="common",
        vm_modules=[],
        vm_module_prefixes={"common": "common"},
        vm_file=None,
        vm_files=[],
        base_dir=tmp_path,
        search_roots=[tmp_path],
    )

    assert '"common.payload-data" define' in source
    assert '"common.decorate" define' in source
    assert '"common.wrap" defmacro' in source
    assert '"common.emit" defmacro' in source
    assert 'common.payload-data' in source
    assert 'common.decorate' in source
    assert 'value unquote' in source


def test_load_stackvm_program_source_links_explicit_module_exports_and_imports(tmp_path: Path):
    vm_root = tmp_path / "vm"
    vm_root.mkdir(parents=True, exist_ok=True)
    (vm_root / "common.vm").write_text(
        '\n'.join(
            [
                '"common" module',
                '[ "shared payload" ] "payload-data" define',
                '"payload-data" export',
                '[ value ] [ [ value unquote ] common.decorate ] syntax-quote "emit" defmacro',
                '"emit" export',
                '[ "value:" swap concat ] "decorate" define',
                '"decorate" export',
            ]
        ),
        encoding="utf-8",
    )
    (vm_root / "router.vm").write_text(
        '\n'.join(
            [
                '"router" module',
                '"common.payload-data" import',
                '"common.emit" import',
                '[ payload-data "message" store-set "ok" emit ] "route" define',
                '"route" export',
            ]
        ),
        encoding="utf-8",
    )

    source, _ = load_stackvm_program_source(
        vm_source=None,
        vm_entry="router.route",
        vm_module=None,
        vm_modules=["vm/common", "vm/router"],
        vm_module_prefixes={},
        vm_file=None,
        vm_files=[],
        base_dir=tmp_path,
        search_roots=[tmp_path],
    )

    assert '"common.payload-data" define' in source
    assert '"common.decorate" define' in source
    assert '"common.emit" defmacro' in source
    assert '"router.route" define' in source
    assert 'common.payload-data "message" store-set' in source
    assert '"ok" common.emit' in source
    assert '"router" module' not in source
    assert ' import' not in source
    assert ' export' not in source


def test_load_stackvm_program_source_resolves_shared_stdlib_from_workspace_root_search_path(tmp_path: Path):
    workspace_vm_root = tmp_path / "vm" / "stdlib"
    workspace_vm_root.mkdir(parents=True, exist_ok=True)
    (workspace_vm_root / "config.vm").write_text(
        '\n'.join(
            [
                '"stdlib.config" module',
                '[ "from-stdlib" ] "value" define',
                '"value" export',
            ]
        ),
        encoding="utf-8",
    )

    namespace_root = tmp_path / "example_ns"
    namespace_vm_root = namespace_root / "vm"
    namespace_vm_root.mkdir(parents=True, exist_ok=True)
    (namespace_vm_root / "router.vm").write_text(
        '\n'.join(
            [
                '"router" module',
                '"stdlib.config.value" import',
                '[ value ] "route" define',
                '"route" export',
            ]
        ),
        encoding="utf-8",
    )

    source, _ = load_stackvm_program_source(
        vm_source=None,
        vm_entry="router.route",
        vm_module=None,
        vm_modules=["stdlib.config", "vm/router"],
        vm_module_prefixes={},
        vm_file=None,
        vm_files=[],
        base_dir=namespace_root,
        search_roots=[namespace_root, tmp_path],
    )

    assert '"stdlib.config.value" define' in source
    assert '"router.route" define' in source
    assert 'stdlib.config.value' in source


def test_load_stackvm_program_source_links_shared_stdlib_macro_from_workspace_root(tmp_path: Path):
    workspace_vm_root = tmp_path / "vm" / "stdlib"
    workspace_vm_root.mkdir(parents=True, exist_ok=True)
    (workspace_vm_root / "io.vm").write_text(
        '\n'.join(
            [
                '"stdlib.io" module',
                '[ request_expr later_turn ] [ "core.read_file" [ request_expr unquote ] [ later_turn unquote ] tool-once ] syntax-quote "read-file-once" defmacro',
                '[ path_expr later_turn ] [ [ "{path: " [ path_expr unquote ] concat "}" concat yaml> ] [ later_turn unquote ] stdlib.io.read-file-once ] syntax-quote "read-yaml-file-once" defmacro',
                '"read-file-once" export',
                '"read-yaml-file-once" export',
            ]
        ),
        encoding="utf-8",
    )

    namespace_root = tmp_path / "example_ns"
    namespace_vm_root = namespace_root / "vm"
    namespace_vm_root.mkdir(parents=True, exist_ok=True)
    (namespace_vm_root / "router.vm").write_text(
        '\n'.join(
            [
                '"router" module',
                '[ "payload.yaml" [ "done" answer ] stdlib.io.read-yaml-file-once ] "route" define',
                '"route" export',
            ]
        ),
        encoding="utf-8",
    )

    source, source_files = load_stackvm_program_source(
        vm_source=None,
        vm_entry="router.route",
        vm_module=None,
        vm_modules=["stdlib.io", "vm/router"],
        vm_module_prefixes={},
        vm_file=None,
        vm_files=[],
        base_dir=namespace_root,
        search_roots=[namespace_root, tmp_path],
    )

    assert '"stdlib.io.read-yaml-file-once" defmacro' in source
    assert '"router.route" define' in source
    assert '[ "payload.yaml" [ "done" answer ] stdlib.io.read-yaml-file-once ] "router.route" define' in source
    assert str(workspace_vm_root / "io.vm") in source_files
    assert str(namespace_vm_root / "router.vm") in source_files


def test_load_stackvm_program_source_supports_stdlib_alias_for_vm_module(tmp_path: Path):
    workspace_vm_root = tmp_path / "vm" / "stdlib"
    workspace_vm_root.mkdir(parents=True, exist_ok=True)
    (workspace_vm_root / "stdlib.yaml").write_text(
        "\n".join(
            [
                "package: stackvm-stdlib",
                "version: 0.1.0",
                "module_root: vm/stdlib",
                "modules:",
                "  - name: stdlib.config",
                "    ref: vm/stdlib/config",
                "    file: vm/stdlib/config.vm",
                "    summary: Demo module.",
                "    exports:",
                "      - value",
            ]
        ),
        encoding="utf-8",
    )
    (workspace_vm_root / "config.vm").write_text(
        '\n'.join(
            [
                '"stdlib.config" module',
                '[ "from-alias" ] "value" define',
                '"value" export',
            ]
        ),
        encoding="utf-8",
    )

    namespace_root = tmp_path / "example_ns"
    namespace_vm_root = namespace_root / "vm"
    namespace_vm_root.mkdir(parents=True, exist_ok=True)
    (namespace_vm_root / "router.vm").write_text(
        '\n'.join(
            [
                '"router" module',
                '"stdlib.config.value" import',
                '[ value ] "route" define',
                '"route" export',
            ]
        ),
        encoding="utf-8",
    )

    source, source_files = load_stackvm_program_source(
        vm_source=None,
        vm_entry="router.route",
        vm_module=None,
        vm_modules=["stdlib.config", "vm/router"],
        vm_module_prefixes={},
        vm_file=None,
        vm_files=[],
        base_dir=namespace_root,
        search_roots=[namespace_root, tmp_path],
    )

    assert '"stdlib.config.value" define' in source
    assert any(path.endswith("vm/stdlib/config.vm") for path in source_files)


def test_load_stackvm_program_source_rejects_unknown_module_imports(tmp_path: Path):
    vm_root = tmp_path / "vm"
    vm_root.mkdir(parents=True, exist_ok=True)
    (vm_root / "router.vm").write_text(
        '\n'.join(
            [
                '"router" module',
                '"common.missing" import',
                '[ missing ] "route" define',
                '"route" export',
            ]
        ),
        encoding="utf-8",
    )

    try:
        load_stackvm_program_source(
            vm_source=None,
            vm_entry="router.route",
            vm_module="vm/router",
            vm_modules=[],
            vm_module_prefixes={},
            vm_file=None,
            vm_files=[],
            base_dir=tmp_path,
            search_roots=[tmp_path],
        )
    except ValueError as exc:
        assert "imports unknown symbol 'common.missing'" in str(exc)
    else:
        raise AssertionError("Expected unknown module import to fail.")


def test_load_stackvm_program_source_rejects_module_import_cycles(tmp_path: Path):
    vm_root = tmp_path / "vm"
    vm_root.mkdir(parents=True, exist_ok=True)
    (vm_root / "a.vm").write_text(
        '\n'.join(
            [
                '"a" module',
                '"b.value" import',
                '[ value ] "route" define',
                '"route" export',
            ]
        ),
        encoding="utf-8",
    )
    (vm_root / "b.vm").write_text(
        '\n'.join(
            [
                '"b" module',
                '"a.route" import',
                '[ route ] "value" define',
                '"value" export',
            ]
        ),
        encoding="utf-8",
    )

    try:
        load_stackvm_program_source(
            vm_source=None,
            vm_entry="a.route",
            vm_module=None,
            vm_modules=["vm/a", "vm/b"],
            vm_module_prefixes={},
            vm_file=None,
            vm_files=[],
            base_dir=tmp_path,
            search_roots=[tmp_path],
        )
    except ValueError as exc:
        assert "import cycle detected" in str(exc)
    else:
        raise AssertionError("Expected module import cycle to fail.")


def test_agent_stack_vm_structured_data_words():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"{items: [alpha, beta], meta: {count: 2, nested: [{name: alpha}, {name: beta}]}}" yaml> '
            'dup "root_mapping" store-set '
            '"root_mapping" store-get "items" dict-get dup len "item_count" store-set '
            '"root_mapping" store-get "items" dict-get 1 list-get "second_item" store-set '
            '"root_mapping" store-get "items" dict-get 9 list-get? "missing_item" store-set '
            '"root_mapping" store-get "missing" dict-get? "missing_key" store-set '
            '"root_mapping" store-get 123 get-in? "invalid_path" store-set '
            '"root_mapping" store-get "items" dict-get 0 "updated-alpha" list-set "updated_items" store-set '
            '"root_mapping" store-get "done" "meta.flags.0.status" set-in? "safe_updated_mapping" store-set '
            '"safe_updated_mapping" store-get "meta.flags.0.status" get-in? "safe_status" store-set '
            '"root_mapping" store-get "nope" 123 set-in? "invalid_safe_set" store-set '
            '"ok" "results.summary.status" shared!? "safe_shared_set" store-set '
            '"bad" 123 shared!? "invalid_shared_set" store-set '
            '"updated_items" store-get "gamma" list-append "items_after" store-set '
            '"items_after" store-get len 3 = "has_three" store-set '
            '"root_mapping" store-get "meta.count" get-in "count_value" store-set '
            '"root_mapping" store-get "meta.nested.1.name" get-in "second_name" store-set '
            '"root_mapping" store-get "delta" "meta.nested.2.name" set-in "updated_mapping" store-set '
            '"updated_mapping" store-get "meta.nested.2.name" get-in "third_name" store-set '
            '"{success: true, text: ok}" yaml> success? "is_success" store-set '
            '"{success: false, error: nope}" yaml> failure? "is_failure" store-set '
            '2 3 + "sum_value" store-set '
            '10 4 - "difference_value" store-set '
            '3 4 * "product_value" store-set '
            '8 2 / "quotient_value" store-set '
            '5 3 > "greater_check" store-set '
            '"updated" "results.reviews.0.status" shared! '
            '"results.reviews.0.status" shared@ "shared_status" store-set'
        )
    )

    assert vm.store["item_count"] == 2
    assert vm.store["second_item"] == "beta"
    assert vm.store["missing_item"] is None
    assert vm.store["missing_key"] is None
    assert vm.store["invalid_path"] is None
    assert vm.store["safe_status"] == "done"
    assert vm.store["invalid_safe_set"] is None
    assert isinstance(vm.store["safe_shared_set"], dict)
    assert vm.store["invalid_shared_set"] is None
    assert vm.store["updated_items"] == ["updated-alpha", "beta", "gamma"]
    assert vm.store["items_after"] == ["updated-alpha", "beta", "gamma"]
    assert vm.store["has_three"] is True
    assert vm.store["count_value"] == 2
    assert vm.store["second_name"] == "beta"
    assert vm.store["third_name"] == "delta"
    assert vm.store["is_success"] is True
    assert vm.store["is_failure"] is True
    assert vm.store["sum_value"] == 5
    assert vm.store["difference_value"] == 6
    assert vm.store["product_value"] == 12
    assert vm.store["quotient_value"] == 4
    assert vm.store["greater_check"] is True
    assert vm.store["shared_status"] == "updated"


def test_agent_stack_vm_stack_guard_words_are_non_destructive():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            'stack-depth "depth_empty" store-set '
            'stack-empty? "empty_before" store-set '
            'can-pop? "can_pop_empty" store-set '
            'can-dup? "can_dup_empty" store-set '
            'can-swap? "can_swap_empty" store-set '
            'can-over? "can_over_empty" store-set '
            '1 '
            'stack-depth "depth_one" store-set '
            'stack-empty? "empty_one" store-set '
            'can-pop? "can_pop_one" store-set '
            'can-dup? "can_dup_one" store-set '
            'can-swap? "can_swap_one" store-set '
            'can-over? "can_over_one" store-set '
            '2 '
            'stack-depth "depth_two" store-set '
            'stack-empty? "empty_two" store-set '
            'can-pop? "can_pop_two" store-set '
            'can-dup? "can_dup_two" store-set '
            'can-swap? "can_swap_two" store-set '
            'can-over? "can_over_two" store-set '
            'stack-depth "depth_final" store-set'
        )
    )

    assert vm.store["depth_empty"] == 0
    assert vm.store["empty_before"] is True
    assert vm.store["can_pop_empty"] is False
    assert vm.store["can_dup_empty"] is False
    assert vm.store["can_swap_empty"] is False
    assert vm.store["can_over_empty"] is False
    assert vm.store["depth_one"] == 1
    assert vm.store["empty_one"] is False
    assert vm.store["can_pop_one"] is True
    assert vm.store["can_dup_one"] is True
    assert vm.store["can_swap_one"] is False
    assert vm.store["can_over_one"] is False
    assert vm.store["depth_two"] == 2
    assert vm.store["empty_two"] is False
    assert vm.store["can_pop_two"] is True
    assert vm.store["can_dup_two"] is True
    assert vm.store["can_swap_two"] is True
    assert vm.store["can_over_two"] is True
    assert vm.store["depth_final"] == 2
    assert vm.stack == [1, 2]


def test_agent_stack_vm_conversion_words():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"42" int> "int_value" store-set '
            '"3.5" float> "float_value" store-set '
            '"yes" bool> "bool_true" store-set '
            '"0" bool> "bool_false" store-set '
            '123 str> dup "string_value" store-set '
            'none? "none_check_after_str" store-set'
        )
    )

    assert vm.store["int_value"] == 42
    assert vm.store["float_value"] == 3.5
    assert vm.store["bool_true"] is True
    assert vm.store["bool_false"] is False
    assert vm.store["string_value"] == "123"
    assert vm.store["none_check_after_str"] is False


def test_agent_stack_vm_join_word_formats_list_values():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"[git, search, context]" yaml> dup ", " join "joined_values" store-set "raw_values" store-set'
        )
    )

    assert vm.store["joined_values"] == "git, search, context"
    assert vm.store["raw_values"] == ["git", "search", "context"]


def test_agent_stack_vm_yaml_dump_word_serializes_structures():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"{route: approve}" yaml> "note" "approved by delegate" dict-set yaml< "yaml_mapping" store-set '
            '"[git, search]" yaml> yaml< "yaml_list" store-set '
            '"true" yaml> yaml< "yaml_bool" store-set'
        )
    )

    assert vm.store["yaml_mapping"] == "{route: approve, note: approved by delegate}"
    assert vm.store["yaml_list"] == "[git, search]"
    assert vm.store["yaml_bool"] == "true"


def test_agent_stack_vm_immutable_collection_words():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"[1, 2, 3, 4]" yaml> [ 10 * ] map "mapped_values" store-set '
            '"[[1, 2], [3], []]" yaml> [ ] flat-map "flat_mapped_values" store-set '
            '"[1, 2, 3, 4]" yaml> [ 2 > ] filter "filtered_values" store-set '
            '"[1, 2, 3, 4]" yaml> [ 2 > ] find "found_value" store-set '
            '"[1, 2, 3, 4]" yaml> [ 3 > ] any? "has_large_value" store-set '
            '"[1, 2, 3, 4]" yaml> [ 0 > ] all? "all_positive" store-set '
            '"[{name: gamma, score: 3}, {name: alpha, score: 1}, {name: beta, score: 2}]" yaml> [ "score" dict-get ] sort-by "sorted_items" store-set '
            '"[{kind: a, value: 1}, {kind: b, value: 2}, {kind: a, value: 3}]" yaml> [ "kind" dict-get ] group-by "grouped_items" store-set '
            '"{left: 1, shared: old}" yaml> "{right: 2, shared: new}" yaml> merge "merged_mapping" store-set'
        )
    )

    assert vm.store["mapped_values"] == [10, 20, 30, 40]
    assert vm.store["flat_mapped_values"] == [1, 2, 3]
    assert vm.store["filtered_values"] == [3, 4]
    assert vm.store["found_value"] == 3
    assert vm.store["has_large_value"] is True
    assert vm.store["all_positive"] is True
    assert [item["name"] for item in vm.store["sorted_items"]] == ["alpha", "beta", "gamma"]
    assert vm.store["grouped_items"] == {
        "a": [{"kind": "a", "value": 1}, {"kind": "a", "value": 3}],
        "b": [{"kind": "b", "value": 2}],
    }
    assert vm.store["merged_mapping"] == {"left": 1, "shared": "new", "right": 2}


def test_agent_stack_vm_map_and_filter_replay_user_defined_words():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '[ 10 + ] "add-ten" define '
            '[ 2 > ] "greater-than-two" define '
            '"[1, 2, 3]" yaml> [ add-ten ] map "mapped_values" store-set '
            '"[1, 2, 3]" yaml> [ greater-than-two ] filter "filtered_values" store-set'
        )
    )

    assert vm.store["mapped_values"] == [11, 12, 13]
    assert vm.store["filtered_values"] == [3]


def test_agent_stack_vm_data_collection_words_reject_transition_words():
    vm = AgentStackVM(shared_store={})
    vm.register_host_words(
        host_context=StackVmHostContext(
            agent_name="vm-test",
            llm_router=None,
            tool_runtime=None,
            llm_profile=None,
            system_prompt="",
            tool_definitions=[],
        ),
        result=StackVmExecutionResult(),
    )

    with pytest.raises(StackVmIllegalChildEffectError, match="map child quotations cannot finalize answers"):
        asyncio.run(vm.eval('"[1]" yaml> [ "nope" answer ] map'))

    with pytest.raises(StackVmIllegalChildEffectError, match="flat-map child quotations cannot finalize answers"):
        asyncio.run(vm.eval('"[[1]]" yaml> [ "nope" answer ] flat-map'))

    with pytest.raises(StackVmIllegalChildEffectError, match="filter child quotations cannot finalize answers"):
        asyncio.run(vm.eval('"[1]" yaml> [ "nope" answer ] filter'))

    with pytest.raises(StackVmIllegalChildEffectError, match="find child quotations cannot finalize answers"):
        asyncio.run(vm.eval('"[1]" yaml> [ "nope" answer ] find'))

    with pytest.raises(StackVmIllegalChildEffectError, match="any\\? child quotations cannot finalize answers"):
        asyncio.run(vm.eval('"[1]" yaml> [ "nope" answer ] any?'))

    with pytest.raises(StackVmIllegalChildEffectError, match="all\\? child quotations cannot finalize answers"):
        asyncio.run(vm.eval('"[1]" yaml> [ "nope" answer ] all?'))

    with pytest.raises(StackVmIllegalChildEffectError, match="sort-by child quotations cannot finalize answers"):
        asyncio.run(vm.eval('"[1]" yaml> [ "nope" answer ] sort-by'))

    with pytest.raises(StackVmIllegalChildEffectError, match="group-by child quotations cannot finalize answers"):
        asyncio.run(vm.eval('"[1]" yaml> [ "nope" answer ] group-by'))


def test_agent_stack_vm_match_supports_literal_and_wildcard_patterns():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"approve" '
            '[ "reject" [ "route.reject" "route" store-set ] _ [ "route.default" "route" store-set ] ] '
            'match'
        )
    )

    assert vm.store["route"] == "route.default"


def test_agent_stack_vm_match_supports_dict_and_list_bindings():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"{kind: approve, payload: {id: 7, tags: [fast, safe]}}" yaml> '
            '[ '
            '  [ "{kind: approve, payload: {id: $approval_id, tags: [$first_tag, $second_tag]}}" yaml> ] '
            '  [ "match.approval_id" shared@ "approval_id" store-set '
            '    "match.first_tag" shared@ "first_tag" store-set '
            '    "match.second_tag" shared@ "second_tag" store-set ] '
            '  _ [ "fallback" "approval_id" store-set ] '
            '] '
            'match'
        )
    )

    assert vm.store["approval_id"] == 7
    assert vm.store["first_tag"] == "fast"
    assert vm.store["second_tag"] == "safe"


def test_agent_stack_vm_match_supports_typed_rest_and_consistent_bindings():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"{kind: route, approval_id: 7, tags: [alpha, beta, gamma], meta: {source: cfg}}" yaml> '
            '[ '
            '  [ "{kind: route, approval_id: $approval_id:int, tags: [$first_tag, $*other_tags], $rest: $remaining}" yaml> ] '
            '  [ "match.approval_id" shared@ "approval_id" store-set '
            '    "match.first_tag" shared@ "first_tag" store-set '
            '    "match.other_tags" shared@ "other_tags" store-set '
            '    "match.remaining" shared@ "remaining" store-set ] '
            '  _ [ "fallback" "approval_id" store-set ] '
            '] '
            'match'
        )
    )

    assert vm.store["approval_id"] == 7
    assert vm.store["first_tag"] == "alpha"
    assert vm.store["other_tags"] == ["beta", "gamma"]
    assert vm.store["remaining"] == {"meta": {"source": "cfg"}}


def test_agent_stack_vm_match_rejects_inconsistent_repeated_bindings():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"[1, 2]" yaml> '
            '[ [ "[1, 1]" yaml> ] [ "literal-match" "result" store-set ] '
            '  [ "[$value, $value]" yaml> ] [ "binding-match" "result" store-set ] '
            '  _ [ "fallback" "result" store-set ] ] '
            'match'
        )
    )

    assert vm.store["result"] == "fallback"


def test_agent_stack_vm_schema_words_validate_and_coerce_values():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            "\"{count: '7', enabled: yes}\" yaml> "
            '"{type: object, required: [count, enabled], properties: {count: {type: integer}, enabled: {type: boolean}, label: {type: string, default: normalized}}}" yaml> '
            'schema-apply dup "applied_schema" store-set '
            '"applied_schema" store-get "success" dict-get "schema_apply_success" store-set '
            '"applied_schema" store-get "value" dict-get "schema_apply_value" store-set '
            '"applied_schema" store-get "errors" dict-get "schema_apply_errors" store-set '
            '"{count: oops}" yaml> '
            '"{type: object, required: [count, enabled], properties: {count: {type: integer}, enabled: {type: boolean}}}" yaml> '
            'schema-check dup "checked_schema" store-set '
            '"checked_schema" store-get "success" dict-get "schema_check_success" store-set '
            '"checked_schema" store-get "errors" dict-get "schema_check_errors" store-set'
        )
    )

    assert vm.store["schema_apply_success"] is True
    assert vm.store["schema_apply_value"] == {"count": 7, "enabled": True, "label": "normalized"}
    assert vm.store["schema_apply_errors"] == []
    assert vm.store["schema_check_success"] is False
    assert any("value.enabled is required." == error for error in vm.store["schema_check_errors"])


def test_agent_stack_vm_active_session_transcript_words(tmp_path: Path):
    session_manager = SessionManager(tmp_path, config={})
    record = session_manager.create_session(
        title="Memory Test",
        state={
            "transcript": [
                {"role": "user", "content": "First question"},
                {"role": "assistant", "content": "First answer"},
                {"role": "user", "content": "Second\nquestion"},
            ]
        },
    )
    vm = AgentStackVM(
        shared_store={
            "_session_manager": session_manager,
            "active_session_id": record.session_id,
        }
    )
    vm.register_host_words(
        host_context=StackVmHostContext(
            agent_name="vm-test",
            llm_router=None,
            tool_runtime=None,
            llm_profile=None,
            system_prompt="",
            tool_definitions=[],
        ),
        result=StackVmExecutionResult(),
    )

    asyncio.run(
        vm.eval(
            '2 active-session-transcript-text "memory_text" store-set '
            'active-session-transcript len "entry_count" store-set'
        )
    )

    assert vm.store["entry_count"] == 3
    assert vm.store["memory_text"] == "Assistant: First answer\nUser: Second question"


def test_agent_stack_vm_join_word_rejects_scalar_values():
    vm = AgentStackVM(shared_store={})

    try:
        asyncio.run(vm.eval('"git" ", " join'))
    except TypeError as exc:
        assert "join expects a list or tuple" in str(exc)
    else:
        raise AssertionError("join should reject scalar values")


def test_agent_stack_vm_switch_executes_matching_branch():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"billing" [ "billing" [ "bill" "route" store-set ] "tech" [ "tech" "route" store-set ] "default" [ "general" "route" store-set ] ] switch'
        )
    )

    assert vm.store["route"] == "bill"


def test_agent_stack_vm_switch_uses_default_when_no_match():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"other" [ "billing" [ "bill" "route" store-set ] "default" [ "general" "route" store-set ] ] switch'
        )
    )

    assert vm.store["route"] == "general"


def test_agent_stack_vm_cond_runs_first_truthy_action():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '[ [ False ] [ "never" "route" store-set ] [ 2 1 > ] [ "greater" "route" store-set ] [ True ] [ "default" "route" store-set ] ] cond'
        )
    )

    assert vm.store["route"] == "greater"


def test_agent_stack_vm_fallback_restores_stack_before_running_fallback():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '1 [ drop missing-word ] [ 2 ] fallback "fallback_result" store-set "remaining" store-set'
        )
    )

    assert vm.store["fallback_result"] == 2
    assert vm.store["remaining"] == 1


def test_agent_stack_vm_host_words_record_last_vm_effect_metadata():
    vm = AgentStackVM(shared_store={})
    result = StackVmExecutionResult()
    vm.register_host_words(
        host_context=StackVmHostContext(
            agent_name="vm-test",
            llm_router=None,
            tool_runtime=None,
            llm_profile=None,
            system_prompt="",
            tool_definitions=[],
        ),
        result=result,
    )

    asyncio.run(vm.eval('"Need confirmation?" ask-user'))

    assert result.transition == "ask_user"
    assert result.effect == {
        "kind": "ask_user",
        "payload": {"question": "Need confirmation?"},
    }
    assert vm.store["last_vm_effect"] == result.effect
    assert vm.store["last_vm_transition"] == "ask_user"
    assert vm.store["vm_effect_history"] == [
        {
            "agent": "vm-test",
            "transition": "ask_user",
            "effect": {
                "kind": "ask_user",
                "payload": {"question": "Need confirmation?"},
            },
        }
    ]


def test_agent_stack_vm_tool_call_pushes_result_and_records_tool_state():
    class _ToolRuntime:
        def execute_tool(self, tool_name, arguments, shared_store, auto_confirm=False, agent_name=None):
            assert tool_name == "demo.echo"
            assert arguments == {"text": "ping"}
            assert agent_name == "vm-test"
            return {"success": True, "text": "pong"}

    vm = AgentStackVM(shared_store={"auto_confirm_tools": True})
    vm.register_host_words(
        host_context=StackVmHostContext(
            agent_name="vm-test",
            llm_router=None,
            tool_runtime=_ToolRuntime(),
            llm_profile=None,
            system_prompt="",
            tool_definitions=[{"name": "demo.echo"}],
        ),
        result=StackVmExecutionResult(),
    )

    asyncio.run(vm.eval('"demo.echo" "{text: ping}" yaml> tool-call dup "tool_result" store-set'))

    assert vm.store["tool_result"] == {"success": True, "text": "pong"}
    assert vm.store["last_tool_result"] == {"success": True, "text": "pong"}
    assert vm.store["last_tool_route"] == {
        "tool": "demo.echo",
        "arguments": {"text": "ping"},
        "result": {"success": True, "text": "pong"},
    }
    assert vm.stack == [{"success": True, "text": "pong"}]


def test_agent_stack_vm_llm_call_pushes_response_and_tracks_usage():
    class _Router:
        default_profile_name = "default"

        def generate(self, *, profile_name, prompt):
            assert profile_name == "default"
            assert prompt == "System context\n\nSay hi"
            return "hello from llm"

        def get_last_generation_info(self):
            return {
                "model": "gpt-test",
                "profile_name": "default",
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
                "estimated_cost_usd": 0.01,
            }

    vm = AgentStackVM(shared_store={})
    vm.register_host_words(
        host_context=StackVmHostContext(
            agent_name="vm-test",
            llm_router=_Router(),
            tool_runtime=None,
            llm_profile=None,
            system_prompt="System context",
            tool_definitions=[],
        ),
        result=StackVmExecutionResult(),
    )

    asyncio.run(vm.eval('"Say hi" llm-call dup "reply" store-set'))

    assert vm.store["reply"] == "hello from llm"
    assert vm.store["last_llm_profile"] == "default"
    assert vm.store["llm_usage_totals"] == {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}
    assert vm.store["llm_cost_usd_total"] == 0.01
    assert vm.stack == ["hello from llm"]


def test_agent_stack_vm_fallback_does_not_swallow_illegal_child_effect_errors():
    vm = AgentStackVM(shared_store={})
    result = StackVmExecutionResult()
    vm.register_host_words(
        host_context=StackVmHostContext(
            agent_name="vm-test",
            llm_router=None,
            tool_runtime=None,
            llm_profile=None,
            system_prompt="",
            tool_definitions=[],
        ),
        result=result,
    )

    try:
        asyncio.run(vm.eval('"[1]" yaml> [ [ "nope" answer ] parallel-map ] [ "recovered" answer ] fallback'))
    except StackVmIllegalChildEffectError as exc:
        assert "parallel-map child quotations cannot finalize answers" in str(exc)
    else:
        raise AssertionError("fallback should not swallow illegal child effect errors")


def test_agent_stack_vm_parallel_map_returns_result_list():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"[1, 2, 3]" yaml> [ 2 * ] parallel-map "mapped" store-set'
        )
    )

    assert vm.store["mapped"] == [2, 4, 6]


def test_agent_stack_vm_parallel_map_replays_user_defined_words():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '[ 10 + ] "add-ten" define "[1, 2, 3]" yaml> [ add-ten ] parallel-map "mapped" store-set'
        )
    )

    assert vm.store["mapped"] == [11, 12, 13]


def test_agent_stack_vm_parallel_map_child_store_mutations_do_not_leak():
    vm = AgentStackVM(shared_store={"normalized": {"count": 0}})

    asyncio.run(
        vm.eval(
            '"[1, 2]" yaml> [ "mutated" "normalized.state" shared! "normalized.count" shared@ 1 + ] '
            'parallel-map "mapped" store-set'
        )
    )

    assert vm.store["mapped"] == [1, 1]
    assert vm.store["normalized"] == {"count": 0}


def test_agent_stack_vm_parallel_map_rejects_transition_words():
    shared_store = {}
    vm = AgentStackVM(shared_store=shared_store)
    vm.register_host_words(
        host_context=StackVmHostContext(
            agent_name="vm-test",
            llm_router=None,
            tool_runtime=None,
            llm_profile=None,
            system_prompt="",
            tool_definitions=[],
        ),
        result=StackVmExecutionResult(),
    )

    try:
        asyncio.run(vm.eval('"[1]" yaml> [ "nope" answer ] parallel-map'))
    except RuntimeError as exc:
        assert "parallel-map child quotations cannot finalize answers" in str(exc)
    else:
        raise AssertionError("parallel-map should reject child answer transitions")


def test_agent_stack_vm_reduce_accumulates_values_with_seed():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"[1, 2, 3, 4]" yaml> 0 [ + ] reduce "total" store-set'
        )
    )

    assert vm.store["total"] == 10


def test_agent_stack_vm_reduce_replays_user_defined_words():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '[ swap + ] "sum-pair" define "[1, 2, 3]" yaml> 10 [ sum-pair ] reduce "total" store-set'
        )
    )

    assert vm.store["total"] == 16


def test_agent_stack_vm_reduce_rejects_transition_words():
    shared_store = {}
    vm = AgentStackVM(shared_store=shared_store)
    vm.register_host_words(
        host_context=StackVmHostContext(
            agent_name="vm-test",
            llm_router=None,
            tool_runtime=None,
            llm_profile=None,
            system_prompt="",
            tool_definitions=[],
        ),
        result=StackVmExecutionResult(),
    )

    try:
        asyncio.run(vm.eval('"[1]" yaml> 0 [ "nope" answer ] reduce'))
    except RuntimeError as exc:
        assert "reduce child quotations cannot finalize answers" in str(exc)
    else:
        raise AssertionError("reduce should reject child answer transitions")


def test_agent_stack_vm_bool_conversion_rejects_ambiguous_strings():
    vm = AgentStackVM(shared_store={})

    try:
        asyncio.run(vm.eval('"maybe" bool>'))
    except ValueError as exc:
        assert "bool> cannot coerce string value" in str(exc)
    else:
        raise AssertionError("bool> should reject ambiguous string values")


def test_agent_stack_vm_safe_collection_words_return_none_for_invalid_access():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"not-a-dict" "key" dict-get? "safe_dict_from_scalar" store-set '
            '"not-a-list" 0 list-get? "safe_list_from_scalar" store-set '
            '"[alpha]" yaml> 2 list-get? "safe_list_oob" store-set'
        )
    )

    assert vm.store["safe_dict_from_scalar"] is None
    assert vm.store["safe_list_from_scalar"] is None
    assert vm.store["safe_list_oob"] is None


def test_agent_stack_vm_safe_nested_update_returns_none_for_invalid_container():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"not-a-container" "value" "meta.status" set-in? "safe_set_scalar" store-set '
            '"{}" yaml> "ok" "meta.status" set-in? "safe_set_mapping" store-set'
        )
    )

    assert vm.store["safe_set_scalar"] is None
    assert vm.store["safe_set_mapping"] == {"meta": {"status": "ok"}}


def test_agent_stack_vm_safe_shared_update_returns_none_for_invalid_path():
    vm = AgentStackVM(shared_store={})

    asyncio.run(
        vm.eval(
            '"ok" "results.summary.status" shared!? "shared_ok" store-set '
            '"bad" 123 shared!? "shared_bad" store-set'
        )
    )

    assert isinstance(vm.store["shared_ok"], dict)
    assert vm.store["results"]["summary"]["status"] == "ok"
    assert vm.store["shared_bad"] is None


def test_agent_stack_vm_prompt_user_word_continues_with_response():
    shared_store = {
        "interaction_handler": lambda request: {
            "kind": request.get("kind", "text"),
            "value": "yes",
            "raw_input": "yes",
        }
    }
    vm = AgentStackVM(shared_store=shared_store)
    vm.register_host_words(
        host_context=StackVmHostContext(
            agent_name="vm-test",
            llm_router=None,
            tool_runtime=None,
            llm_profile=None,
            system_prompt="",
            tool_definitions=[],
        ),
        result=StackVmExecutionResult(),
    )

    asyncio.run(vm.eval('"Proceed?" prompt-user dup "reply" store-set'))

    assert vm.store["last_user_prompt"] == "Proceed?"
    assert vm.store["last_user_input"] == "yes"
    assert vm.store["last_user_value"] == "yes"
    assert vm.store["last_user_interaction"]["value"] == "yes"
    assert vm.store["reply"] == "yes"
    assert vm.stack == ["yes"]


def test_agent_stack_vm_prompt_interaction_word_pushes_selected_value():
    shared_store = {
        "interaction_handler": lambda request: {
            "kind": request.get("kind", "buttons"),
            "value": "delegate",
            "values": ["delegate"],
            "label": "Delegate",
            "selected_options": [{"id": "delegate", "label": "Delegate", "value": "delegate"}],
            "raw_input": "delegate",
        }
    }
    vm = AgentStackVM(shared_store=shared_store)
    vm.register_host_words(
        host_context=StackVmHostContext(
            agent_name="vm-test",
            llm_router=None,
            tool_runtime=None,
            llm_profile=None,
            system_prompt="",
            tool_definitions=[],
        ),
        result=StackVmExecutionResult(),
    )

    asyncio.run(
        vm.eval(
            '"{kind: buttons, prompt: Choose action, options: [{id: approve, label: Approve, value: approve}, {id: delegate, label: Delegate, value: delegate}]}" '
            'prompt-interaction dup "selection" store-set'
        )
    )

    assert vm.store["last_user_prompt"] == "Choose action"
    assert vm.store["last_user_request"]["kind"] == "buttons"
    assert vm.store["last_user_value"] == "delegate"
    assert vm.store["selection"] == "delegate"
    assert vm.stack == ["delegate"]


def test_agent_stack_vm_prompt_interaction_word_pushes_checklist_values():
    shared_store = {
        "interaction_handler": lambda request: {
            "kind": request.get("kind", "checklist"),
            "value": ["git", "search"],
            "values": ["git", "search"],
            "selected_options": [
                {"id": "git", "label": "Git", "value": "git"},
                {"id": "search", "label": "Search", "value": "search"},
            ],
            "raw_input": "git,search",
        }
    }
    vm = AgentStackVM(shared_store=shared_store)
    vm.register_host_words(
        host_context=StackVmHostContext(
            agent_name="vm-test",
            llm_router=None,
            tool_runtime=None,
            llm_profile=None,
            system_prompt="",
            tool_definitions=[],
        ),
        result=StackVmExecutionResult(),
    )

    asyncio.run(
        vm.eval(
            '"{kind: checklist, prompt: Pick tools, options: [{id: git, label: Git, value: git}, {id: search, label: Search, value: search}]}" '
            'prompt-interaction dup "selected" store-set len "selected_count" store-set'
        )
    )

    assert vm.store["last_user_value"] == ["git", "search"]
    assert vm.store["selected"] == ["git", "search"]
    assert vm.store["selected_count"] == 2
    assert vm.stack == []
