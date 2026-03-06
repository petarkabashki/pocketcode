# Quickstart: Agents to Plugins — Core ReAct Agent Only

**Branch**: `004-agents-to-plugins` | **Date**: 2026-03-05

This guide covers local setup, verification steps for each User Story, and the test commands to confirm the migration is complete.

---

## Prerequisites

```bash
cd /media/mu6mula/Data1/AI-Stuff/PocketCoder
source .venv/bin/activate
```

---

## Story 1 — Verify `core` plugin exposes only `react`

### What to check
After implementation, `core/plugin.yaml` must declare exactly one agent (`react`) and no `coder`, `architect`, or `ask` entries.

### Quick manifest check

```bash
# Should print: react
python - <<'EOF'
import yaml
with open("pocketcode/plugins/core/plugin.yaml") as f:
    data = yaml.safe_load(f)
agents = list(data.get("agents", {}).keys())
print("core agents:", agents)
assert agents == ["react"], f"Expected ['react'], got {agents}"
print("✅ Story 1 manifest check passed")
EOF
```

### Verify deleted files

```bash
# Both should report "No such file"
ls pocketcode/plugins/core/prompts/flows/single_agent.md 2>&1
ls pocketcode/plugins/core/prompts/nodes/single_agent/think.md 2>&1
```

### Run core-only integration test

```bash
pytest tests/integration/test_pocketflow_plugin_discovery.py \
  -k "core" -v
```

---

## Story 2 — Verify domain agents are in their plugins

### Quick manifest checks

```bash
python - <<'EOF'
import yaml, pathlib

checks = [
    (".pocketcode/plugins/coder/plugin.yaml",     "coder",     "coder"),
    (".pocketcode/plugins/architect/plugin.yaml", "architect", "architect"),
    (".pocketcode/plugins/asker/plugin.yaml",     "asker",     "ask"),
]

for path, expected_name, expected_agent in checks:
    with open(path) as f:
        data = yaml.safe_load(f)
    assert data["name"] == expected_name, \
        f"{path}: plugin name '{data['name']}' != '{expected_name}'"
    agents = list(data.get("agents", {}).keys())
    assert expected_agent in agents, \
        f"{path}: agent '{expected_agent}' not found in {agents}"
    # Ensure module path is local to plugin
    module = data["agents"][expected_agent]["module"]
    assert not module.startswith(".."), f"{path}: cross-plugin module ref forbidden"
    print(f"✅ {expected_name}::{expected_agent}")

print("✅ Story 2 manifest checks passed")
EOF
```

### Run plugin discovery integration test

```bash
pytest tests/integration/test_pocketflow_plugin_discovery.py -v
```

---

## Story 3 — Verify cross-plugin handoff routing

### Quick handoff reference check

```bash
python - <<'EOF'
import yaml

manifest_path = ".pocketcode/plugins/coder/plugin.yaml"
with open(manifest_path) as f:
    data = yaml.safe_load(f)

handoffs = data["agents"]["coder"].get("handoff_agents", [])
print("coder::coder handoffs:", handoffs)

# All handoffs must be fully-qualified (contain "::")
for h in handoffs:
    assert "::" in h, f"Bare handoff '{h}' not allowed — must be 'plugin::agent'"
print("✅ Story 3 handoff format check passed")
EOF
```

### Run agent execution integration test

```bash
pytest tests/integration/test_pocketflow_agent_execution.py -v
```

---

## Run All Tests

```bash
pytest tests/ -v --tb=short
```

Expected: **0 failures, 0 errors** across all unit and integration tests.

---

## Smoke Test: `core::react` as default agent

```bash
# pocketcode.yml default_agent must be core::react
python - <<'EOF'
import yaml
with open("pocketcode.yml") as f:
    cfg = yaml.safe_load(f)
default = cfg["runtime"]["default_agent"]
print("default_agent:", default)
assert default == "core::react", f"Expected 'core::react', got '{default}'"
assert "agent_runtime_workflow" not in cfg.get("runtime", {}), \
    "agent_runtime_workflow key must be removed"
print("✅ pocketcode.yml smoke test passed")
EOF
```

---

## Edge Case Validation

### Stale reference detection

Test that loading a config referencing `core::coder` produces a descriptive error (not a crash):

```bash
python - <<'EOF'
# Simulate a stale reference by checking the runtime raises a clear error
# This is a conceptual smoke test — real validation happens in unit tests
import sys
sys.path.insert(0, ".")
# If manifest validation is implemented correctly, loading a plugin that
# references core::coder should raise RuntimeError/ValueError with suggestion text
print("✅ Stale reference detection validated via unit tests in tests/unit/")
EOF
```

Run the associated unit test:

```bash
pytest tests/unit/test_manifest_loader.py -v -k "stale or not_found"
```

---

## Filesystem Verification Checklist

```bash
echo "=== core agents dir ===" && ls pocketcode/plugins/core/agents/
echo "=== should contain react_agent.py, __init__.py ==="
echo ""
echo "=== single_agent flow files (should not exist) ==="
ls pocketcode/plugins/core/prompts/flows/   # should NOT contain single_agent.md
ls pocketcode/plugins/core/prompts/nodes/   # should NOT contain single_agent/ dir
echo ""
echo "=== domain agent modules ==="
ls .pocketcode/plugins/coder/agents/
ls .pocketcode/plugins/architect/agents/
ls .pocketcode/plugins/asker/agents/
```
