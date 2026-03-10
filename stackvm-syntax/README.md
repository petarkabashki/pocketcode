# StackVM Syntax Highlighting for VS Code

This extension provides syntax highlighting for StackVM `.vm` files.

## Features
- Highlights the current StackVM control words such as `call`, `if`, `while`, `define`, `switch`, `cond`, `fallback`, `parallel-map`, and `reduce`
- Highlights host/runtime words such as `answer`, `handoff`, `tool-request`, `prompt-interaction`, `llm-call`, `shared@`, `shared!`, and `yaml>`
- Recognizes StackVM line comments that begin with `!`
- Highlights numbers, booleans, strings, and identifiers used by the current PocketCoder StackVM runtime

## Installation
1. Open VS Code.
2. Press `F5` to run the extension in a new window (if developing).
3. Or package and install:
   - Run `vsce package` in this folder to create a `.vsix` file.
   - Install via Extensions: `Install from VSIX...`

## File Types
- Files with `.vm` extension are recognized as StackVM.

## Customization
Edit `stackvm.tmLanguage.json` and `stackvm-language.json` to add more runtime words or update comment/token rules as the language evolves.
