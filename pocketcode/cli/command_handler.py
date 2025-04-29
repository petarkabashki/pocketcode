#%% pocketcode/cli/command_handler.py
import logging
import os
from typing import Dict, Optional, Any, TYPE_CHECKING

# Use TYPE_CHECKING to avoid circular imports for type hints if necessary
# These imports might need adjustment based on actual project structure/availability
if TYPE_CHECKING:
    from pocketcode.core.memory_bank import MemoryBankManager
    from pocketcode.core.watcher import FileWatcher
    from pocketcode.core.interfaces import BaseMode

logger = logging.getLogger(__name__)

# --- Command Handling ---
def handle_command(
    command_input: str,
    config: Dict[str, Any],
    memory_manager: Optional['MemoryBankManager'], # Use string literal for forward ref if needed
    file_watcher: Optional['FileWatcher'],       # Use string literal for forward ref if needed
    current_mode_instance: Optional['BaseMode'], # Use string literal for forward ref if needed
    registered_components: Dict[str, Dict],
    cli_context: Dict[str, Any],
    global_allow_mode_switching: bool
) -> Optional['BaseMode']: # Return the potentially updated mode instance
    """
    Parses and executes CLI commands.

    Args:
        command_input: The raw command string from the user (e.g., "/mode code").
        config: The global configuration dictionary.
        memory_manager: The MemoryBankManager instance (or None).
        file_watcher: The FileWatcher instance (or None).
        current_mode_instance: The currently active mode instance (or None).
        registered_components: Dictionary containing registered modes and tools.
        cli_context: The dictionary holding CLI-managed context (files, folders, etc.).
        global_allow_mode_switching: Boolean indicating if mode switching is globally enabled.

    Returns:
        The potentially updated current_mode_instance if a mode switch occurred, otherwise None.
        Returning the instance allows the main loop to update its reference.
    """
    parts = command_input.strip().split()
    command = parts[0].lower()
    args = parts[1:]

    logger.debug(f"Handling command: {command} with args: {args}")

    # Removed global declarations - using passed arguments instead
    # global current_mode_instance -> use current_mode_instance parameter
    # global registered_components -> use registered_components parameter
    # global cli_context -> use cli_context parameter
    # global global_allow_mode_switching -> use global_allow_mode_switching parameter

    registered_modes = registered_components.get('modes', {})
    registered_tools = registered_components.get('tools', {})

    new_mode_instance = None # Variable to hold the new instance if mode changes

    if command == "/help":
        print_help()
    elif command == "/create-memory-bank": # Added command
        if memory_manager:
            print(f"Attempting to create memory bank structure in: {memory_manager.get_memory_bank_path()}")
            success = memory_manager.create_memory_bank_structure()
            if success:
                print("Memory bank structure created successfully (or already existed).")
            else:
                print("Failed to create memory bank structure. Check logs for details.")
        else:
            print("Memory bank is not configured or enabled in settings. Cannot create structure.")
            logger.warning("Attempted /create-memory-bank command, but memory bank is not configured/enabled.")

    elif command == "/modes": # New command implementation
        target_modes = args if args else sorted(registered_modes.keys())
        print("Modes and Allowed Tools:")
        found_any = False
        for mode_slug in target_modes:
            if mode_slug in registered_modes:
                found_any = True
                mode_config = config.get('modes', {}).get(mode_slug, {})
                allowed_tools_list = mode_config.get('allowed_tools', [])
                print(f"  {mode_slug}:")
                if allowed_tools_list:
                    for tool_name in sorted(allowed_tools_list):
                        print(f"    - {tool_name}")
                else:
                    print("    (No tools specifically configured)")
            else:
                print(f"  Warning: Mode '{mode_slug}' requested but not registered.")
        if not found_any and not args:
             print("  (No modes registered)")


    elif command == "/mode":
        # Check if mode switching is allowed globally
        if not global_allow_mode_switching:
            print("Mode switching is currently disabled by configuration.")
            logger.warning("Attempted /mode command while mode switching is disabled.")
            return None # Indicate no mode change

        if not args:
            logger.warning("Usage: /mode <mode_slug>")
            print("Please specify a mode slug. Available modes:", list(registered_modes.keys()))
            return None # Indicate no mode change
        target_mode_slug = args[0]
        # Use slug for comparison
        current_slug = getattr(current_mode_instance, 'slug', None)
        if current_slug and target_mode_slug == current_slug:
             print(f"Already in mode '{target_mode_slug}'.")
             return None # Indicate no mode change
        if target_mode_slug in registered_modes:
            ModeClass = registered_modes[target_mode_slug]
            mode_config = config.get('modes', {}).get(target_mode_slug, {})
            if not mode_config:
                logger.error(f"Configuration for mode '{target_mode_slug}' not found.")
                print(f"Error: Configuration missing for mode '{target_mode_slug}'.")
                return None # Indicate no mode change
            try:
                mode_config['slug'] = target_mode_slug # Ensure slug is in config for the instance
                # Pass memory_manager, global_config, tool_registry when switching modes
                # Store the new instance in a local variable
                new_mode_instance_local = ModeClass(
                    config=mode_config,
                    memory_manager=memory_manager,
                    global_config=config,
                    tool_registry=registered_tools
                )
                logger.info(f"Switched to mode: {new_mode_instance_local.display_name}")
                print(f"Switched to mode: {new_mode_instance_local.display_name}")
                new_mode_instance = new_mode_instance_local # Assign to return variable
            except TypeError as e:
                 # Handle cases where ModeClass doesn't accept new args yet
                 if 'global_config' in str(e) or 'tool_registry' in str(e):
                      logger.warning(f"Mode '{target_mode_slug}' does not seem to accept 'global_config' or 'tool_registry'. Instantiating without them. Error: {e}")
                      new_mode_instance_local = ModeClass(config=mode_config, memory_manager=memory_manager) # Fallback
                      logger.info(f"Switched to mode (fallback): {new_mode_instance_local.display_name}")
                      print(f"Switched to mode (fallback): {new_mode_instance_local.display_name}")
                      new_mode_instance = new_mode_instance_local # Assign to return variable
                 elif 'memory_manager' in str(e):
                      logger.warning(f"Mode '{target_mode_slug}' does not seem to accept 'memory_manager' argument. Instantiating without it. Error: {e}")
                      new_mode_instance_local = ModeClass(config=mode_config) # Fallback
                      logger.info(f"Switched to mode (without memory manager): {new_mode_instance_local.display_name}")
                      print(f"Switched to mode (without memory manager): {new_mode_instance_local.display_name}")
                      new_mode_instance = new_mode_instance_local # Assign to return variable
                 else:
                      logger.error(f"Error switching to mode '{target_mode_slug}': {e}", exc_info=True)
                      print(f"Error switching to mode '{target_mode_slug}'.")
            except Exception as e:
                logger.error(f"Error switching to mode '{target_mode_slug}': {e}", exc_info=True)
                print(f"Error switching to mode '{target_mode_slug}'.")
        else:
            logger.warning(f"Mode '{target_mode_slug}' not found.")
            print(f"Unknown mode: '{target_mode_slug}'. Available modes:", list(registered_modes.keys()))

    elif command == "/tools": # MODIFIED: Removed auto-allow status check/display
        show_all = "--all" in args
        current_slug = getattr(current_mode_instance, 'slug', None)

        if show_all:
            print("All Registered Tools:")
            if registered_tools:
                for tool_name in sorted(registered_tools.keys()):
                    # REMOVED: allowed = is_tool_auto_allowed(tool_name)
                    # REMOVED: status = "(allowed)" if allowed else ""
                    print(f"  - {tool_name}") # Just print the name
            else:
                print("  (No tools registered)")
        elif current_mode_instance and current_slug:
            print(f"Tools available for current mode ({current_mode_instance.display_name}):")
            try:
                mode_config = getattr(current_mode_instance, 'config', {})
                mode_tools = mode_config.get('allowed_tools', []) # Use allowed_tools from config
                if mode_tools:
                     for tool_name in sorted(mode_tools):
                         if tool_name in registered_tools:
                             # REMOVED: allowed = is_tool_auto_allowed(tool_name, current_slug)
                             # REMOVED: status = "(allowed)" if allowed else ""
                             print(f"  - {tool_name}") # Just print the name
                         else:
                             print(f"  - {tool_name} (Warning: Configured but not registered)")
                else:
                    print("  (No tools specifically configured for this mode)")
            except AttributeError:
                 logger.error(f"Could not retrieve tool list from mode {current_mode_instance.display_name}. Does it have a 'config' attribute with a 'allowed_tools' key?")
                 print("  (Error retrieving tool list for this mode)")
        else:
             print("Error: No active mode to list tools for.")

    # REMOVED: /allow and /disallow command handling logic

    # %% Added: /context command handling
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
                return None # Indicate no mode change
            add_type = sub_args[0].lower()
            value = sub_args[1:] # Remaining parts form the value/content

            if add_type == "file":
                file_path = value[0]
                # Basic validation: check if file exists (optional, can be noisy)
                # if not os.path.isfile(file_path):
                #     print(f"Warning: File not found at '{file_path}'. Adding anyway.")
                cli_context["files"].add(file_path)
                print(f"Added file context: {file_path}")
            elif add_type == "folder":
                folder_path = value[0]
                # Basic validation: check if folder exists (optional)
                # if not os.path.isdir(folder_path):
                #     print(f"Warning: Folder not found at '{folder_path}'. Adding anyway.")
                cli_context["folders"].add(folder_path)
                print(f"Added folder context: {folder_path}")
            elif add_type == "url":
                url = value[0]
                # Basic validation could be added here (e.g., regex)
                cli_context["urls"].add(url)
                print(f"Added URL context: {url}")
            elif add_type == "snippet":
                if len(value) < 2:
                    print("Usage: /context add snippet <name> <content...>")
                    return None # Indicate no mode change
                snippet_name = value[0]
                snippet_content = " ".join(value[1:])
                cli_context["snippets"][snippet_name] = snippet_content
                print(f"Added snippet context: '{snippet_name}'")
            else:
                print(f"Unknown context type to add: '{add_type}'. Use file, folder, url, or snippet.")

        elif subcommand == "remove":
            if len(sub_args) < 2:
                print(f"Usage: /context remove <file|folder|url|snippet> <value_or_name>")
                return None # Indicate no mode change
            remove_type = sub_args[0].lower()
            identifier = sub_args[1] # Path, URL, or snippet name

            item_removed = False
            if remove_type == "file":
                if identifier in cli_context["files"]:
                    cli_context["files"].remove(identifier)
                    item_removed = True
            elif remove_type == "folder":
                 if identifier in cli_context["folders"]:
                    cli_context["folders"].remove(identifier)
                    item_removed = True
            elif remove_type == "url":
                 if identifier in cli_context["urls"]:
                    cli_context["urls"].remove(identifier)
                    item_removed = True
            elif remove_type == "snippet":
                 if identifier in cli_context["snippets"]:
                    del cli_context["snippets"][identifier]
                    item_removed = True
            else:
                print(f"Unknown context type to remove: '{remove_type}'. Use file, folder, url, or snippet.")
                return None # Indicate no mode change

            if item_removed:
                print(f"Removed {remove_type} context: {identifier}")
            else:
                print(f"{remove_type.capitalize()} context not found: {identifier}")

        elif subcommand == "clear":
            clear_type = sub_args[0].lower() if sub_args else "all"

            cleared_something = False
            if clear_type in ["all", "files"]:
                if cli_context["files"]:
                    cli_context["files"].clear()
                    print("Cleared file context.")
                    cleared_something = True
            if clear_type in ["all", "folders"]:
                 if cli_context["folders"]:
                    cli_context["folders"].clear()
                    print("Cleared folder context.")
                    cleared_something = True
            if clear_type in ["all", "urls"]:
                 if cli_context["urls"]:
                    cli_context["urls"].clear()
                    print("Cleared URL context.")
                    cleared_something = True
            if clear_type in ["all", "snippets"]:
                 if cli_context["snippets"]:
                    cli_context["snippets"].clear()
                    print("Cleared snippet context.")
                    cleared_something = True

            if not cleared_something and clear_type != "all":
                 print(f"No {clear_type} context found to clear.")
            elif clear_type == "all" and not cleared_something:
                 print("Context was already empty.")
            elif clear_type not in ["all", "files", "folders", "urls", "snippets"]:
                 print(f"Unknown context type to clear: '{clear_type}'. Use file, folder, url, snippet, or all.")

        else:
            print(f"Unknown /context subcommand: '{subcommand}'. Use show, add, remove, clear, or help.")

    # %% Added: Mode switching status command
    elif command == "/mode-switch-status":
        status = "enabled" if global_allow_mode_switching else "disabled"
        print(f"Mode switching is currently {status} (based on configuration).")

    # %% Added: /watch command handling
    elif command == "/watch":
        if not file_watcher:
            print("Error: File watcher is not initialized.")
            logger.error("Attempted /watch command but file_watcher is None.")
            return None # Indicate no mode change

        if not args:
            print("Usage: /watch <start|stop|status> [paths...]")
            return None # Indicate no mode change

        subcommand = args[0].lower()
        watch_args = args[1:]

        if subcommand == "start":
            if not watch_args:
                print("Usage: /watch start <path1> [path2...]")
                return None # Indicate no mode change
            added_count = 0
            for path in watch_args:
                if file_watcher.add_watch(path):
                    added_count += 1
            print(f"Added {added_count} path(s) to watcher.")
            if not file_watcher.is_running() and added_count > 0:
                 print("Starting watcher thread...")
                 file_watcher.start()
            elif not file_watcher.is_running() and added_count == 0:
                 print("No valid paths added, watcher not started.")
            elif file_watcher.is_running():
                 print("Watcher is already running.")

        elif subcommand == "stop":
            if not watch_args:
                # Stop watching all paths and stop the thread
                print("Stopping watcher and clearing all watched paths...")
                watched = file_watcher.get_watched_paths()
                removed_count = 0
                for path in list(watched): # Iterate over a copy
                    if file_watcher.remove_watch(path):
                        removed_count += 1
                if file_watcher.is_running():
                    file_watcher.stop()
                print(f"Removed {removed_count} path(s). Watcher stopped.")
            else:
                # Stop watching specific paths
                removed_count = 0
                for path in watch_args:
                    if file_watcher.remove_watch(path):
                        removed_count += 1
                print(f"Removed {removed_count} path(s) from watcher.")
                # Optionally stop the thread if no paths are left?
                if not file_watcher.get_watched_paths() and file_watcher.is_running():
                     print("No paths left to watch. Stopping watcher thread...")
                     file_watcher.stop()

        elif subcommand == "status":
            if file_watcher.is_running():
                print("Watcher status: Running")
                watched = file_watcher.get_watched_paths()
                if watched:
                    print("Watching paths:")
                    for path in sorted(list(watched)):
                        print(f"  - {path}")
                else:
                    print("Watching paths: (None)")
            else:
                print("Watcher status: Stopped")
                # Still show paths that *would* be watched if started
                watched = file_watcher.get_watched_paths()
                if watched:
                     print("Paths configured for watching (if started):")
                     for path in sorted(list(watched)):
                         print(f"  - {path}")

        else:
            print(f"Unknown /watch subcommand: '{subcommand}'. Use start, stop, or status.")


    else:
        logger.warning(f"Unknown command: {command}")
        print(f"Unknown command: {command}")
        print_help() # Show help for unknown commands

    return new_mode_instance # Return the new mode instance if switched, else None


def print_help():
    """Prints the available CLI commands."""
    # MODIFIED: Removed /allow, /disallow and related notes
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

# %% Added: Helper function for /context help
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