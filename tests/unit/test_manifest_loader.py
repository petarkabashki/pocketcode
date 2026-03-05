"""
Unit tests for pocketcode.core.manifest_loader.

Covers:
- load_manifest() success for a valid v1 plugin.yaml
- ManifestSchemaError on missing schema_version
- ManifestSchemaError on unknown schema_version value
- agent.yaml filename → WARNING + schema_version=0 returned
- _warn_legacy_sections() → WARNING emitted for each legacy section
- Missing 'module' or 'entry_fn' → ManifestSchemaError
- Various edge-cases: non-dict YAML, bad tool entry types, bad agent cfg types
"""

from __future__ import annotations

import logging
from pathlib import Path
from textwrap import dedent

import pytest

from pocketcode.core.manifest_loader import (
    SUPPORTED_SCHEMA_VERSIONS,
    ManifestSchemaError,
    ParsedManifest,
    load_manifest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_yaml(tmp_path: Path, filename: str, content: str) -> Path:
    """Write *content* to *tmp_path/filename* and return the Path."""
    p = tmp_path / filename
    p.write_text(dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


class TestLoadManifestSuccess:
    def test_minimal_valid_plugin_yaml(self, tmp_path):
        p = write_yaml(
            tmp_path,
            "plugin.yaml",
            """
            schema_version: 1
            name: my_plugin
            description: A test plugin.
            """,
        )
        manifest = load_manifest(p)

        assert isinstance(manifest, ParsedManifest)
        assert manifest.schema_version == 1
        assert manifest.name == "my_plugin"
        assert manifest.description == "A test plugin."
        assert manifest.plugin_root == p.parent
        assert manifest.tools == {}
        assert manifest.agents == {}
        assert manifest.prompts == {}

    def test_full_plugin_yaml_with_tools_and_agents(self, tmp_path):
        p = write_yaml(
            tmp_path,
            "plugin.yaml",
            """
            schema_version: 1
            name: coder
            description: Expert coder.
            tools:
              write_file: "tools/filesystem.py:WriteFileTool"
              git_diff: "tools/git.py:GitDiffTool"
            agents:
              coder:
                module: "agents/coder_agent.py"
                entry_fn: "create_flow"
                description: "Writes code."
                tools: [write_file, git_diff]
            """,
        )
        manifest = load_manifest(p)

        assert manifest.schema_version == 1
        assert manifest.name == "coder"
        assert manifest.tools == {
            "write_file": "tools/filesystem.py:WriteFileTool",
            "git_diff": "tools/git.py:GitDiffTool",
        }
        assert "coder" in manifest.agents
        assert manifest.agents["coder"]["module"] == "agents/coder_agent.py"
        assert manifest.agents["coder"]["entry_fn"] == "create_flow"

    def test_name_defaults_to_parent_directory(self, tmp_path):
        plugin_dir = tmp_path / "my_cool_plugin"
        plugin_dir.mkdir()
        p = plugin_dir / "plugin.yaml"
        p.write_text("schema_version: 1\n", encoding="utf-8")

        manifest = load_manifest(p)
        assert manifest.name == "my_cool_plugin"

    def test_prompts_section_parsed(self, tmp_path):
        p = write_yaml(
            tmp_path,
            "plugin.yaml",
            """
            schema_version: 1
            name: myplugin
            description: ""
            prompts:
              system: "prompts/system.md"
              user: "prompts/user.md"
            """,
        )
        manifest = load_manifest(p)
        assert manifest.prompts == {
            "system": "prompts/system.md",
            "user": "prompts/user.md",
        }

    def test_llm_profiles_section_parsed(self, tmp_path):
        p = write_yaml(
            tmp_path,
            "plugin.yaml",
            """
            schema_version: 1
            name: myplugin
            description: ""
            llm_profiles:
              default:
                provider: openai
                model: gpt-4o
            """,
        )
        manifest = load_manifest(p)
        assert manifest.llm_profiles == {"default": {"provider": "openai", "model": "gpt-4o"}}


# ---------------------------------------------------------------------------
# ManifestSchemaError cases
# ---------------------------------------------------------------------------


class TestManifestSchemaErrors:
    def test_missing_schema_version_raises(self, tmp_path):
        p = write_yaml(tmp_path, "plugin.yaml", "name: bad_plugin\ndescription: oops\n")
        with pytest.raises(ManifestSchemaError, match="schema_version"):
            load_manifest(p)

    def test_unknown_schema_version_raises(self, tmp_path):
        p = write_yaml(tmp_path, "plugin.yaml", "schema_version: 99\nname: x\ndescription: y\n")
        with pytest.raises(ManifestSchemaError, match="Unsupported schema_version"):
            load_manifest(p)

    def test_schema_version_zero_raises(self, tmp_path):
        p = write_yaml(tmp_path, "plugin.yaml", "schema_version: 0\nname: x\ndescription: y\n")
        with pytest.raises(ManifestSchemaError, match="Unsupported schema_version"):
            load_manifest(p)

    def test_schema_version_string_raises(self, tmp_path):
        p = write_yaml(
            tmp_path, "plugin.yaml", "schema_version: 'one'\nname: x\ndescription: y\n"
        )
        with pytest.raises(ManifestSchemaError):
            load_manifest(p)

    def test_non_dict_yaml_raises(self, tmp_path):
        p = write_yaml(tmp_path, "plugin.yaml", "- item1\n- item2\n")
        with pytest.raises(ManifestSchemaError, match="YAML mapping"):
            load_manifest(p)

    def test_agent_missing_module_raises(self, tmp_path):
        p = write_yaml(
            tmp_path,
            "plugin.yaml",
            """
            schema_version: 1
            name: bad
            description: ""
            agents:
              bad_agent:
                entry_fn: create_flow
            """,
        )
        with pytest.raises(ManifestSchemaError, match="module"):
            load_manifest(p)

    def test_agent_missing_entry_fn_raises(self, tmp_path):
        p = write_yaml(
            tmp_path,
            "plugin.yaml",
            """
            schema_version: 1
            name: bad
            description: ""
            agents:
              bad_agent:
                module: agents/foo.py
            """,
        )
        with pytest.raises(ManifestSchemaError, match="entry_fn"):
            load_manifest(p)

    def test_agent_missing_both_module_and_entry_fn_raises(self, tmp_path):
        p = write_yaml(
            tmp_path,
            "plugin.yaml",
            """
            schema_version: 1
            name: bad
            description: ""
            agents:
              bad_agent:
                description: no wiring
            """,
        )
        with pytest.raises(ManifestSchemaError):
            load_manifest(p)


# ---------------------------------------------------------------------------
# agent.yaml (legacy) detection
# ---------------------------------------------------------------------------


class TestAgentYamlLegacyLoading:
    def test_agent_yaml_returns_schema_version_zero(self, tmp_path):
        p = write_yaml(
            tmp_path,
            "agent.yaml",
            """
            name: legacyplugin
            description: Old format plugin.
            tools:
              - id: my_tool
                handler: tools/foo.py
            """,
        )
        manifest = load_manifest(p)
        assert manifest.schema_version == 0

    def test_agent_yaml_emits_warning(self, tmp_path, caplog):
        p = write_yaml(
            tmp_path,
            "agent.yaml",
            """
            name: legacyplugin
            description: Old format plugin.
            """,
        )
        with caplog.at_level(logging.WARNING, logger="pocketcode.core.manifest_loader"):
            load_manifest(p)

        assert any("LEGACY MANIFEST" in r.message for r in caplog.records)

    def test_agent_yaml_emits_no_agent_warning(self, tmp_path, caplog):
        p = write_yaml(
            tmp_path,
            "agent.yaml",
            """
            name: legacyplugin
            description: Old.
            """,
        )
        with caplog.at_level(logging.WARNING, logger="pocketcode.core.manifest_loader"):
            load_manifest(p)

        messages = [r.message for r in caplog.records]
        assert any("module" in m or "entry_fn" in m for m in messages)

    def test_agent_yaml_migrates_tools(self, tmp_path):
        p = write_yaml(
            tmp_path,
            "agent.yaml",
            """
            name: legacy
            description: ""
            tools:
              - id: write_file
                handler: tools/filesystem.py
              - id: create_dir
                handler: tools/filesystem.py
            """,
        )
        manifest = load_manifest(p)
        assert "write_file" in manifest.tools
        assert "create_dir" in manifest.tools

    def test_agent_yaml_agents_dict_is_empty(self, tmp_path):
        p = write_yaml(
            tmp_path,
            "agent.yaml",
            "name: lg\ndescription: ''\n",
        )
        manifest = load_manifest(p)
        assert manifest.agents == {}


# ---------------------------------------------------------------------------
# Legacy section warnings (_warn_legacy_sections)
# ---------------------------------------------------------------------------


class TestLegacySectionWarnings:
    @pytest.mark.parametrize("section", ["components", "workflows", "node_definitions", "flows", "modes"])
    def test_legacy_section_emits_warning(self, tmp_path, caplog, section):
        p = write_yaml(
            tmp_path,
            "plugin.yaml",
            f"""
            schema_version: 1
            name: myplugin
            description: ""
            {section}:
              - dummy
            """,
        )
        with caplog.at_level(logging.WARNING, logger="pocketcode.core.manifest_loader"):
            load_manifest(p)

        assert any("LEGACY SECTION" in r.message for r in caplog.records)

    def test_multiple_legacy_sections_each_warn(self, tmp_path, caplog):
        p = write_yaml(
            tmp_path,
            "plugin.yaml",
            """
            schema_version: 1
            name: myplugin
            description: ""
            workflows:
              - w1
            node_definitions:
              foo: bar
            """,
        )
        with caplog.at_level(logging.WARNING, logger="pocketcode.core.manifest_loader"):
            load_manifest(p)

        legacy_warns = [r for r in caplog.records if "LEGACY SECTION" in r.message]
        assert len(legacy_warns) == 2

    def test_no_legacy_sections_no_warning(self, tmp_path, caplog):
        p = write_yaml(
            tmp_path,
            "plugin.yaml",
            "schema_version: 1\nname: clean\ndescription: ''\n",
        )
        with caplog.at_level(logging.WARNING, logger="pocketcode.core.manifest_loader"):
            load_manifest(p)

        legacy_warns = [r for r in caplog.records if "LEGACY SECTION" in r.message]
        assert len(legacy_warns) == 0


# ---------------------------------------------------------------------------
# Edge-cases / type safety
# ---------------------------------------------------------------------------


class TestTypeValidation:
    def test_tools_not_dict_returns_empty(self, tmp_path, caplog):
        p = write_yaml(
            tmp_path,
            "plugin.yaml",
            """
            schema_version: 1
            name: x
            description: ""
            tools:
              - bad_list_item
            """,
        )
        with caplog.at_level(logging.WARNING, logger="pocketcode.core.manifest_loader"):
            manifest = load_manifest(p)

        assert manifest.tools == {}

    def test_agents_not_dict_returns_empty(self, tmp_path, caplog):
        p = write_yaml(
            tmp_path,
            "plugin.yaml",
            """
            schema_version: 1
            name: x
            description: ""
            agents:
              - bad
            """,
        )
        with caplog.at_level(logging.WARNING, logger="pocketcode.core.manifest_loader"):
            manifest = load_manifest(p)

        assert manifest.agents == {}

    def test_supported_schema_versions_contains_1(self):
        assert 1 in SUPPORTED_SCHEMA_VERSIONS

    def test_empty_yaml_is_handled(self, tmp_path):
        p = write_yaml(tmp_path, "plugin.yaml", "schema_version: 1\n")
        manifest = load_manifest(p)
        assert manifest.schema_version == 1
