# Dynamic Mode Loading Implementation Plan

**Approved:** Yes (with modification)

**Goal:**

1.  Rename `pocketcode/flows` to `pocketcode/mode_flows`.
2.  Modify `ModeManager` to dynamically discover and load modes (flow structures) from Python files within `pocketcode/mode_flows`.
3.  Continue loading mode *configuration* (LLM settings, tools, display names) from `settings.yaml`.
4.  Ensure the application correctly identifies and uses the dynamically loaded modes.

**Plan:**

1.  **Rename Directory (Manual Step Required):**
    *   The directory `pocketcode/flows` needs to be renamed to `pocketcode/mode_flows`.
    *   *Note: This step requires manual intervention or switching to a mode with execution capabilities.*

2.  **Modify `pocketcode/core/mode_manager.py`:**
    *   **Add Dynamic Discovery:**
        *   Implement a new private method, e.g., `_discover_mode_flows(self, flows_dir_path)`, that:
            *   Scans the specified directory (`pocketcode/mode_flows`).
            *   Identifies Python files (e.g., `asker.py`, `koder.py`, excluding `__init__.py`).
            *   For each file, derives the `mode_slug` (e.g., `asker`).
            *   Dynamically imports the module.
            *   Looks for a function named `create_{mode_slug}_flow` within the module.
            *   Returns a dictionary mapping `mode_slug` to the full import path of its creation function (e.g., `{'asker': 'pocketcode.mode_flows.asker.create_asker_flow'}`).
    *   **Update `__init__`:**
        *   Call `_discover_mode_flows` to get the discovered flow function paths.
        *   Load the static configurations from `settings.yaml` using `_load_mode_configs` as before.
        *   Merge the discovered function paths with the static configurations:
            *   Iterate through the static configurations. For each `mode_slug`, check if it was discovered.
            *   If discovered, add the discovered function path to the mode's configuration dictionary (e.g., under a key like `_flow_creator_path`).
            *   If a mode is in static config but *not* discovered, **raise an error** (missing file/function).
            *   If a mode is discovered but *not* in static config, **raise an error** (missing configuration).
            *   Store the final, valid configurations in `self._mode_configs`.
    *   **Update `get_flow_structure`:**
        *   Modify this method to retrieve the flow creator function path from the mode's configuration dictionary (using the new key, e.g., `_flow_creator_path`).
        *   Import and call the function using this dynamically discovered path.
        *   Remove the dependency on the old `flow_module` key from the static configuration.

3.  **Update `settings.yaml` (Recommended):**
    *   Remove the `flow_module` key from each mode's definition within `settings.yaml`, as it will no longer be used. This keeps the configuration clean.

4.  **Code Search (Verification):**
    *   Perform a search across the codebase for any remaining explicit imports like `from pocketcode.flows...` and update them to `from pocketcode.mode_flows...` if found.

**Diagram:**

```mermaid
graph TD
    A[Start Application] --> B(Load settings.yaml);
    B --> C{Instantiate ModeManager};
    C --> D(Load Static Mode Configs from settings.yaml);
    C --> E(Discover Mode Flows in pocketcode/mode_flows);
    E --> F(Import Modules & Find create_*_flow functions);
    F --> G{Build Discovered Flows Map};
    D & G --> H(Merge Static Config & Discovered Flows);
    H -- Mismatch --> H_Error{Raise Error};
    H -- Match --> I[Store Final Mode Configs in ModeManager];
    I --> J{User Interaction / Request};
    J --> K(ModeManager.get_flow_structure);
    K --> L(Retrieve Mode Config including _flow_creator_path);
    L --> M(Import & Call create_*_flow function);
    M --> N[Return Flow Structure];
    J & N --> O(ModeManager.prepare_initial_store);
    O --> P[Inject Dependencies into Shared Store];
    N & P --> Q(Execute Flow);
    Q --> R[Return Result];

    subgraph ModeManager Initialization
        direction LR
        D; E; F; G; H; H_Error; I;
    end

    subgraph Request Processing
        direction LR
        J; K; L; M; N; O; P; Q; R;
    end

    style E fill:#f9f,stroke:#333,stroke-width:2px
    style F fill:#f9f,stroke:#333,stroke-width:2px
    style G fill:#f9f,stroke:#333,stroke-width:2px
    style H fill:#f9f,stroke:#333,stroke-width:2px
    style L fill:#f9f,stroke:#333,stroke-width:2px
    style M fill:#f9f,stroke:#333,stroke-width:2px
    style H_Error fill:#f00,stroke:#333,stroke-width:2px