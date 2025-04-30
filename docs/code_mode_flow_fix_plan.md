# Plan to Fix KoderMode Flow Initialization TypeError

## Problem

The `pocketcode.modes.code.KoderMode` class attempts to create a flow instance by calling `pocketcode.flows.code.create_code_flow`. However, it passes incorrect arguments, leading to a `TypeError: create_code_flow() got an unexpected keyword argument 'config'`.

**Root Causes:**

1.  `KoderMode._get_flow` passes `self._config` using the argument name `config` instead of the expected `mode_config`.
2.  `KoderMode._get_flow` does not pass the required `global_config` and `tool_registry` arguments to `create_code_flow`.
3.  `KoderMode._get_flow` conditionally passes `memory_manager`, which is not an expected argument for `create_code_flow`.
4.  `KoderMode.__init__` does not accept or store `global_config` or `tool_registry`, making them unavailable when `_get_flow` is called.

## Proposed Solution

Modify `KoderMode` and its instantiation process to ensure `create_code_flow` receives the correct arguments.

**Steps:**

1.  **Modify `KoderMode.__init__`:**
    *   Update the constructor signature to accept `global_config: Dict[str, Any]` and `tool_registry: Dict[str, str]` in addition to the mode-specific `config`.
    *   Store these new arguments as instance attributes: `self._global_config` and `self._tool_registry`.
    *   Keep `self._config` for the mode-specific settings.

2.  **Modify `KoderMode._get_flow`:**
    *   When preparing the `flow_args` dictionary for `create_code_flow`:
        *   Use the key `mode_config` for the value `self._config`.
        *   Use the key `global_config` for the value `self._global_config`.
        *   Use the key `tool_registry` for the value `self._tool_registry`.
    *   Remove any logic that attempts to pass `memory_manager` to `create_code_flow`.

3.  **Update `KoderMode` Instantiation:**
    *   Identify the code responsible for creating `KoderMode` instances (likely in `pocketcode/main.py` or a related factory/registration function).
    *   Ensure that the necessary `global_config` (e.g., the main `settings` dictionary) and the `tool_registry` (obtained from component registration) are passed to the `KoderMode` constructor during instantiation.

## Data Flow Diagram

```mermaid
graph TD
    A[Load Settings & Register Tools (e.g., in main.py)] -->|settings (global_config), tool_registry, mode_config| B(Instantiate KoderMode);
    B --> C{KoderMode Instance};
    C -- Stores --> D[self._config (mode_config)];
    C -- Stores --> E[self._global_config];
    C -- Stores --> F[self._tool_registry];
    G[KoderMode.process_request calls _get_flow] --> H(KoderMode._get_flow);
    H -- Uses --> D;
    H -- Uses --> E;
    H -- Uses --> F;
    H -->|mode_config=self._config, global_config=self._global_config, tool_registry=self._tool_registry| I(flows.code.create_code_flow);
    I --> J[Flow Instance];
```

## Next Steps

Implement these changes in `pocketcode/modes/code.py` and the relevant instantiation code (likely `pocketcode/main.py`) using the Code mode.