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


def _make_workspace_plugin_manager(tmp_path: Path) -> PluginManager:
    return PluginManager(
        config={"runtime": {"plugin_paths": [".pocketcode/plugins"]}},
        workspace_root=tmp_path,
    )


class TestPluginManagerRuntimeLoading:
    def test_disabled_plugin_directory_is_not_loaded(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "hidden.disabled"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: hidden",
                    'description: "disabled plugin"',
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

        manager = _make_manager(tmp_path)
        manager.load()

        assert "hidden.planner" not in manager.agents

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

    def test_workspace_ignore_rules_filter_and_reinclude_workspace_resources(self, tmp_path):
        _write(
            tmp_path / ".pocketcode" / ".pocketcodeignore",
            "\n".join(
                [
                    "prompts/*.md",
                    "!prompts/keep.md",
                    "tools/*.py",
                    "!tools/keep.py",
                ]
            ),
        )
        _write(tmp_path / ".pocketcode" / "prompts" / "drop.md", "Drop.\n")
        _write(tmp_path / ".pocketcode" / "prompts" / "keep.md", "Keep.\n")
        _write(
            tmp_path / ".pocketcode" / "tools" / "drop.py",
            "def drop_tool(text):\n"
            "    return {'success': True, 'result': text}\n",
        )
        _write(
            tmp_path / ".pocketcode" / "tools" / "keep.py",
            "def keep_tool(text):\n"
            "    return {'success': True, 'result': text}\n",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        assert "workspace.drop" not in manager.prompts
        assert manager.prompts.resolve("workspace.keep") == "Keep.\n"
        assert "workspace.drop_tool" not in manager.tools
        assert manager.tools.resolve("workspace.keep_tool")("ok") == {
            "success": True,
            "result": "ok",
        }

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

    def test_dot_pocketcode_ignore_applies_to_workspace_plugin_resources(self, tmp_path):
        plugin_root = tmp_path / ".pocketcode" / "plugins" / "workspaceignore"
        _write(
            tmp_path / ".pocketcode" / ".pocketcodeignore",
            "\n".join(
                [
                    "plugins/workspaceignore/prompts/*.md",
                    "!plugins/workspaceignore/prompts/keep.md",
                    "plugins/workspaceignore/tools/*.py",
                    "!plugins/workspaceignore/tools/keep.py",
                ]
            ),
        )
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: workspaceignore",
                    'description: "workspace plugin ignore test"',
                    "tools:",
                    '  drop_tool: "tools/drop.py:drop_tool"',
                    '  keep_tool: "tools/keep.py:keep_tool"',
                    "prompts:",
                    '  drop: "prompts/drop.md"',
                    '  keep: "prompts/keep.md"',
                ]
            ),
        )
        _write(plugin_root / "tools" / "drop.py", "def drop_tool():\n    return 'drop'\n")
        _write(plugin_root / "tools" / "keep.py", "def keep_tool():\n    return 'keep'\n")
        _write(plugin_root / "prompts" / "drop.md", "Drop.\n")
        _write(plugin_root / "prompts" / "keep.md", "Keep.\n")

        manager = _make_workspace_plugin_manager(tmp_path)
        manager.load()

        assert "workspaceignore.drop_tool" not in manager.tools
        assert manager.tools.resolve("workspaceignore.keep_tool")() == "keep"
        assert "workspaceignore.drop" not in manager.prompts
        assert manager.prompts.resolve("workspaceignore.keep") == "Keep.\n"

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

    def test_workspace_tools_support_explicit_tool_exports(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "workspaceexports"
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: workspaceexports",
                    'description: "workspace tool export test"',
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
            tmp_path / ".pocketcode" / "tools" / "exports.py",
            "class PickTool:\n"
            "    name = 'pick'\n"
            "    def __call__(self):\n"
            "        return {'success': True, 'picked': True}\n\n"
            "def ignored_tool():\n"
            "    return {'success': True, 'ignored': True}\n\n"
            "TOOLS = {'pick_tool': PickTool()}\n",
        )

        manager = _make_manager(tmp_path)
        manager.load()

        assert manager.tools.resolve("workspace.pick_tool")() == {
            "success": True,
            "picked": True,
        }
        assert "workspace.pick_tool" in manager.resolve_tools_for_agent("workspaceexports::planner")

    def test_workspace_level_ignore_rules_apply_to_external_plugin_resources(self, tmp_path):
        plugin_root = tmp_path / "plugins" / "ignoreplug"
        _write(
            tmp_path / ".pocketcodeignore",
            "\n".join(
                [
                    "ignoreplug/tools/*.py",
                    "!ignoreplug/tools/keep.py",
                    "ignoreplug/prompts/*.md",
                    "!ignoreplug/prompts/keep.md",
                ]
            ),
        )
        _write(
            plugin_root / "plugin.yaml",
            "\n".join(
                [
                    "schema_version: 1",
                    "name: ignoreplug",
                    'description: "ignore test"',
                    "tools:",
                    '  drop_tool: "tools/drop.py:drop_tool"',
                    '  keep_tool: "tools/keep.py:keep_tool"',
                    "prompts:",
                    '  drop: "prompts/drop.md"',
                    '  keep: "prompts/keep.md"',
                ]
            ),
        )
        _write(plugin_root / "tools" / "drop.py", "def drop_tool():\n    return 'drop'\n")
        _write(plugin_root / "tools" / "keep.py", "def keep_tool():\n    return 'keep'\n")
        _write(plugin_root / "prompts" / "drop.md", "Drop.\n")
        _write(plugin_root / "prompts" / "keep.md", "Keep.\n")

        manager = _make_manager(tmp_path)
        manager.load()

        assert "ignoreplug.drop_tool" not in manager.tools
        assert manager.tools.resolve("ignoreplug.keep_tool")() == "keep"
        assert "ignoreplug.drop" not in manager.prompts
        assert manager.prompts.resolve("ignoreplug.keep") == "Keep.\n"

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
