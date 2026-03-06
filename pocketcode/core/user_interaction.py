from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

VALID_INTERACTION_KINDS = {"text", "buttons", "radio", "checklist"}


def _slugify_label(label: str, index: int) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in label.strip())
    text = "-".join(part for part in text.split("-") if part)
    return text or f"option-{index + 1}"


@dataclass(frozen=True)
class InteractionOption:
    id: str
    label: str
    value: Any = None
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "value": self.value,
            "description": self.description,
        }

    @classmethod
    def from_raw(cls, raw: Any, index: int) -> "InteractionOption":
        if isinstance(raw, cls):
            return raw

        if isinstance(raw, str):
            label = raw.strip() or f"Option {index + 1}"
            return cls(
                id=_slugify_label(label, index),
                label=label,
                value=raw,
            )

        if isinstance(raw, Mapping):
            label = str(raw.get("label") or raw.get("value") or raw.get("id") or f"Option {index + 1}").strip()
            option_id = str(raw.get("id") or _slugify_label(label, index)).strip() or f"option-{index + 1}"
            value = raw.get("value", option_id)
            description = str(raw.get("description") or "")
            return cls(id=option_id, label=label, value=value, description=description)

        raise TypeError(f"Unsupported interaction option type: {type(raw)!r}")


@dataclass(frozen=True)
class InteractionRequest:
    kind: str
    prompt: str
    description: str = ""
    default: Any = None
    allow_empty: bool = False
    placeholder: str = ""
    options: tuple[InteractionOption, ...] = ()
    multi_select: bool = False
    min_selected: int | None = None
    max_selected: int | None = None
    submit_label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self, *, request_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "prompt": self.prompt,
            "description": self.description,
            "default": self.default,
            "allow_empty": self.allow_empty,
            "placeholder": self.placeholder,
            "options": [option.as_dict() for option in self.options],
            "multi_select": self.multi_select,
            "min_selected": self.min_selected,
            "max_selected": self.max_selected,
            "submit_label": self.submit_label,
            "metadata": dict(self.metadata),
        }
        if request_id is not None:
            payload["request_id"] = request_id
        return payload

    @classmethod
    def from_raw(cls, raw: "InteractionRequest | Mapping[str, Any]") -> "InteractionRequest":
        if isinstance(raw, cls):
            return raw
        if not isinstance(raw, Mapping):
            raise TypeError(f"Unsupported interaction request type: {type(raw)!r}")

        kind = str(raw.get("kind") or "text").strip().lower()
        if kind not in VALID_INTERACTION_KINDS:
            raise ValueError(f"Unsupported interaction kind: {kind!r}")

        options = tuple(
            InteractionOption.from_raw(option, index)
            for index, option in enumerate(raw.get("options") or [])
        )
        multi_select = bool(raw.get("multi_select", kind == "checklist"))
        if kind == "checklist":
            multi_select = True

        min_selected = raw.get("min_selected")
        max_selected = raw.get("max_selected")
        min_selected = int(min_selected) if min_selected is not None else None
        max_selected = int(max_selected) if max_selected is not None else None

        return cls(
            kind=kind,
            prompt=str(raw.get("prompt") or "Input required").strip() or "Input required",
            description=str(raw.get("description") or "").strip(),
            default=raw.get("default"),
            allow_empty=bool(raw.get("allow_empty", False)),
            placeholder=str(raw.get("placeholder") or "").strip(),
            options=options,
            multi_select=multi_select,
            min_selected=min_selected,
            max_selected=max_selected,
            submit_label=str(raw.get("submit_label") or "").strip(),
            metadata=dict(raw.get("metadata") or {}),
        )


def normalize_interaction_request(raw: InteractionRequest | Mapping[str, Any]) -> InteractionRequest:
    return InteractionRequest.from_raw(raw)