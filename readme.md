# Pocketcode

## Overview

Pocketcode is an open-source, highly extendable, and embeddable AI coding assistant. It aims to combine the strengths of powerful coding models with agentic, iterative development workflows, providing a flexible framework for integrating AI into custom development processes.

## Problems Solved

*   Addresses the lack of easily extendable open-source AI coding assistants.
*   Simplifies the integration of AI coding workflows into diverse development environments.
*   Provides a platform for customizing AI assistants with new tools (Python functions, MCP) and agentic behaviors (Modes).

## Core Features

*   **Agentic Modes:** Utilizes specialized modes (e.g., Coder, Architect) for different tasks, managed by the PocketFlow framework.
*   **Extensible Tooling:** Easily add new capabilities through Python functions or Model Context Protocol (MCP) servers.
*   **Modular Design:** Core components (modes, tools, workflows) are designed for loose coupling and easy extension.
*   **Workflow Engine:** Leverages PocketFlow to manage complex sequences of operations.
*   **Embeddable:** Core workflows can be integrated into other Python applications.

## Technology Stack

*   **Language:** Python (3.10+)
*   **Framework:** PocketFlow
*   **Core Tools:** Includes native tools for filesystem operations, shell command execution, Git interactions, and code search (requires `ripgrep`).

## Getting Started

1.  **Prerequisites:**
    *   Python 3.10+
    *   `ripgrep` installed and available in your system's PATH. (See [ripgrep releases](https://github.com/BurntSushi/ripgrep/releases))
2.  **Setup Virtual Environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate # Linux/macOS
    # .venv\Scripts\activate # Windows
    ```
3.  **Install Dependencies (Placeholder):**
    ```bash
    # Assuming requirements.txt will be created
    # pip install -r requirements.txt 
    ```
    *(Note: `requirements.txt` is not yet fully defined)*

## Current Status

*   **Phase:** Project Initialization & Planning.
*   The core structure and initial documentation (Memory Bank) are being established. No functional code is implemented yet. See `cline_docs/progress.md` for high-level goals.

## Contributing

Pocketcode is designed for extendability. Contributions for new modes, tools, or workflow improvements are welcome (contribution guidelines TBD).