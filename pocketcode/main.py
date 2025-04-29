# pocketcode/main.py
import sys
import json
import argparse # Added for CLI argument parsing
import logging
import os # Added for CWD and path operations
import queue # %% Added for watcher queue
import time # %% Added for potential delays/timing

# Updated imports
from pocketcode.config.loader import load_settings
from pocketcode.core.registration import register_components
# Removed MemoryBankIncompleteError import, kept MemoryBankManager
from pocketcode.core.memory_bank import MemoryBankManager
from pocketcode.core.watcher import FileWatcher # %% Added watcher import

# --- Global State (Placeholder) ---
current_mode_instance = None
registered_components = {} # To store modes and tools globally for commands
# Refactored: Nested structure for global and per-mode auto-approval
auto_allowed_tools = {"__global__": {"__all__": False}}
memory_manager = None # Global placeholder for memory manager instance
global_allow_mode_switching = True # Default value, will be updated from config
# %% Added: Global dictionary for CLI-managed context
cli_context = {
    "files": set(),
    "folders": set(),
    "urls": set(),
    "snippets": {}
}
# %% Added: Watcher globals
instruction_queue = None
file_watcher = None

# Basic logging setup
# Ensure log level respects config later if needed
log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper() # Example default
logging.basicConfig(level=getattr(logging, log_level_str, logging.INFO),
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# %% Added: Helper function to process watcher queue items
def process_watcher_queue(instruction_queue, config, current_mode_instance, cli_context):
    """Checks the watcher queue and processes one instruction if available."""
    try:
        event_data = instruction_queue.get_nowait()
        logger.info(f"Processing event from watcher queue: {event_data.get('type')}")

        if event_data.get("type") == "instruction":
            filepath = event_data["filepath"]
            instruction = event_data["instruction"]
            watch_config = config.get('watch_mode', {})
            ask_confirmation = watch_config.get('ask_confirmation', True)

            proceed = False
            if ask_confirmation:
                # Temporarily log confirmation request instead of blocking input here
                # Proper async input handling would be needed for a seamless experience
                logger.info(f"Confirmation needed for watched instruction in '{filepath}': '{instruction}'")
                # For now, let's assume 'y' for testing, replace with actual input if possible non-blockingly
                # confirm = input(f"Detected 'AI!' instruction in '{filepath}': '{instruction}'. Process? (y/n) ").lower()
                print(f"\n[Watcher] Detected 'AI!' instruction in '{filepath}': '{instruction}'.")
                confirm = input(f"[Watcher] Process? (y/n) > ").strip().lower()
                if confirm == 'y':
                    proceed = True
                else:
                    logger.info("User declined processing watched instruction.")
                    print("[Watcher] Instruction processing declined.")
            else:
                proceed = True # Process automatically if confirmation not required
                print(f"\n[Watcher] Auto-processing instruction from '{filepath}': '{instruction}'")


            if proceed and current_mode_instance:
                logger.info(f"Processing watched instruction from {filepath}...")
                try:
                    # Read the *current* content
                    # Add a small delay in case the file is still being written
                    time.sleep(0.1)
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        file_content = f.read()

                    # Prepare context
                    context = {
                        "user_id": "cli_user",
                        "session_id": "cli_session",
                        "cli_context": cli_context, # Pass original context dict
                        "watched_file_path": filepath,
                        "watched_file_content": file_content
                    }

                    # Process the request
                    print(f"[Watcher] Sending instruction to {current_mode_instance.display_name}...")
                    result = current_mode_instance.process_request(instruction, context)
                    logger.info(f"Response from {current_mode_instance.display_name} (triggered by watch):")
                    # Print clearly marked output
                    print(f"\n--- Watch Trigger Result ({os.path.basename(filepath)}) ---")
                    print(result)
                    print("--- End Watch Trigger Result ---")

                except FileNotFoundError:
                    logger.error(f"File not found when trying to process watched instruction: {filepath}")
                    print(f"[Watcher Error] File not found: {filepath}")
                except Exception as e:
                    logger.error(f"Error processing watched instruction from {filepath}: {e}", exc_info=True)
                    print(f"[Watcher Error] Error processing instruction from {filepath}. See logs.")

        # Mark task as done *after* processing attempt
        instruction_queue.task_done()
        return True # Indicate an item was processed

    except queue.Empty:
        # No items in the queue, continue normally
        return False
    except Exception as e:
        # Catch other potential errors during queue processing
        logger.error(f"Error processing watcher queue: {e}", exc_info=True)
        print("[Watcher Error] An unexpected error occurred processing the queue. See logs.")
        # Attempt to mark task done even if there was an error during processing
        try:
             instruction_queue.task_done()
        except ValueError: # If task_done() called when queue is empty/no pending task
             pass
        return False # Indicate no item successfully processed


def run():
    """Main entry point for Pocketcode."""
    logger.info("--- Starting Pocketcode ---")
    global memory_manager # Declare intent to modify global
    # %% Added watcher globals modification
    global instruction_queue
    global file_watcher

    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="Pocketcode AI Assistant CLI")
    parser.add_argument("--mode", help="Specify the starting mode slug.", default='code') # Default to 'code'
    args = parser.parse_args()

    # Load configuration using the new loader
    try:
        config = load_settings()
        if not config:
            logger.error("Failed to load configuration or configuration is empty. Exiting.")
            sys.exit(1)
        # Update logging level based on config if present
        core_config_temp = config.get('core', {})
        log_level_config = core_config_temp.get('log_level', 'INFO').upper()
        numeric_level = getattr(logging, log_level_config, None)
        if isinstance(numeric_level, int):
             logging.getLogger().setLevel(numeric_level)
             logger.info(f"Logging level set to {log_level_config}")
        else:
             logger.warning(f"Invalid log level '{log_level_config}' in config. Using default.")
