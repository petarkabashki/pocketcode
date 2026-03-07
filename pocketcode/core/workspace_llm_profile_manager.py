from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


logger = logging.getLogger(__name__)


class WorkspaceLlmProfileManager:
    """Load and persist workspace-backed LLM profiles."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._workspace_llm_profiles_dir = self._workspace_root / ".pocketcode" / "llm-profiles"
        self._profiles: Dict[str, Dict[str, Any]] = {}
        self._source_paths: Dict[str, Path] = {}

    def load(self) -> None:
        self._profiles = {}
        self._source_paths = {}
        if not self._workspace_llm_profiles_dir.exists():
            return

        for yaml_file in sorted(self._workspace_llm_profiles_dir.glob("*.yaml")):
            self._load_profile_file(yaml_file)

    def reload(self) -> None:
        self.load()

    def list(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": name,
                "config": copy.deepcopy(self._profiles[name]),
                "source_path": self._source_paths[name],
            }
            for name in sorted(self._profiles)
        ]

    def list_profiles(self) -> Dict[str, Dict[str, Any]]:
        return copy.deepcopy(self._profiles)

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        if name not in self._profiles:
            return None
        return {
            "name": name,
            "config": copy.deepcopy(self._profiles[name]),
            "source_path": self._source_paths[name],
        }

    def clone(self, src_name: str, new_name: str, source_config: Dict[str, Any]) -> Dict[str, Any]:
        if not new_name.strip():
            raise ValueError("LLM profile name cannot be empty.")
        target_path = self._workspace_llm_profiles_dir / f"{new_name}.yaml"
        if target_path.exists():
            raise ValueError(
                f"Cannot clone: target file '{target_path}' already exists. "
                "Choose a different name or remove the existing file first."
            )
        self.save(new_name, source_config)
        self.reload()
        cloned = self.get(new_name)
        if cloned is None:
            raise ValueError(f"Failed to load cloned LLM profile '{new_name}'.")
        return cloned

    def save(self, name: str, profile_config: Dict[str, Any]) -> Path:
        cleaned_name = str(name).strip()
        if not cleaned_name:
            raise ValueError("LLM profile name cannot be empty.")
        if not isinstance(profile_config, dict):
            raise ValueError("LLM profile config must be a mapping.")

        provider = str(profile_config.get("provider") or "").strip()
        model = str(profile_config.get("model") or "").strip()
        if not provider or not model:
            raise ValueError("LLM profiles require non-empty 'provider' and 'model' values.")

        data = dict(profile_config)
        parameters = data.get("parameters")
        if parameters is None:
            data.pop("parameters", None)
        elif not isinstance(parameters, dict):
            raise ValueError("LLM profile 'parameters' must be a mapping when provided.")

        payload = {"name": cleaned_name, **data}
        self._workspace_llm_profiles_dir.mkdir(parents=True, exist_ok=True)
        target_path = self._workspace_llm_profiles_dir / f"{cleaned_name}.yaml"
        target_path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        logger.debug("Saved workspace LLM profile '%s' to %s", cleaned_name, target_path)
        return target_path

    def _load_profile_file(self, yaml_file: Path) -> None:
        try:
            raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.warning("Skipping LLM profile file '%s': %s", yaml_file, exc)
            return

        if not isinstance(raw, dict):
            logger.warning("Skipping LLM profile file '%s': root must be a YAML mapping.", yaml_file)
            return

        name = str(raw.get("name") or yaml_file.stem).strip()
        provider = str(raw.get("provider") or "").strip()
        model = str(raw.get("model") or "").strip()
        if not name or not provider or not model:
            logger.warning(
                "Skipping LLM profile file '%s': expected 'name', 'provider', and 'model'.",
                yaml_file,
            )
            return

        profile_config = dict(raw)
        profile_config.pop("name", None)
        parameters = profile_config.get("parameters")
        if parameters is not None and not isinstance(parameters, dict):
            logger.warning(
                "Skipping LLM profile file '%s': 'parameters' must be a mapping when provided.",
                yaml_file,
            )
            return

        self._profiles[name] = profile_config
        self._source_paths[name] = yaml_file
