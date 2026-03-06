from __future__ import annotations

from typing import Any, Callable

from pocketcode.core.user_interaction import InteractionOption, normalize_interaction_request


def describe_interaction_request(raw_request: dict[str, Any]) -> str:
    request = normalize_interaction_request(raw_request)
    lines = [request.prompt]
    if request.description:
        lines.append(request.description)

    if request.options:
        lines.append("Select all that apply:" if request.kind == "checklist" else "Choose one:")
        defaults = _coerce_default_tokens(request.default)
        for index, option in enumerate(request.options, start=1):
            suffix = ""
            if option.id in defaults or str(option.value) in defaults:
                suffix = " [default]"
            detail = f" - {option.description}" if option.description else ""
            lines.append(f"  {index}. {option.label}{suffix}{detail}")

    if request.kind == "checklist":
        lines.append("Enter comma-separated numbers or ids.")
    elif request.kind in {"buttons", "radio"}:
        lines.append("Enter a number, id, or option label.")

    return "\n".join(lines)


def interaction_placeholder(raw_request: dict[str, Any]) -> str:
    request = normalize_interaction_request(raw_request)
    if request.placeholder:
        return request.placeholder
    if request.kind == "text":
        return request.prompt
    if request.kind == "checklist":
        return f"{request.prompt} (comma-separated choices)"
    return f"{request.prompt} (choose one option)"


def parse_interaction_response(raw_request: dict[str, Any], raw_text: str) -> dict[str, Any]:
    request = normalize_interaction_request(raw_request)
    text = raw_text.strip()

    if request.kind == "text":
        if text:
            return {"kind": request.kind, "value": text, "raw_input": raw_text}
        if request.default not in {None, ""}:
            return {"kind": request.kind, "value": request.default, "raw_input": raw_text}
        if request.allow_empty:
            return {"kind": request.kind, "value": "", "raw_input": raw_text}
        raise ValueError("Input cannot be empty.")

    if request.kind in {"buttons", "radio"}:
        token = text or _default_token(request.default)
        if not token:
            raise ValueError("Please choose one of the available options.")
        option = _resolve_single_option(request.options, token)
        return {
            "kind": request.kind,
            "value": option.value,
            "values": [option.value],
            "label": option.label,
            "selected_options": [option.as_dict()],
            "raw_input": raw_text,
        }

    tokens = [segment.strip() for segment in text.split(",") if segment.strip()]
    if not tokens:
        tokens = _coerce_default_tokens(request.default)
    if not tokens:
        if request.min_selected and request.min_selected > 0:
            raise ValueError(f"Please choose at least {request.min_selected} option(s).")
        return {
            "kind": request.kind,
            "value": [],
            "values": [],
            "selected_options": [],
            "raw_input": raw_text,
        }

    selected: list[InteractionOption] = []
    seen_ids: set[str] = set()
    for token in tokens:
        option = _resolve_single_option(request.options, token)
        if option.id in seen_ids:
            continue
        seen_ids.add(option.id)
        selected.append(option)

    if request.min_selected is not None and len(selected) < request.min_selected:
        raise ValueError(f"Please choose at least {request.min_selected} option(s).")
    if request.max_selected is not None and len(selected) > request.max_selected:
        raise ValueError(f"Please choose at most {request.max_selected} option(s).")

    return {
        "kind": request.kind,
        "value": [option.value for option in selected],
        "values": [option.value for option in selected],
        "labels": [option.label for option in selected],
        "selected_options": [option.as_dict() for option in selected],
        "raw_input": raw_text,
    }


def request_interaction_from_console(
    raw_request: dict[str, Any],
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> dict[str, Any]:
    request = normalize_interaction_request(raw_request)

    if request.kind != "text":
        output_func(describe_interaction_request(request.as_dict()))

    while True:
        response_text = input_func(_input_prompt(request.as_dict()))
        try:
            return parse_interaction_response(request.as_dict(), response_text)
        except ValueError as exc:
            output_func(str(exc))


def _input_prompt(raw_request: dict[str, Any]) -> str:
    request = normalize_interaction_request(raw_request)
    default = request.default
    if request.kind == "text":
        suffix = f" [{default}]" if default not in {None, ""} else ""
        return f"{request.prompt}{suffix}: "
    if request.kind == "checklist":
        return "Choices: "
    return "Choice: "


def _resolve_single_option(options: tuple[InteractionOption, ...], token: str) -> InteractionOption:
    normalized = token.strip().lower()
    if not normalized:
        raise ValueError("Please choose one of the available options.")

    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(options):
            return options[index]

    for option in options:
        if option.id.lower() == normalized:
            return option
        if str(option.value).strip().lower() == normalized:
            return option
        if option.label.strip().lower() == normalized:
            return option

    raise ValueError(f"Unknown option: {token}")


def _default_token(default: Any) -> str:
    tokens = _coerce_default_tokens(default)
    return tokens[0] if tokens else ""


def _coerce_default_tokens(default: Any) -> list[str]:
    if default is None:
        return []
    if isinstance(default, (list, tuple, set)):
        return [str(item).strip() for item in default if str(item).strip()]
    text = str(default).strip()
    return [text] if text else []