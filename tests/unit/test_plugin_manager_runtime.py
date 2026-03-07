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

    def test_workspace_prompt_registry_loads_dot_pocketcode_prompts(self, tmp_path):
        _write(tmp_path / ".pocketcode" / "prompts" / "shared.md", "Shared workspace prompt.\n")

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.prompts.resolve("workspace.shared") == "Shared workspace prompt.\n"

    def test_workspace_prompt_files_are_available_to_plugin_agents(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "workspacepromptplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: workspacepromptplug",
                    'description: "workspace prompt fallback test"',
                    "flows:",
                    "  planner:",
                    '    module: "flows/planner.py"',
                    '    entry_fn: "create_flow"',
                    "    prompt_files:",
                    '      - "shared.md"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.py",
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
        _write(tmp_path / ".pocketcode" / "prompts" / "shared.md", "Use the shared workspace instructions.\n")

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.agents.resolve("workspacepromptplug.planner").system_prompt == "Use the shared workspace instructions."

    def test_workspace_dot_pocketcode_tools_register_and_are_visible_to_all_agents(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "workspaceplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: workspaceplug",
                    'description: "workspace tool fallback test"',
                    "flows:",
                    "  planner:",
                    '    module: "flows/planner.py"',
                    '    entry_fn: "create_flow"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.py",
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
        _write(
            tmp_path / ".pocketcode" / "tools" / "shared_tools.py",
            "def workspace_echo(text):\n"
            "    return {'success': True, 'result': text}\n",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.tools.resolve("workspace.workspace_echo")("hello") == {
            "success": True,
            "result": "hello",
        }
        assert "workspace.workspace_echo" in manager.resolve_tools_for_agent("workspaceplug::planner")

    def test_agent_prompts_alias_loads_system_prompt(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "agentpromptplug"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: agentpromptplug",
                    'description: "agent prompt test"',
                    "flows:",
                    "  planner:",
                    '    module: "flows/planner.py"',
                    '    entry_fn: "create_flow"',
                    "    prompts:",
                    '      - "prompts/system.md"',
                ]
            ),
        )
        _write(
            plugin_root / "flows" / "planner.py",
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
                    "flows:",
                    "  broken:",
                    '    module: "flows/broken.py"',
                ]
            ),
        )

        manager = _make_manager(tmp_path)
        manager.load()

        assert "brokenplug.broken" not in manager.agents
