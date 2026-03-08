from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


TYPED_REFERENCE_PREFIXES = frozenset({"agent", "flow", "prompt", "tool"})


@dataclass(frozen=True)
class ResourceReference:
    raw: str
    target: str
    kind: str | None = None
    container: str | None = None
    name: str = ""

    @property
    def is_qualified(self) -> bool:
        return self.container is not None

    def as_registry_key(self) -> str:
        return self.target

    def as_typed(self, kind: str | None = None) -> str:
        typed_kind = (kind or self.kind or "").strip().lower()
        if not typed_kind:
            return self.target
        return f"{typed_kind}:{self.target}"


def typed_reference_kind(ref: str) -> str | None:
    cleaned = str(ref or "").strip()
    prefix, separator, _remainder = cleaned.partition(":")
    if separator and prefix.strip().lower() in TYPED_REFERENCE_PREFIXES:
        return prefix.strip().lower()
    return None


def parse_reference(
    ref: str,
    *,
    allowed_kinds: Iterable[str] | None = None,
) -> ResourceReference:
    cleaned = str(ref or "").strip()
    if not cleaned:
        return ResourceReference(raw=str(ref or ""), target="")

    kind = typed_reference_kind(cleaned)
    target = cleaned
    if kind is not None:
        allowed = {value.strip().lower() for value in allowed_kinds} if allowed_kinds is not None else None
        if allowed is not None and kind not in allowed:
            allowed_display = ", ".join(sorted(allowed))
            raise ValueError(f"Typed reference kind '{kind}:' is not allowed here; expected one of: {allowed_display}.")
        target = cleaned.split(":", 1)[1].strip()
        if not target:
            raise ValueError(f"Typed reference '{kind}:' is missing a target.")

    target = target.replace("::", ".")
    if "#" in target:
        container, name = target.split("#", 1)
        container = container.strip()
        name = name.strip()
        if not container or not name:
            raise ValueError(f"Reference '{ref}' must specify both container and resource name around '#'.")
        target = f"{container}.{name}"

    container = None
    name = target
    if "." in target:
        container, name = target.rsplit(".", 1)
        container = container.strip() or None
        name = name.strip()

    return ResourceReference(
        raw=cleaned,
        target=target,
        kind=kind,
        container=container,
        name=name,
    )


def parse_prompt_reference(prompt_ref: str) -> ResourceReference:
    reference = parse_reference(prompt_ref, allowed_kinds={"prompt"})
    if reference.kind != "prompt":
        raise ValueError(f"Prompt reference '{prompt_ref}' must start with 'prompt:'.")
    return reference


def normalize_registry_reference(ref: str, *, allowed_kinds: Iterable[str] | None = None) -> str:
    return parse_reference(ref, allowed_kinds=allowed_kinds).as_registry_key()


def normalize_registry_reference_compat(ref: str, *, allowed_kinds: Iterable[str] | None = None) -> str:
    cleaned = str(ref or "").strip()
    if not cleaned:
        return ""
    try:
        return normalize_registry_reference(cleaned, allowed_kinds=allowed_kinds)
    except ValueError:
        return cleaned.replace("::", ".")


def normalize_prompt_reference(prompt_ref: str) -> str:
    return parse_prompt_reference(prompt_ref).as_registry_key()


def normalize_prompt_source(ref: str) -> str:
    cleaned = str(ref or "").strip()
    if not cleaned:
        return ""

    kind = typed_reference_kind(cleaned)
    if kind is None:
        return cleaned

    return parse_prompt_reference(cleaned).as_typed()


def validate_registry_reference(ref: str, *, allowed_kinds: Iterable[str], field_name: str) -> None:
    cleaned = str(ref or "").strip()
    if not cleaned:
        raise ValueError(f"Field '{field_name}' cannot be empty.")
    try:
        normalize_registry_reference(cleaned, allowed_kinds=allowed_kinds)
    except ValueError as exc:
        raise ValueError(f"Invalid value for '{field_name}': {exc}") from exc


def validate_prompt_source(ref: str, *, field_name: str) -> None:
    cleaned = str(ref or "").strip()
    if not cleaned:
        raise ValueError(f"Field '{field_name}' cannot be empty.")

    kind = typed_reference_kind(cleaned)
    if kind is None:
        return
    if kind != "prompt":
        raise ValueError(
            f"Invalid value for '{field_name}': typed reference kind '{kind}:' is not allowed for prompt sources."
        )
    parse_prompt_reference(cleaned)