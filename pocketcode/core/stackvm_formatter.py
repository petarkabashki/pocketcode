from __future__ import annotations

import json
from typing import Any

import yaml
from pocketcode.core.stackvm_parser import parse_stackvm_source, serialize_stackvm_ast


def format_stackvm_source(source: str, max_width: int = 80) -> str:
    """Parses and formats StackVM source code."""
    if not source.strip():
        return ""
    ast = parse_stackvm_source(source)
    return format_stackvm_ast(ast, max_width=max_width)


def format_stackvm_ast(ast: list[Any], indent: int = 0, max_width: int = 80) -> str:
    """Converts a StackVM AST into a formatted source string."""
    lines: list[str] = []
    current_line: list[str] = []
    
    base_indent = "  " * indent
    i = 0
    while i < len(ast):
        node = ast[i]
        # Peek for YAML suffix pattern: ("str", val) followed by ("sym", "yaml>")
        next_node = ast[i + 1] if i + 1 < len(ast) else None

        if (isinstance(node, tuple) and node[0] == "str" and 
            isinstance(next_node, tuple) and next_node[0] == "sym" and str(next_node[1]) == "yaml>"):
            if current_line:
                lines.append(base_indent + " ".join(current_line))
                current_line = []
            lines.append(_format_yaml_block(node[1], indent))
            i += 2
            continue

        is_multiline_block = False
        if isinstance(node, list):
            is_multiline_block = _should_format_multiline(node)
        elif isinstance(node, tuple) and node[0] == "sig":
            is_multiline_block = _should_format_multiline_sig(node[1])
            
        node_str = _format_node(node, indent, max_width)
        
        if is_multiline_block or (current_line and len(" ".join(current_line) + " " + node_str) > max_width):
            if current_line:
                lines.append(base_indent + " ".join(current_line))
                current_line = []
            
            if is_multiline_block:
                if isinstance(node, list):
                    lines.append(_format_multiline_quotation(node, indent, max_width))
                else:
                    lines.append(_format_multiline_signature(node, indent, max_width))
            else:
                current_line.append(node_str)
        else:
            current_line.append(node_str)
        i += 1

    if current_line:
        lines.append(base_indent + " ".join(current_line))

    return "\n".join(lines).strip()


def _format_yaml_block(val: Any, indent: int) -> str:
    """Formats a string as a multi-line YAML literal followed by yaml>."""
    base_indent = "  " * indent
    try:
        # Try to parse the string content as YAML to see if it's a collection
        data = yaml.safe_load(str(val))
    except Exception:
        data = val

    if not isinstance(data, (dict, list)):
        return f'{base_indent}{json.dumps(str(val))} yaml>'

    inner_indent = "  " * (indent + 1)
    # Use default_flow_style=False to get readable multi-line YAML
    yaml_text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False).strip()
    
    if "\n" not in yaml_text and len(yaml_text) < 40:
        return f'{base_indent}"{yaml_text}" yaml>'
        
    indented_yaml = "\n".join(inner_indent + line for line in yaml_text.splitlines())
    
    # Use braces for mappings to be explicit, otherwise just indented block
    content = f'"{{\n{indented_yaml}\n{base_indent}}}"' if isinstance(data, dict) else f'"\n{indented_yaml}\n{base_indent}"'
    return f"{base_indent}{content} yaml>"


def _format_node(node: Any, indent: int, max_width: int) -> str:
    if isinstance(node, list):
        return f"[ { ' '.join(_format_node(n, indent, max_width) for n in node) } ]"
    
    if isinstance(node, tuple) and len(node) == 2:
        token_type, token_value = node
        if token_type == "sig":
            return f"( {' '.join(_format_node(item, indent, max_width) for item in token_value)} )"
        if token_type == "str":
            return json.dumps(str(token_value))
        if token_type == "bool":
            return "True" if token_value else "False"
        if token_type == "none":
            return "None"
        return str(token_value)
    
    return str(node)


def _should_format_multiline(quotation: list[Any]) -> bool:
    """Returns True if the quotation contains structural keywords or is long."""
    keywords = {
        "if",
        "match",
        "switch",
        "cond",
        "while",
        "parallel-map",
        "define",
        "defmacro",
        "yaml>",
        "yaml<",
    }
    
    if len(quotation) > 5:
        return True
        
    for node in quotation:
        if isinstance(node, list):
            return True
        if isinstance(node, tuple) and node[0] == "sig":
            return True
        if isinstance(node, tuple) and node[0] == "sym" and str(node[1]) in keywords:
            return True
            
    return False


def _should_format_multiline_sig(tokens: list[Any]) -> bool:
    """Returns True if the signature has many tokens."""
    return len(tokens) > 8


def _format_multiline_quotation(quotation: list[Any], indent: int, max_width: int) -> str:
    """Formats a quotation as a multi-line block with indentation."""
    base_indent = "  " * indent
    inner_indent = indent + 1
    
    # Special case: very short quotations might still look better inline
    flat = _format_node(quotation, indent, max_width)
    if len(flat) < 40 and not any(isinstance(n, list) for n in quotation):
        return base_indent + flat

    inner_content = format_stackvm_ast(quotation, indent=inner_indent, max_width=max_width)
    
    return (
        f"{base_indent}[\n"
        f"{inner_content}\n"
        f"{base_indent}]"
    )


def _format_multiline_signature(node: tuple[str, list[Any]], indent: int, max_width: int) -> str:
    """Formats a signature block as a multi-line block with indentation."""
    base_indent = "  " * indent
    inner_indent = indent + 1
    tokens = node[1]
    
    # Short signatures look better inline
    flat = _format_node(node, indent, max_width)
    if len(flat) < 40:
        return base_indent + flat

    inner_content = format_stackvm_ast(tokens, indent=inner_indent, max_width=max_width)
    return (
        f"{base_indent}(\n"
        f"{inner_content}\n"
        f"{base_indent})"
    )