# Read mode switching setting
        global global_allow_mode_switching
        global_allow_mode_switching = core_config_temp.get('allow_mode_switching', True) # Default to True if missing
        logger.info(f"Mode switching allowed: {global_allow_mode_switching}")

    except FileNotFoundError as e:
         logger.error(f"Configuration file not found: {e}. Exiting.")
         sys.exit(1)
    except Exception as e:
         logger.error(f"An unexpected error occurred loading configuration: {e}. Exiting.")
         sys.exit(1)

    logger.info("Configuration Loaded.")
    try:
        logger.debug("Full Config:\n%s", json.dumps(config, indent=2))
    except TypeError as e:
         logger.error(f"Error serializing config to JSON: {e}")
         logger.debug("Raw config: %s", config) # Log raw config if JSON fails

    # --- Memory Bank Initialization and Verification --- Modified Section ---
    memory_manager = None # Default to None
    try:
        project_root = os.getcwd()
        core_config = config.get('core', {})
        # Check if memory bank is enabled in config
        if core_config.get('enable_memory_bank', False):
            if 'memory_bank_dir' in core_config and 'memory_bank_files' in core_config:
                memory_manager = MemoryBankManager(core_config, project_root)
                # verify_and_prepare now handles creation and logs warnings, doesn't raise for missing files
                memory_manager.verify_and_prepare()
            else:
                logger.warning("Memory bank enabled but configuration keys ('memory_bank_dir', 'memory_bank_files') missing. Memory bank inactive.")
        else:
             logger.info("Memory bank is disabled in configuration.")

    except OSError as e: # Catch potential directory creation errors from verify_and_prepare
         logger.error(f"Failed to prepare memory bank directory: {e}. Exiting.")
         sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred during memory bank initialization: {e}", exc_info=True)
        # Decide if this should be fatal - for now, let's make it non-fatal but log error
        logger.error("Proceeding without memory bank due to initialization error.")
        memory_manager = None # Ensure manager is None if setup failed
    # --- End Memory Bank Section ---

    # %% --- Watcher Initialization ---
    watch_mode_config = config.get('watch_mode', {})
    instruction_queue = queue.Queue()
    file_watcher = FileWatcher(instruction_queue, watch_mode_config)
    # Note: Watcher is not started here by default based on plan. Use /watch start.
    logger.info("File watcher initialized.")
    # %% --- End Watcher Initialization ---


    logger.info("Registering Components...")
    try:
        global registered_components # Store components globally
        registered_components = register_components(config) # Pass the loaded config
    except Exception as e:
        logger.error(f"Registered components: {registered_components}") # Log what was registered before error
        logger.error(f"An error occurred during component registration: {e}. Exiting.")
        sys.exit(1)

    logger.info("Registered Components Summary:")
    registered_modes = registered_components.get('modes', {})
    registered_tools = registered_components.get('tools', {})
    logger.info(f"  Modes: {list(registered_modes.keys())}")
    logger.info(f"  Tools: {list(registered_tools.keys())}")

    # --- Initial Mode Setup ---
    initial_mode_slug = args.mode
    logger.info(f"\n--- Attempting to start in '{initial_mode_slug}' mode ---")

    if initial_mode_slug in registered_modes:
        ModeClass = registered_modes[initial_mode_slug]
        mode_config = config.get('modes', {}).get(initial_mode_slug, {})

        if not mode_config:
            logger.error(f"Configuration for mode '{initial_mode_slug}' not found in settings. Cannot start.")
            sys.exit(1)
        else:
            try:
                mode_config['slug'] = initial_mode_slug
                # Instantiate the mode, passing the memory manager (which might be None)
                global current_mode_instance
                current_mode_instance = ModeClass(config=mode_config, memory_manager=memory_manager) # Pass manager (or None)
                logger.info(f"Successfully started in mode: {current_mode_instance.display_name}")
            except TypeError as e:
                 if 'memory_manager' in str(e):
                      logger.warning(f"Mode '{initial_mode_slug}' does not seem to accept 'memory_manager' argument. Instantiating without it. Error: {e}")
                      current_mode_instance = ModeClass(config=mode_config) # Fallback
                      logger.info(f"Successfully started in mode (without memory manager): {current_mode_instance.display_name}")
                 else:
                      logger.error(f"Error instantiating mode '{initial_mode_slug}': {e}", exc_info=True)
                      sys.exit(1)
            except Exception as e:
                logger.error(f"Error instantiating mode '{initial_mode_slug}': {e}", exc_info=True)
                sys.exit(1)
    else:
        logger.error(f"Initial mode '{initial_mode_slug}' not found in registered modes. Exiting.")
        sys.exit(1)

    # --- Interactive CLI Loop ---
    logger.info("\n--- Pocketcode Ready. Enter your request or a command (starting with /). ---")
    while True:
        processed_queue_item = False
        try:
            # %% Check watcher queue before prompting for input
            # Keep checking queue until it's empty or an error occurs
            while True:
                 item_processed_this_cycle = process_watcher_queue(instruction_queue, config, current_mode_instance, cli_context)
                 if item_processed_this_cycle:
                     processed_queue_item = True # Mark that we did something from the queue
                 else:
                     break # Queue is empty or error occurred, break inner loop

            # If we processed an item, show the prompt again without waiting for input immediately
            # This provides a chance to see the output before the next input prompt blocks
            if processed_queue_item:
                 print(f"\n({getattr(current_mode_instance, 'display_name', 'unknown')}) > ", end='', flush=True)
                 # We could potentially add a small sleep here if needed, but let's try without first.
                 # time.sleep(0.1)


            if not current_mode_instance:
                 logger.error("Critical error: No active mode instance. Exiting.")
                 break
            # Use display_name if available, otherwise slug
            mode_prompt_name = getattr(current_mode_instance, 'display_name', getattr(current_mode_instance, 'name', 'unknown'))

            # Get user input (this will block)
            user_input = input(f"({mode_prompt_name}) > ")
            if not user_input:
                continue

            if user_input.startswith('/'):
                # %% Pass file_watcher to handle_command
                handle_command(user_input, config, memory_manager, file_watcher)
            elif current_mode_instance:
                logger.info(f"Processing request with {current_mode_instance.display_name}...")
                # %% Modified: Include cli_context in the context passed to the mode
                context = {
                    "user_id": "cli_user",
                    "session_id": "cli_session",
                    "cli_context": cli_context # Pass the managed context
                }
                result = current_mode_instance.process_request(user_input, context)
                logger.info(f"Response from {current_mode_instance.display_name}:")
                print(result)
            else:
                logger.error("No active mode to process the request.")

        except KeyboardInterrupt:
            logger.info("\nStopping watcher...")
            if file_watcher and file_watcher.is_running():
                file_watcher.stop() # %% Ensure watcher stops on exit
            logger.info("Exiting Pocketcode.")
            break
        except Exception as e:
            logger.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
            # %% Ensure watcher stops on unexpected exit too
            logger.info("\nStopping watcher due to error...")
            if file_watcher and file_watcher.is_running():
                file_watcher.stop()
            break # Exit loop on error

