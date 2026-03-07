# Quickstart: CLI Consistency Cleanup

## Goal

Verify that the cleaned CLI contract is consistent across basic CLI usage, one-shot command execution, and Textual-specific discovery.

## Prerequisites

1. Activate the project environment.
2. Ensure you are on branch `005-cleanup-cli-consistency`.

## Validation Steps

1. Run the targeted CLI unit tests.

```bash
source .venv/bin/activate
pytest tests/unit/test_command_handler.py tests/unit/test_cli_user_interaction.py
```

2. Run any additional CLI contract tests added for help output, startup output, and interface-specific discovery.

```bash
source .venv/bin/activate
pytest tests/unit -k "command_handler or cli or textual"
```

3. Smoke-test one-shot universal help.

```bash
source .venv/bin/activate
python -m pocketcode.main --prompt "/help"
```

Expected result:

- universal help shows only universally supported commands
- no removed workflow terminology appears
- deprecated removed aliases or flags are absent from the public contract

4. Smoke-test one-shot status output.

```bash
source .venv/bin/activate
python -m pocketcode.main --prompt "/status"
```

Expected result:

- runtime labels use agent-centered terminology
- no user-facing workflow wording remains

5. Start the Textual UI and confirm interface-only command discovery remains local to Textual surfaces.

```bash
source .venv/bin/activate
python -m pocketcode.main
```

Expected result:

- Textual-only actions remain discoverable inside Textual UI
- interface-only commands are not advertised in universal help or shared suggestions
- Textual-local help or hints clearly expose retained interface-specific commands without contradicting the universal help surface

## Completion Checklist

- Universal help and shared suggestions expose only universal commands.
- Interface-specific commands are discoverable only in their owning interface.
- Interface-specific discovery is explicitly validated inside the owning interface rather than inferred only from universal help behavior.
- Public CLI wording is centered on `agent` and no longer exposes `workflow`.
- Old CLI routing and terminology helpers tied only to deprecated behavior are removed.