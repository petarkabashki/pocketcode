# Plan: Centralized LLM Client Initialization

This plan outlines the steps to refactor the Language Model (LLM) client initialization process to ensure it's centralized, uniform across all modes, and based on configuration defined in `settings.yaml`.

## Problem

Currently, the LLM client initialization logic is missing or misplaced. Flow creation functions (e.g., `create_code_flow`) incorrectly expect a pre-initialized LLM client object within the configuration dictionaries they receive, rather than initializing the client based on settings.

## Solution Steps

1.  **Create Centralized LLM Factory:**
    *   Create a new utility module: `pocketcode/core/llm_factory.py`.
    *   Define a function within this module, e.g., `create_llm_client(llm_config: Dict, providers_config: Dict) -> Any`.
    *   This function will encapsulate the logic:
        *   Determine the provider (e.g., 'gemini', 'anthropic') from the merged `llm_config`.
        *   Look up the corresponding API key in `providers_config`.
        *   Use the appropriate library (e.g., LangChain, Google AI SDK, Anthropic SDK) to instantiate and return the LLM client object based on the provider, model, API key, and parameters.
        *   Include error handling for missing keys, invalid providers, or instantiation failures.

2.  **Integrate Factory into `BaseMode`:**
    *   Modify the `BaseMode` class (likely in `pocketcode/core/interfaces.py`).
    *   In its `__init__` method:
        *   Import `create_llm_client` from the new factory module.
        *   Determine the final `llm_config` for the specific mode instance by merging its specific config (from `settings.yaml`) with the `defaults.llm_config`.
        *   Retrieve the global `providers` config.
        *   Call `create_llm_client` using the merged `llm_config` and the `providers_config`.
        *   Store the returned, initialized `llm_client` object as an instance variable (e.g., `self._llm_client`). This ensures every mode instance gets its correctly configured client upon creation.

3.  **Standardize Flow Creation Functions:**
    *   Ensure *all* flow creation functions (like `create_code_flow`, `create_architect_flow`, etc., referenced in `settings.yaml` under `flow_module`) accept an `llm_client: Any` argument in their signature.
    *   Remove any LLM initialization logic from within these flow creation functions. They should expect a ready-to-use client.

4.  **Update Flow Creation Calls in Modes:**
    *   In the `_get_flow` method within each mode class (e.g., `KoderMode`, `ArkitektMode`):
        *   When dynamically loading and calling the flow creation function (`create_flow_func`), pass the mode's initialized `self._llm_client` instance as the `llm_client` argument.

## Conceptual Diagram

```mermaid
graph TD
    A[Load settings.yaml] --> B(Instantiate Any Mode e.g., KoderMode);
    B -- Inherits from --> C[BaseMode];
    C -- Contains LLM settings & provider keys --> D{BaseMode.__init__};
    D -- Merges Mode & Default LLM Config --> D1[Get Final LLM Config];
    D1 & D -- Pass Config --> E[llm_factory.create_llm_client(final_llm_config, providers_config)];
    E -- Returns --> F[Initialized LLM Client Object];
    D -- Stores --> G[self._llm_client];

    H[Request Processing] --> I{Mode.process_request};
    I -- Calls --> J{Mode._get_flow};
    J -- Needs Flow --> K[Checks self._flow];
    K -- Flow not present --> L[Calls create_flow_func (e.g., create_code_flow)];
    J -- Passes --> G;
    L -- Receives --> G;
    L -- Uses Client --> M[Instantiate LLM-dependent Node (e.g., CodeAgentNode)];
    L -- Returns --> N[Initialized Flow Object];
    J -- Stores --> O[self._flow];
    I -- Uses --> O;
    O -- Executes --> M;
    M -- Uses Client --> P((LLM API));

    subgraph Central LLM Factory
        E
        F
    end

    subgraph Base Mode Initialization (Uniform for all Modes)
        C
        D
        D1
        G
    end

    subgraph Flow Creation & Usage (Uniform for all Modes)
        H
        I
        J
        K
        L
        M
        N
        O
        P
    end
```

## Benefits

*   Centralized and reusable LLM client creation logic.
*   Uniform initialization process for all modes.
*   Configuration remains in `settings.yaml`.
*   Modes and flows receive ready-to-use client objects, simplifying their internal logic.
*   Easier to add support for new LLM providers in the future.