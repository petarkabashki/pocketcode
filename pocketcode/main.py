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
# %% Added import for extracted command handler
from pocketcode.cli.command_handler import handle_command

# --- Global State (Placeholder) ---
current_mode_instance = None
registered_components = {} # To store modes and tools globally for commands
# REMOVED: auto_allowed_tools = {"__global__": {"__all__": False}}
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
                        "watched_file_content": file_content,
                        # Pass global config to the mode's process_request
                        "global_config": config,
                        # Pass tool registry from registered_components
                        "tool_registry": registered_components.get('tools', {})
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
    # Declare intent to modify globals needed within this function or passed down
    global memory_manager
    global instruction_queue
    global file_watcher
    global global_allow_mode_switching
    global registered_components
    global current_mode_instance
    global cli_context # cli_context is modified by handle_command, keep global for now

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
        # Store components globally - needed for context and command handler
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
                # Also pass global config and tool registry needed by the flow
                # Assign to the global variable
                current_mode_instance = ModeClass(
                    config=mode_config,
                    memory_manager=memory_manager, # Pass manager (or None)
                    global_config=config, # Pass global config
                    tool_registry=registered_tools # Pass tool registry
                )
                logger.info(f"Successfully started in mode: {current_mode_instance.display_name}")
            except TypeError as e:
                 # Handle cases where ModeClass doesn't accept new args yet
                 if 'global_config' in str(e) or 'tool_registry' in str(e):
                      logger.warning(f"Mode '{initial_mode_slug}' does not seem to accept 'global_config' or 'tool_registry'. Instantiating without them. Error: {e}")
                      # Fallback to original instantiation if new args fail
                      current_mode_instance = ModeClass(config=mode_config, memory_manager=memory_manager)
                      logger.info(f"Successfully started in mode (fallback): {current_mode_instance.display_name}")
                 elif 'memory_manager' in str(e):
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
                # %% Call the extracted command handler
                # Pass all necessary state and configuration
                returned_mode_instance = handle_command(
                    command_input=user_input,
                    config=config,
                    memory_manager=memory_manager,
                    file_watcher=file_watcher,
                    current_mode_instance=current_mode_instance,
                    registered_components=registered_components,
                    cli_context=cli_context, # Pass the global context dict
                    global_allow_mode_switching=global_allow_mode_switching
                )
                # Update the global instance if the command handler returned a new one (mode switch)
                if returned_mode_instance:
                    current_mode_instance = returned_mode_instance
            elif current_mode_instance:
                logger.info(f"Processing request with {current_mode_instance.display_name}...")
                # %% Modified: Include cli_context, global_config, and tool_registry in the context passed to the mode
                context = {
                    "user_id": "cli_user",
                    "session_id": "cli_session",
                    "cli_context": cli_context, # Pass the managed context
                    "global_config": config, # Pass the global config
                    "tool_registry": registered_tools # Pass the tool registry
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

# --- Command Handling Functions Removed ---
# handle_command, print_help, print_context_help were moved to pocketcode.cli.command_handler


if __name__ == "__main__":
    run()