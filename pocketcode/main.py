# pocketcode/main.py
import sys
import json
import argparse # Added for CLI argument parsing
import logging
import os # Added for CWD and path operations

# Updated imports
from pocketcode.config.loader import load_settings
from pocketcode.core.registration import register_components
# Removed MemoryBankIncompleteError import, kept MemoryBankManager
from pocketcode.core.memory_bank import MemoryBankManager

# --- Global State (Placeholder) ---
current_mode_instance = None
registered_components = {} # To store modes and tools globally for commands
# Refactored: Nested structure for global and per-mode auto-approval
auto_allowed_tools = {"__global__": {"__all__": False}}
memory_manager = None # Global placeholder for memory manager instance

# Basic logging setup
# Ensure log level respects config later if needed
log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper() # Example default
logging.basicConfig(level=getattr(logging, log_level_str, logging.INFO),
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run():
    """Main entry point for Pocketcode."""
    logger.info("--- Starting Pocketcode ---")
    global memory_manager # Declare intent to modify global

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
        try:
            if not current_mode_instance:
                 logger.error("Critical error: No active mode instance. Exiting.")
                 break
            # Use display_name if available, otherwise slug
            mode_prompt_name = getattr(current_mode_instance, 'display_name', getattr(current_mode_instance, 'name', 'unknown'))
            user_input = input(f"({mode_prompt_name}) > ")
            if not user_input:
                continue

            if user_input.startswith('/'):
                # Pass memory_manager (could be None) to handle_command
                handle_command(user_input, config, memory_manager)
            elif current_mode_instance:
                logger.info(f"Processing request with {current_mode_instance.display_name}...")
                context = {"user_id": "cli_user", "session_id": "cli_session"}
                result = current_mode_instance.process_request(user_input, context)
                logger.info(f"Response from {current_mode_instance.display_name}:")
                print(result)
            else:
                logger.error("No active mode to process the request.")

        except KeyboardInterrupt:
            logger.info("\nExiting Pocketcode.")
            break
        except Exception as e:
            logger.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)

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
# Signature remains the same, memory_manager can be None
def handle_command(command_input, config, memory_manager):
    """Parses and executes CLI commands."""
    parts = command_input.strip().split()
    command = parts[0].lower()
    args = parts[1:]

    logger.debug(f"Handling command: {command} with args: {args}")

    global current_mode_instance
    global registered_components
    global auto_allowed_tools

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

    else:
        logger.warning(f"Unknown command: {command}")
        print(f"Unknown command: {command}")
        print_help() # Show help for unknown commands

def print_help():
    """Prints the available CLI commands."""
    # Updated help text
    help_text = """
Pocketcode Commands:
  /help                    Show this help message.
  /mode <mode_slug>        Switch to the specified mode.
  /modes [<m1> <m2> ...]   List allowed tools for specified modes (or all modes).
  /tools [--all]           List tools for current mode (or all registered tools).
                           Shows (allowed) status based on auto-approval settings.
  /allow [<t>] [--mode <m>] Allow auto-approval for tool <t> (or all tools if <t> omitted).
                           Applies globally or only to specified modes <m> if --mode is used.
  /disallow [<t>] [--mode <m>] Disallow auto-approval for tool <t> (or all tools if <t> omitted).
                           Applies globally or only to specified modes <m> if --mode is used.
  /create-memory-bank    Create the memory bank directory and required empty files (if configured).
  Ctrl+C                   Exit Pocketcode.

Note: Auto-allow status controls whether tool execution requires confirmation (if enabled globally).
      It does not change the fundamental list of tools a mode *can* use, defined in settings.
"""
    print(help_text)


if __name__ == "__main__":
    run()