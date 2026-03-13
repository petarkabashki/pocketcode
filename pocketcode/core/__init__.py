"""Core runtime package for Pocketcode."""

from __future__ import annotations

from typing import Any

__all__ = [
    "PocketCodeEngine",
    "CommandContext",
    "CommandInvocation",
    "CommandProvider",
    "CommandResult",
    "CommandSpec",
]


def __getattr__(name: str) -> Any:
    if name == "PocketCodeEngine":
        from pocketcode.core.engine import PocketCodeEngine

        return PocketCodeEngine
    if name in {"CommandContext", "CommandInvocation", "CommandProvider", "CommandResult", "CommandSpec"}:
        from pocketcode.core.command_runtime import (
            CommandContext,
            CommandInvocation,
            CommandProvider,
            CommandResult,
            CommandSpec,
        )

        return {
            "CommandContext": CommandContext,
            "CommandInvocation": CommandInvocation,
            "CommandProvider": CommandProvider,
            "CommandResult": CommandResult,
            "CommandSpec": CommandSpec,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
