# pocketcode/cli/command_handler.py
import logging
import os
from typing import Dict, Optional, Any, TYPE_CHECKING, Union, Type

# Use TYPE_CHECKING to avoid circular imports for type hints
if TYPE_CHECKING:
    from pocketcode.core.memory_bank import MemoryBankManager
    from pocketcode.core.watcher import FileWatcher
    # Import ModeManager for type hinting
    from pocketcode.core.mode_manager import ModeManager
    # BaseMode is no longer directly used here
    # from pocketcode.core.interfaces import BaseMode

logger = logging.getLogger(__name__)

# --- Command Handling ---
def handle_command(
    command_input: str,
    config: Dict[str, Any],
    memory_manager: Optional['MemoryBankManager'],
    file_watcher: Optional['FileWatcher'],
    # --- Updated arguments ---
    mode_manager: Optional['ModeManager'], # Pass the manager instance
    current_mode_slug: Optional[str],      # Pass the current mode's slug
    # --- End Updated arguments ---
    registered_components: Dict[str, Dict[str, Union[str, Type]]], # Contains tool classes now
    cli_context: Dict[str, Any],
    global_allow_mode_switching: bool
) -> Optional[str]: # Return the potentially updated mode SLUG
    """
    Parses and executes CLI commands, interacting with ModeManager.

    Args:
        command_input: The raw command string from the user.
        config: The global configuration dictionary.
        memory_manager: The MemoryBankManager instance (or None).
        file_watcher: The FileWatcher instance (or None).
        mode_manager: The ModeManager instance (or None).
        current_mode_slug: The slug of the currently active mode (or None).
        registered_components: Dictionary containing registered tools (classes).
                               'modes' key is likely unused here now.
        cli_context: The dictionary holding CLI-managed context.
        global_allow_mode_switching: Boolean indicating if mode switching is globally enabled.

    Returns:
        The slug of the new mode if a switch occurred and was successful, otherwise None.
    """
    parts = command_input.strip().split()
    command = parts[0].lower()
    args = parts[1:]

    logger.debug(f"Handling command: {command} with args: {args}")

    if not mode_manager:
        logger.error("ModeManager not provided to handle_command. Cannot process most commands.")
        print("[Error] Internal error: ModeManager unavailable.")
        return None # Cannot proceed without manager

    # Get available modes and tools from manager and components dict
    available_modes = mode_manager.get_available_modes() # Dict[slug, mode_config]
    registered_tools = registered_components.get('tools', {}) # Dict[name, ToolClass]

    new_mode_slug = None # Variable to hold the new slug if mode changes

    if command == "/help":
        print_help()
    elif command == "/create-memory-bank":
        # (Logic unchanged)
        if memory_manager:
            print(f"Attempting to create memory bank structure in: {memory_manager.get_memory_bank_path()}")
            success = memory_manager.create_memory_bank_structure()
            if success: print("Memory bank structure created successfully (or already existed).")
            else: print("Failed to create memory bank structure. Check logs.")
        else:
            print("Memory bank is not configured or enabled. Cannot create structure.")
            logger.warning("Attempted /create-memory-bank, but memory bank is not configured/enabled.")

    elif command == "/modes":
        target_modes = args if args else sorted(available_modes.keys())
        print("Modes and Allowed Tools (from config):")
        found_any = False
        for mode_slug in target_modes:
            mode_config = available_modes.get(mode_slug) # Get config from manager's loaded configs
            if mode_config and isinstance(mode_config, dict): # Check if config exists and is a dict
                found_any = True
                allowed_tools_list = mode_config.get('allowed_tools', [])
                display_name = mode_config.get('display_name', mode_slug)
                print(f"  {display_name} ({mode_slug}):")
                if allowed_tools_list:
                    for tool_name in sorted(allowed_tools_list):
                        print(f"    - {tool_name}")
                else:
                    print("    (No tools specifically configured)")
            else:
                print(f"  Warning: Mode '{mode_slug}' requested but not found or config invalid.")
        if not found_any and not args:
             print("  (No modes available via ModeManager)")


    elif command == "/mode":
        if not global_allow_mode_switching:
            print("Mode switching is currently disabled by configuration.")
            logger.warning("Attempted /mode command while mode switching is disabled.")
            return None # Indicate no mode change

        if not args:
            print("Usage: /mode <mode_slug>")
            print("Available modes:", list(available_modes.keys()))
            return None

        target_mode_slug = args[0]

        if current_mode_slug and target_mode_slug == current_mode_slug:
             print(f"Already in mode '{target_mode_slug}'.")
             return None # No change

        if target_mode_slug in available_modes:
            # Mode exists, signal the main loop to switch by returning the slug
            target_mode_config = available_modes[target_mode_slug]
            # Ensure config is dict before getting display name
            if isinstance(target_mode_config, dict):
                 display_name = target_mode_config.get('display_name', target_mode_slug)
            else:
                 display_name = target_mode_slug
                 logger.warning(f"Mode config for '{target_mode_slug}' is not a dictionary.")

            logger.info(f"Requesting switch to mode: {display_name} ({target_mode_slug})")
            print(f"Switching to mode: {display_name}")
            new_mode_slug = target_mode_slug # Set slug to be returned
        else:
            logger.warning(f"Mode '{target_mode_slug}' not found.")
            print(f"Unknown mode: '{target_mode_slug}'. Available modes:", list(available_modes.keys()))

    elif command == "/tools":
        show_all = "--all" in args

        if show_all:
            print("All Registered Tools:")
            if registered_tools:
                for tool_name in sorted(registered_tools.keys()):
                    print(f"  - {tool_name}")
            else:
                print("  (No tools registered)")
        elif current_mode_slug:
            # Get current mode's config from the manager's loaded configs
            current_mode_config = available_modes.get(current_mode_slug)
            if current_mode_config and isinstance(current_mode_config, dict):
                display_name = current_mode_config.get('display_name', current_mode_slug)
                print(f"Tools available for current mode ({display_name}):")
                mode_tools = current_mode_config.get('allowed_tools', [])
                if mode_tools:
                     for tool_name in sorted(mode_tools):
                         if tool_name in registered_tools:
                             print(f"  - {tool_name}")
                         else:
                             print(f"  - {tool_name} (Warning: Configured but not registered)")
                else:
                    print("  (No tools specifically configured for this mode)")
            else:
                 logger.error(f"Could not retrieve valid config for current mode '{current_mode_slug}'.")
                 print(f"  (Error retrieving tool list for mode '{current_mode_slug}')")
        else:
             print("Error: No active mode to list tools for.")

    # %% /context command handling (Unchanged logic)
    elif command == "/context":
        if not args:
            print("Usage: /context <show|add|remove|clear> [options...]")
            print("Run '/context help' for more details.")
            return None # Indicate no mode change

        subcommand = args[0].lower()
        sub_args = args[1:]

        if subcommand == "help":
             print_context_help()

        elif subcommand == "show":
            show_type = sub_args[0].lower() if sub_args else "all"
            print("--- Current CLI Context ---")
            if show_type in ["all", "files"] and cli_context["files"]:
                print("Files:")
                for item in sorted(list(cli_context["files"])): print(f"  - {item}")
            if show_type in ["all", "folders"] and cli_context["folders"]:
                print("Folders:")
                for item in sorted(list(cli_context["folders"])): print(f"  - {item}")
            if show_type in ["all", "urls"] and cli_context["urls"]:
                print("URLs:")
                for item in sorted(list(cli_context["urls"])): print(f"  - {item}")
            if show_type in ["all", "snippets"] and cli_context["snippets"]:
                print("Snippets:")
                for name, content in sorted(cli_context["snippets"].items()):
                    print(f"  - {name}: '{content[:50]}{'...' if len(content) > 50 else ''}'")
            if not cli_context["files"] and not cli_context["folders"] and \
               not cli_context["urls"] and not cli_context["snippets"]:
                print("(Context is empty)")
            print("---------------------------")

        elif subcommand == "add":
            if len(sub_args) < 2:
                print(f"Usage: /context add <file|folder|url|snippet> <value...>")
                return None
            add_type = sub_args[0].lower()
            value = sub_args[1:]

            if add_type == "file":
                file_path = value[0]
                cli_context["files"].add(file_path)
                print(f"Added file context: {file_path}")
            elif add_type == "folder":
                folder_path = value[0]
                cli_context["folders"].add(folder_path)
                print(f"Added folder context: {folder_path}")
            elif add_type == "url":
                url = value[0]
                cli_context["urls"].add(url)
                print(f"Added URL context: {url}")
            elif add_type == "snippet":
                if len(value) < 2:
                    print("Usage: /context add snippet <name> <content...>")
                    return None
                snippet_name = value[0]
                snippet_content = " ".join(value[1:])
                cli_context["snippets"][snippet_name] = snippet_content
                print(f"Added snippet context: '{snippet_name}'")
            else:
                print(f"Unknown context type to add: '{add_type}'. Use file, folder, url, or snippet.")

        elif subcommand == "remove":
            if len(sub_args) < 2:
                print(f"Usage: /context remove <file|folder|url|snippet> <value_or_name>")
                return None
            remove_type = sub_args[0].lower()
            identifier = sub_args[1]

            item_removed = False
            if remove_type == "file":
                if identifier in cli_context["files"]: cli_context["files"].remove(identifier); item_removed = True
            elif remove_type == "folder":
                 if identifier in cli_context["folders"]: cli_context["folders"].remove(identifier); item_removed = True
            elif remove_type == "url":
                 if identifier in cli_context["urls"]: cli_context["urls"].remove(identifier); item_removed = True
            elif remove_type == "snippet":
                 if identifier in cli_context["snippets"]: del cli_context["snippets"][identifier]; item_removed = True
            else:
                print(f"Unknown context type to remove: '{remove_type}'.")
                return None

            if item_removed: print(f"Removed {remove_type} context: {identifier}")
            else: print(f"{remove_type.capitalize()} context not found: {identifier}")

        elif subcommand == "clear":
            clear_type = sub_args[0].lower() if sub_args else "all"
            cleared_something = False
            if clear_type in ["all", "files"] and cli_context["files"]: cli_context["files"].clear(); print("Cleared file context."); cleared_something = True
            if clear_type in ["all", "folders"] and cli_context["folders"]: cli_context["folders"].clear(); print("Cleared folder context."); cleared_something = True
            if clear_type in ["all", "urls"] and cli_context["urls"]: cli_context["urls"].clear(); print("Cleared URL context."); cleared_something = True
            if clear_type in ["all", "snippets"] and cli_context["snippets"]: cli_context["snippets"].clear(); print("Cleared snippet context."); cleared_something = True

            if not cleared_something and clear_type != "all": print(f"No {clear_type} context found to clear.")
            elif clear_type == "all" and not cleared_something: print("Context was already empty.")
            elif clear_type not in ["all", "files", "folders", "urls", "snippets"]: print(f"Unknown context type to clear: '{clear_type}'.")

        else:
            print(f"Unknown /context subcommand: '{subcommand}'. Use show, add, remove, clear, or help.")

    # %% /mode-switch-status command (Unchanged logic)
    elif command == "/mode-switch-status":
        status = "enabled" if global_allow_mode_switching else "disabled"
        print(f"Mode switching is currently {status} (based on configuration).")

    # %% /watch command handling (Unchanged logic)
    elif command == "/watch":
        if not file_watcher:
            print("Error: File watcher is not initialized.")
            logger.error("Attempted /watch command but file_watcher is None.")
            return None

        if not args:
            print("Usage: /watch <start|stop|status> [paths...]")
            return None

        subcommand = args[0].lower()
        watch_args = args[1:]

        if subcommand == "start":
            if not watch_args: print("Usage: /watch start <path1> [path2...]"); return None
            added_count = 0
            for path in watch_args:
                if file_watcher.add_watch(path): added_count += 1
            print(f"Added {added_count} path(s) to watcher.")
            if not file_watcher.is_running() and added_count > 0: print("Starting watcher thread..."); file_watcher.start()
            elif not file_watcher.is_running() and added_count == 0: print("No valid paths added, watcher not started.")
            elif file_watcher.is_running(): print("Watcher is already running.")

        elif subcommand == "stop":
            if not watch_args:
                print("Stopping watcher and clearing all watched paths...")
                watched = file_watcher.get_watched_paths()
                removed_count = 0
                for path in list(watched):
                    if file_watcher.remove_watch(path): removed_count += 1
                if file_watcher.is_running(): file_watcher.stop()
                print(f"Removed {removed_count} path(s). Watcher stopped.")
            else:
                removed_count = 0
                for path in watch_args:
                    if file_watcher.remove_watch(path): removed_count += 1
                print(f"Removed {removed_count} path(s) from watcher.")
                if not file_watcher.get_watched_paths() and file_watcher.is_running():
                     print("No paths left to watch. Stopping watcher thread..."); file_watcher.stop()

        elif subcommand == "status":
            if file_watcher.is_running():
                print("Watcher status: Running")
                watched = file_watcher.get_watched_paths()
                if watched: print("Watching paths:"); [print(f"  - {p}") for p in sorted(list(watched))]
                else: print("Watching paths: (None)")
            else:
                print("Watcher status: Stopped")
                watched = file_watcher.get_watched_paths()
                if watched: print("Paths configured for watching (if started):"); [print(f"  - {p}") for p in sorted(list(watched))]

        else:
            print(f"Unknown /watch subcommand: '{subcommand}'. Use start, stop, or status.")


    else:
        logger.warning(f"Unknown command: {command}")
        print(f"Unknown command: {command}")
        print_help() # Show help for unknown commands

    # Return the slug of the new mode if a switch occurred, otherwise None
    return new_mode_slug

