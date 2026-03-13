from __future__ import annotations

import asyncio
from pathlib import Path

from pocketcode.core.agent_stack_vm import (
    AgentStackVM,
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
        vm_file=None,
        vm_files=[],
        base_dir=tmp_path,
        search_roots=[tmp_path],
    )

    assert '[ "resolved" answer ] "route" define' in source
    assert str(vm_root / "router.vm") in source_files


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