# --- Helper Function for Auto-Allow Check ---
def is_tool_auto_allowed(tool_name, mode_slug=None):
    """Checks if a tool is auto-allowed, considering mode-specific overrides."""
    global auto_allowed_tools

    # 1. Check mode-specific tool setting
    if mode_slug and mode_slug in auto_allowed_tools:
        mode_settings = auto_allowed_tools[mode_slug]
        if tool_name in mode_settings:
            return mode_settings[tool_name]
        # 2. Check mode-specific __all__ setting
        if mode_settings.get("__all__", False): # Default to False if __all__ not explicitly set for mode
             return True

    # 3. Check global tool setting
    global_settings = auto_allowed_tools.get("__global__", {})
    if tool_name in global_settings:
        return global_settings[tool_name]

    # 4. Check global __all__ setting
    return global_settings.get("__all__", False)

# --- Command Handling ---
# %% Modified signature to accept file_watcher
def handle_command(command_input, config, memory_manager, file_watcher):
    """Parses and executes CLI commands."""
    parts = command_input.strip().split()
    command = parts[0].lower()
    args = parts[1:]

    logger.debug(f"Handling command: {command} with args: {args}")

    global current_mode_instance
    global registered_components
    global auto_allowed_tools
    # %% Added: Make cli_context accessible
    global cli_context
    # Access the global mode switching setting
    global global_allow_mode_switching

    registered_modes = registered_components.get('modes', {})
    registered_tools = registered_components.get('tools', {})

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
            return

        if not args:
            logger.warning("Usage: /mode <mode_slug>")
            print("Please specify a mode slug. Available modes:", list(registered_modes.keys()))
            return
        target_mode_slug = args[0]
        # Use slug for comparison
        current_slug = getattr(current_mode_instance, 'slug', None)
        if current_slug and target_mode_slug == current_slug:
             print(f"Already in mode '{target_mode_slug}'.")
             return
        if target_mode_slug in registered_modes:
            ModeClass = registered_modes[target_mode_slug]
            mode_config = config.get('modes', {}).get(target_mode_slug, {})
            if not mode_config:
                logger.error(f"Configuration for mode '{target_mode_slug}' not found.")
                print(f"Error: Configuration missing for mode '{target_mode_slug}'.")
                return
            try:
                mode_config['slug'] = target_mode_slug # Ensure slug is in config for the instance
                # Pass memory_manager (could be None) when switching modes
                current_mode_instance = ModeClass(config=mode_config, memory_manager=memory_manager)
                logger.info(f"Switched to mode: {current_mode_instance.display_name}")
                print(f"Switched to mode: {current_mode_instance.display_name}")
            except TypeError as e:
                 if 'memory_manager' in str(e):
                      logger.warning(f"Mode '{target_mode_slug}' does not seem to accept 'memory_manager' argument. Instantiating without it. Error: {e}")
                      current_mode_instance = ModeClass(config=mode_config) # Fallback
                      logger.info(f"Switched to mode (without memory manager): {current_mode_instance.display_name}")
                      print(f"Switched to mode (without memory manager): {current_mode_instance.display_name}")
                 else:
                      logger.error(f"Error switching to mode '{target_mode_slug}': {e}", exc_info=True)
                      print(f"Error switching to mode '{target_mode_slug}'.")
            except Exception as e:
                logger.error(f"Error switching to mode '{target_mode_slug}': {e}", exc_info=True)
                print(f"Error switching to mode '{target_mode_slug}'.")
        else:
            logger.warning(f"Mode '{target_mode_slug}' not found.")
            print(f"Unknown mode: '{target_mode_slug}'. Available modes:", list(registered_modes.keys()))

    elif command == "/tools": # Updated logic for checking auto-allow status
        show_all = "--all" in args
        current_slug = getattr(current_mode_instance, 'slug', None)

        if show_all:
            print("All Registered Tools:")
            if registered_tools:
                for tool_name in sorted(registered_tools.keys()):
                    # Check global status only for --all
                    allowed = is_tool_auto_allowed(tool_name) # Check global only
                    status = "(allowed)" if allowed else ""
                    print(f"  - {tool_name} {status}")
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
                             # Check status considering current mode
                             allowed = is_tool_auto_allowed(tool_name, current_slug)
                             status = "(allowed)" if allowed else ""
                             print(f"  - {tool_name} {status}")
                         else:
                             print(f"  - {tool_name} (Warning: Configured but not registered)")
                else:
                    print("  (No tools specifically configured for this mode)")
            except AttributeError:
                 logger.error(f"Could not retrieve tool list from mode {current_mode_instance.display_name}. Does it have a 'config' attribute with a 'allowed_tools' key?")
                 print("  (Error retrieving tool list for this mode)")
        else:
             print("Error: No active mode to list tools for.")

    elif command == "/allow" or command == "/disallow": # Combined and refactored /allow and /disallow
        allow_action = command == "/allow"
        target_tool = None
        target_modes = []
        apply_globally = True # Default to global if --mode is not specified

        # Parse arguments for tool name and --mode flag
        mode_flag_index = -1
        if "--mode" in args:
            mode_flag_index = args.index("--mode")
            if mode_flag_index == 0: # --mode cannot be the first argument if a tool is expected
                 print(f"Usage: {command} [<tool_name>] [--mode <mode1> <mode2> ...]")
                 return
            target_tool = args[0] if mode_flag_index > 0 else None
            target_modes = args[mode_flag_index + 1:]
            apply_globally = False
            if not target_modes:
                 print("Error: --mode flag requires at least one mode slug.")
                 return
        elif args: # If args exist but no --mode flag, the first arg is the tool
             target_tool = args[0]

        # Validate target modes
        invalid_modes = [m for m in target_modes if m not in registered_modes]
        if invalid_modes:
            print(f"Error: Unknown mode(s): {', '.join(invalid_modes)}. Available: {list(registered_modes.keys())}")
            return

        # Determine the scope (global or specific modes)
        scopes_to_update = target_modes if not apply_globally else ["__global__"]
        scope_names_for_msg = target_modes if not apply_globally else ["globally"]

        if target_tool:
            # Apply to a specific tool
            if target_tool not in registered_tools:
                print(f"Error: Tool '{target_tool}' not registered.")
                return

            for scope in scopes_to_update:
                if scope not in auto_allowed_tools:
                    auto_allowed_tools[scope] = {} # Initialize if mode scope doesn't exist
                auto_allowed_tools[scope]["__all__"] = False # Setting a specific tool overrides __all__ for the scope
                auto_allowed_tools[scope][target_tool] = allow_action
                action_str = "Auto-allowing" if allow_action else "Disabling auto-approval for"
                print(f"{action_str} tool '{target_tool}' for scope: {scope}")
                logger.info(f"Set auto-allow={allow_action} for tool '{target_tool}' in scope '{scope}'")

        else:
            # Apply to all tools (__all__)
            for scope in scopes_to_update:
                if scope not in auto_allowed_tools:
                    auto_allowed_tools[scope] = {} # Initialize if mode scope doesn't exist
                # Clear specific tool settings when setting __all__ for the scope
                keys_to_remove = [k for k in auto_allowed_tools[scope] if k != "__all__"]
                for k in keys_to_remove:
                    del auto_allowed_tools[scope][k]
                auto_allowed_tools[scope]["__all__"] = allow_action
                action_str = "Auto-allowing ALL" if allow_action else "Disabling auto-approval for ALL"
                print(f"{action_str} tools for scope: {scope}.")
                logger.info(f"Set auto-allow __all__={allow_action} for scope '{scope}'")

    # %% Added: /context command handling
    elif command == "/context":
        if not args:
            print("Usage: /context <show|add|remove|clear> [options...]")
            print("Run '/context help' for more details.")
            return

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
                return
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
                    return
                snippet_name = value[0]
                snippet_content = " ".join(value[1:])
                cli_context["snippets"][snippet_name] = snippet_content
                print(f"Added snippet context: '{snippet_name}'")
            else:
                print(f"Unknown context type to add: '{add_type}'. Use file, folder, url, or snippet.")

        elif subcommand == "remove":
            if len(sub_args) < 2:
                print(f"Usage: /context remove <file|folder|url|snippet> <value_or_name>")
                return
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
                return

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
            return

        if not args:
            print("Usage: /watch <start|stop|status> [paths...]")
            return

        subcommand = args[0].lower()
        watch_args = args[1:]

        if subcommand == "start":
            if not watch_args:
                print("Usage: /watch start <path1> [path2...]")
                return
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

