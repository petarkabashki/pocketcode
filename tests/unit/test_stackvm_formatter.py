from __future__ import annotations

from pocketcode.core.stackvm_formatter import format_stackvm_source
from pocketcode.core.stackvm_parser import parse_stackvm_source


def test_format_stackvm_source_normalizes_spacing():
    source = ' "hello"   [ 1 2 + ]   answer '
    formatted = format_stackvm_source(source)
    assert formatted == '"hello" [ 1 2 + ] answer'


def test_format_stackvm_source_breaks_long_quotations():
    source = '[ "a" "b" "c" "d" "e" "f" "g" ]'
    formatted = format_stackvm_source(source)
    assert "[\n" in formatted
    assert "  \"a\" \"b\"" in formatted


def test_format_stackvm_source_handles_nested_ifs():
    source = 'condition [ True [ "yes" ] [ "no" ] if ] when'
    formatted = format_stackvm_source(source)
    assert "  [" in formatted  # Check indentation

def test_format_is_idempotent():
    source = '[ 1 2 + ] ( int -- int ) "add" define'
    formatted = format_stackvm_source(source)
    assert format_stackvm_source(formatted) == formatted


def test_format_stackvm_source_handles_multiline_yaml():
    source = '"{kind: buttons, prompt: Choose, options: [{id: approve, label: Approve, value: approve}]}" yaml> answer'
    formatted = format_stackvm_source(source)
    assert 'kind: buttons' in formatted
    assert 'yaml>' in formatted
    assert '"\n  kind: buttons' in formatted


def test_format_stackvm_source_handles_yaml_dump_consistency():
    # yaml< should be treated as a keyword, triggering multiline if the quotation is substantial
    source = '[ my-dict "key" "val" dict-set yaml< answer ]'
    formatted = format_stackvm_source(source)
    assert "[\n" in formatted
    assert "  yaml<" in formatted