"""Core runtime package for Pocketcode."""

from __future__ import annotations

from typing import Any

__all__ = ["PocketCodeEngine"]


def __getattr__(name: str) -> Any:
	if name == "PocketCodeEngine":
		from pocketcode.core.engine import PocketCodeEngine

		return PocketCodeEngine
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
