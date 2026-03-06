from __future__ import annotations

from pathlib import Path

from pocketcode.core.plugin_manager import PluginManager


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_manager(tmp_path: Path) -> PluginManager:
    plugins_root = tmp_path / "plugins"
    return PluginManager(
        config={"runtime": {"plugin_paths": [str(plugins_root)]}},
        workspace_root=tmp_path,
    )


class TestPluginManagerRuntimeLoading:
    def test_reload_refreshes_dynamic_tool_modules(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "reloadplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: reloadplug",
                    'description: "reload test"',
                    "tools:",
                    '  greet: "tools/greet.py:greet"',
                ]
            ),
        )
        tool_file = plugin_root / "tools" / "greet.py"
        _write(tool_file, "def greet():\n    return 'v1'\n")

        manager = _make_manager(tmp_path)
        manager.load()
        assert manager.tools.resolve("reloadplug.greet")() == "v1"

        _write(tool_file, "def greet():\n    return 'v2'\n")
        manager.load()
        assert manager.tools.resolve("reloadplug.greet")() == "v2"

    def test_prompt_registry_loads_manifest_prompts(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "promptplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: promptplug",
                    'description: "prompt test"',
                    "prompts:",
                    '  system: "prompts/system.md"',
                ]
            ),
        )
        _write(plugin_root / "prompts" / "system.md", "You are promptplug.\n")

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.prompts.resolve("promptplug.system") == "You are promptplug.\n"

    def test_agent_prompts_alias_loads_system_prompt(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "agentpromptplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: agentpromptplug",
                    'description: "agent prompt test"',
                    "agents:",
                    "  planner:",
                    '    module: "agents/planner.py"',
                    '    entry_fn: "create_flow"',
                    "    prompts:",
                    '      - "prompts/system.md"',
                ]
            ),
        )
        _write(
            plugin_root / "agents" / "planner.py",
            "from pocketflow import Flow, Node\n\n"
            "class _Start(Node):\n"
            "    def prep(self, shared):\n"
            "        return None\n\n"
            "    def exec(self, value):\n"
            "        return None\n\n"
            "    def post(self, shared, prep_res, exec_res):\n"
            "        return 'continue'\n\n"
            "def create_flow():\n"
            "    return Flow(start=_Start())\n",
        )
        _write(plugin_root / "prompts" / "system.md", "Plan carefully.\n")

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.agents.resolve("agentpromptplug.planner").system_prompt == "Plan carefully."

    def test_invalid_manifest_plugin_is_skipped(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "brokenplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: brokenplug",
                    'description: "broken"',
                    "agents:",
                    "  broken:",
                    '    module: "agents/broken.py"',
                ]
            ),
        )

        manager = _make_manager(tmp_path)
        manager.load()

        assert "brokenplug.broken" not in manager.agents