def print_help():
    """Prints the available CLI commands."""
    # %% Modified: Added /watch commands to help
    help_text = """
Pocketcode Commands:
  /help                    Show this help message.
  /mode <mode_slug>        Switch to the specified mode (if enabled).
  /modes [<m1> <m2> ...]   List allowed tools for specified modes (or all modes).
  /tools [--all]           List tools for current mode (or all registered tools).
                           Shows (allowed) status based on auto-approval settings.
  /allow [<t>] [--mode <m>] Allow auto-approval for tool <t> (or all tools if <t> omitted).
                           Applies globally or only to specified modes <m> if --mode is used.
  /disallow [<t>] [--mode <m>] Disallow auto-approval for tool <t> (or all tools if <t> omitted).
                           Applies globally or only to specified modes <m> if --mode is used.
  /context <cmd> [opts]    Manage CLI context (files, folders, urls, snippets). Run '/context help'.
  /watch start <p1> [<p2>..] Start watching specified file(s) or directorie(s).
  /watch stop [<p1> <p2>..] Stop watching specified path(s), or all paths if none given.
  /watch status            Show if the watcher is running and list watched paths.
  /create-memory-bank    Create the memory bank directory and required empty files (if configured).
  /mode-switch-status    Show if mode switching is currently enabled or disabled by configuration.
  Ctrl+C                   Exit Pocketcode.

Note: Auto-allow status controls whether tool execution requires confirmation (if enabled globally).
      It does not change the fundamental list of tools a mode *can* use, defined in settings.
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


if __name__ == "__main__":
    run()