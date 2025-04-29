#%%
"""
Tool Definitions for Pocketcode Native Tools.

This module centralizes the schemas and descriptions for the native Python functions
provided in the pocketcode.tools package. These definitions are intended to be used
by the PocketFlow framework for registering the tools and making them available to the LLM.

Each definition typically includes:
- name: The name the LLM will use to call the tool.
- description: A clear explanation of what the tool does for the LLM.
- parameters: A JSON schema describing the expected input parameters.
"""

# It's often useful to store these as a list or dictionary for easy iteration/lookup
# during registration. Using a dictionary keyed by function name might be convenient.

TOOL_DEFINITIONS = {
    # --- system.py ---
    "execute_shell_command": {
        "name": "execute_shell_command",
        "description": "Executes a shell command in the agent's environment and returns its stdout, stderr, and return code. Use with caution.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute."
                }
            },
            "required": ["command"]
        }
    },

    # --- filesystem.py ---
    "read_file": {
        "name": "read_file",
        "description": "Reads the entire content of a specified file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file from the project root."
                }
            },
            "required": ["path"]
        }
    },
    "write_file": {
        "name": "write_file",
        "description": "Writes content to a specified file. Creates the file if it doesn't exist, and overwrites it if it does. Creates parent directories if needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file from the project root."
                },
                "content": {
                    "type": "string",
                    "description": "The full content to write to the file."
                }
            },
            "required": ["path", "content"]
        }
    },
    "create_directory": {
        "name": "create_directory",
        "description": "Creates a directory at the specified path. Creates parent directories if they don't exist. Does nothing if the directory already exists.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of the directory to create from the project root."
                }
            },
            "required": ["path"]
        }
    },
    "list_directory": {
        "name": "list_directory",
        "description": "Lists the files and subdirectories within a specified directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of the directory to list. Defaults to the project root.",
                    "default": "."
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Whether to list contents recursively through all subdirectories.",
                    "default": False
                }
            },
            "required": [] # path has a default
        }
    },
    "glob_files": {
        "name": "glob_files",
        "description": "Finds files and directories matching a specified glob pattern within a base path.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The glob pattern to match (e.g., '*.py', 'src/**/*.txt', 'docs/*')."
                },
                "base_path": {
                    "type": "string",
                    "description": "The base directory to search within, relative to the project root. Defaults to the project root.",
                    "default": "."
                }
            },
            "required": ["pattern"]
        }
    },

    # --- git.py ---
    "git_status": {
        "name": "git_status",
        "description": "Shows the git working tree status (changes not staged, changes staged, untracked files) using 'git status --porcelain'.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "git_diff": {
        "name": "git_diff",
        "description": "Shows changes between commits, commit and working tree, etc. By default shows unstaged changes.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Optional relative path to a specific file to diff."
                },
                "staged": {
                    "type": "boolean",
                    "description": "Show staged changes (diff against HEAD) instead of unstaged changes (diff against index).",
                    "default": False
                }
            },
            "required": []
        }
    },
    "git_add": {
        "name": "git_add",
        "description": "Stages changes in specified files for the next commit. Use '.' to stage all changes.",
        "parameters": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of relative file paths to stage. Use ['.'] to stage all modified/new files."
                }
            },
            "required": ["files"]
        }
    },
    "git_commit": {
        "name": "git_commit",
        "description": "Records staged changes to the repository with a commit message.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The commit message."
                }
            },
            "required": ["message"]
        }
    },
    "git_pull": {
        "name": "git_pull",
        "description": "Fetches changes from a remote repository and integrates them into the current local branch.",
        "parameters": {
            "type": "object",
            "properties": {
                "remote": {
                    "type": "string",
                    "description": "The name of the remote repository (e.g., 'origin').",
                    "default": "origin"
                },
                "branch": {
                    "type": "string",
                    "description": "The specific branch name on the remote to pull. Defaults to the current branch's configured upstream."
                }
            },
            "required": []
        }
    },
    "git_push": {
        "name": "git_push",
        "description": "Updates remote refs using local refs, sending local commits to the remote repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "remote": {
                    "type": "string",
                    "description": "The name of the remote repository (e.g., 'origin').",
                    "default": "origin"
                },
                "branch": {
                    "type": "string",
                    "description": "The specific local branch name to push. Defaults to the current branch."
                }
            },
            "required": []
        }
    },

    # --- search.py ---
    "search_code": {
        "name": "search_code",
        "description": "Searches for a regex pattern within files in a specified path using ripgrep (rg). Requires 'rg' command to be installed.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The regex pattern to search for."
                },
                "path": {
                    "type": "string",
                    "description": "The directory or file path to search within, relative to the project root.",
                    "default": "."
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Optional glob pattern to filter files to search within (e.g., '*.py', '!*.md')."
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Perform a case-sensitive search.",
                    "default": False
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Number of context lines to show before and after each match.",
                    "default": 2
                }
            },
            "required": ["query"]
        }
    },

    # --- memory_bank_tools.py ---
    "read_memory_bank_file": {
        "name": "read_memory_bank_file",
        "description": "Reads the entire content of a specified Memory Bank file (e.g., productContext.md).",
        "parameters": {
            "type": "object",
            "properties": {
                "file_name": {
                    "type": "string",
                    "description": "The name of the Memory Bank file (e.g., \"productContext.md\")."
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional absolute or relative path to the project root. Defaults to current project."
                }
            },
            "required": ["file_name"]
        }
    },
    "write_memory_bank_file": {
        "name": "write_memory_bank_file",
        "description": "Writes content to a specified Memory Bank file, overwriting existing content. Creates the file/directory if needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_name": {
                    "type": "string",
                    "description": "The name of the Memory Bank file to write to."
                },
                "content": {
                    "type": "string",
                    "description": "The new content to write."
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional path to the project root."
                }
            },
            "required": ["file_name", "content"]
        }
    },
    "append_to_memory_bank_file": {
        "name": "append_to_memory_bank_file",
        "description": "Appends content to a specified Memory Bank file. Creates the file/directory if needed. Adds a newline before appending if necessary.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_name": {
                    "type": "string",
                    "description": "The name of the Memory Bank file to append to."
                },
                "content": {
                    "type": "string",
                    "description": "The content to append."
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional path to the project root."
                }
            },
            "required": ["file_name", "content"]
        }
    },
    "get_memory_bank_summary": {
        "name": "get_memory_bank_summary",
        "description": "Retrieves a summary by concatenating the content of specified Memory Bank files (or all by default).",
        "parameters": {
            "type": "object",
            "properties": {
                "file_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of Memory Bank file names to summarize. Defaults to all standard files."
                },
                "topic": {
                    "type": "string",
                    "description": "Optional specific topic or question (currently ignored)."
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional path to the project root."
                }
            },
            "required": []
        }
    },
    "check_memory_bank_status": {
        "name": "check_memory_bank_status",
        "description": "Verifies the existence and basic validity (non-empty) of standard Memory Bank files.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {
                    "type": "string",
                    "description": "Optional path to the project root."
                }
            },
            "required": []
        }
    }
}

def get_tool_definition(name: str):
    """Helper function to retrieve a tool definition by name."""
    return TOOL_DEFINITIONS.get(name)

def get_all_tool_definitions():
    """Helper function to retrieve all tool definitions."""
    return TOOL_DEFINITIONS