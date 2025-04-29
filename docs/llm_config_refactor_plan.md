# LLM Configuration Refactor Plan

## 1. Goal

Refactor the `pocketcode/config/settings.yaml` file to:
*   Define API keys for LLM providers centrally (once per provider).
*   Allow individual modes to specify different models from the same provider.

## 2. Current State

Currently, API keys are defined either in:
*   `defaults.llm_config` (e.g., `api_key: ${GOOGLE_API_KEY}`)
*   Specific `modes.<mode_name>.llm_config` sections (e.g., `code` mode specifies `api_key: ${ANTHROPIC_API_KEY}`).

Modes can inherit the default LLM configuration or override it entirely. This leads to potential redundancy if multiple modes use the same provider but different models, requiring repeated API key variable references.

## 3. Proposed Changes

1.  **Introduce Top-Level `providers` Section:**
    *   Create a new section at the root level of `settings.yaml` called `providers`.
    *   This section will map provider names (e.g., `google`, `anthropic`) to their respective API keys, referencing environment variables:
      ```yaml
      providers:
        google: ${GOOGLE_API_KEY}
        anthropic: ${ANTHROPIC_API_KEY}
        # Add other providers as needed
      ```

2.  **Refactor `llm_config` Sections:**
    *   **Remove `api_key`:** Delete the `api_key` field from both `defaults.llm_config` and all `modes.<mode_name>.llm_config` sections.
    *   **Ensure Provider/Model Specificity:** Each mode's `llm_config` (or the default) must still specify the `provider` and `model` it intends to use.

3.  **Update Configuration Loading Logic (`pocketcode/config/loader.py`):**
    *   Modify the configuration loading code.
    *   When determining the final LLM configuration for a mode:
        *   Identify the `provider` and `model` (from mode-specific settings or defaults).
        *   Look up the API key in the new top-level `providers` section using the identified `provider`.
        *   Inject the retrieved API key into the final LLM configuration object passed to the mode/LLM client.

## 4. Visual Plan (Mermaid Diagram)

```mermaid
graph TD
    A[Start: Current settings.yaml] --> B{API Keys Location};
    B -- Default --> C[defaults.llm_config];
    B -- Override --> D[modes.*.llm_config];
    C & D --> E[Problem: Keys Scattered/Redundant];

    E --> F[Goal: Central Keys, Mode Models];

    F --> G{Proposed Changes};
    G --> H[1. Add top-level `providers` section (Keys)];
    G --> I[2. Remove `api_key` from `llm_config` sections];
    G --> J[3. Modes define `provider` & `model`];
    G --> K[4. Modify `loader.py` logic];

    K --> L[Loader fetches key from `providers` based on mode's `provider`];
    L --> M[End: Clean settings.yaml & Updated Loader];
```

## 5. Summary of Changes

*   **`settings.yaml`:** Add a `providers` map, remove `api_key` from `llm_config`.
*   **`pocketcode/config/loader.py`:** Update logic to fetch the API key from the `providers` section based on the mode's selected provider.