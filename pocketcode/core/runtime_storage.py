from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

DEFAULT_SESSION_STATE_DIR = ".pocketstate"
DEFAULT_ENTRY_HISTORY_DIR = ".pockethist"
DEFAULT_CHECKPOINT_DIRNAME = "checkpoints"
ENTRY_HISTORY_FILENAME = "textual_entry_history.json"
MAX_ENTRY_HISTORY = 100


def session_storage_dir(workspace_root: str | Path, config: dict[str, Any] | None = None) -> Path:
    root = _runtime_storage_root(
        workspace_root,
        config,
        key="session_state_dir",
        default_dir=DEFAULT_SESSION_STATE_DIR,
    )
    return root / "sessions"


def entry_history_file_path(workspace_root: str | Path, config: dict[str, Any] | None = None) -> Path:
    root = _runtime_storage_root(
        workspace_root,
        config,
        key="entry_history_dir",
        default_dir=DEFAULT_ENTRY_HISTORY_DIR,
    )
    return root / ENTRY_HISTORY_FILENAME


def checkpoint_storage_dir(workspace_root: str | Path, config: dict[str, Any] | None = None) -> Path:
    root = _runtime_storage_root(
        workspace_root,
        config,
        key="session_state_dir",
        default_dir=DEFAULT_SESSION_STATE_DIR,
    )
    return root / DEFAULT_CHECKPOINT_DIRNAME


def normalize_entry_history(entries: list[str] | tuple[str, ...] | None) -> list[str]:
    normalized: list[str] = []
    for item in entries or []:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized[-MAX_ENTRY_HISTORY:]


def load_entry_history(workspace_root: str | Path, config: dict[str, Any] | None = None) -> list[str]:
    history_file = entry_history_file_path(workspace_root, config)
    if not history_file.exists():
        return []
    try:
        raw = json.loads(history_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Ignoring unreadable textual history file '%s': %s", history_file, exc)
        return []
    if not isinstance(raw, list):
        logger.warning("Ignoring invalid textual history payload in '%s'.", history_file)
        return []
    return normalize_entry_history(raw)


def save_entry_history(
    workspace_root: str | Path,
    entries: list[str] | tuple[str, ...] | None,
    config: dict[str, Any] | None = None,
) -> Path:
    normalized = normalize_entry_history(entries)
    history_file = entry_history_file_path(workspace_root, config)
    if normalized:
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history_file.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
        return history_file
    if history_file.exists():
        history_file.unlink()
    return history_file


def _runtime_storage_root(
    workspace_root: str | Path,
    config: dict[str, Any] | None,
    *,
    key: str,
    default_dir: str,
) -> Path:
    workspace_path = Path(workspace_root).resolve()
    runtime = config.get("runtime", {}) if isinstance(config, dict) else {}
    storage = runtime.get("storage", {}) if isinstance(runtime, dict) else {}
    configured = str(storage.get(key) or "").strip() if isinstance(storage, dict) else ""
    target = Path(configured or default_dir)
    if not target.is_absolute():
        target = workspace_path / target
    return target.resolve()