# (print_help and print_context_help remain unchanged)
def print_help():
    """Prints the available CLI commands."""
    help_text = """
Pocketcode Commands:
  /help                    Show this help message.
  /mode <mode_slug>        Switch to the specified mode (if enabled).
  /modes [<m1> <m2> ...]   List allowed tools for specified modes (or all modes).
  /tools [--all]           List tools for current mode (or all registered tools).
  /context <cmd> [opts]    Manage CLI context (files, folders, urls, snippets). Run '/context help'.
  /watch start <p1> [<p2>..] Start watching specified file(s) or directorie(s).
  /watch stop [<p1> <p2>..] Stop watching specified path(s), or all paths if none given.
  /watch status            Show if the watcher is running and list watched paths.
  /create-memory-bank    Create the memory bank directory and required empty files (if configured).
  /mode-switch-status    Show if mode switching is currently enabled or disabled by configuration.
  Ctrl+C                   Exit Pocketcode.

Note: Tool execution confirmation is handled based on 'core.require_tool_confirmation'
      and 'core.auto_approved_tools' settings in settings.yaml.
Watch mode triggers on lines containing 'AI!' (configurable) in modified watched files.
"""
    print(help_text)

def print_context_help():
    """Prints help specific to the /context command."""
    context_help = """
/context Commands:
  /context show [files|folders|urls|snippets|all]
                           Show current context items (default: all).
  /context add file <path>
                           Add a file path to the context.
  /context add folder <path>
                           Add a folder path to the context.
  /context add url <url>
                           Add a URL to the context.
  /context add snippet <name> <content...>
                           Add a named text snippet to the context.
  /context remove file <path>
                           Remove a file path from the context.
  /context remove folder <path>
                           Remove a folder path from the context.
  /context remove url <url>
                           Remove a URL from the context.
  /context remove snippet <name>
                           Remove a named snippet from the context.
  /context clear [files|folders|urls|snippets|all]
                           Clear context items (default: all).
  /context help            Show this context command help.

Note: This context is currently managed per-session and passed to the active mode.
"""
    print(context_help)