# pocketcode/main.py
import sys
import json
import argparse
import logging
import os
import queue
import time
import typing # Added for Optional type hint

from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import NestedCompleter, WordCompleter, PathCompleter, Completion, Completer
from prompt_toolkit.document import Document

from pocketcode.config.loader import load_settings
from pocketcode.core.registration import register_components # Still needed for tools
from pocketcode.core.memory_bank import MemoryBankManager
from pocketcode.core.watcher import FileWatcher
from pocketcode.cli.command_handler import handle_command
# --- Import the new ModeManager ---
from pocketcode.core.mode_manager import ModeManager
# --- Import Flow for type hinting ---
from pocketflow import Flow

# --- Global State ---
# REMOVED: current_mode_instance = None
current_mode_slug: typing.Optional[str] = None # Store the slug of the active mode
registered_components = {} # Still used for tools and potentially passing to command handler
memory_manager: typing.Optional[MemoryBankManager] = None
mode_manager: typing.Optional[ModeManager] = None # Global placeholder for ModeManager instance
global_allow_mode_switching = True
cli_context = { "files": set(), "folders": set(), "urls": set(), "snippets": {} }
instruction_queue = None
file_watcher = None

# Basic logging setup
log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level_str, logging.INFO),
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# %% Helper function to process watcher queue items (Modified to use ModeManager)
def process_watcher_queue(instruction_queue, config, current_mode_slug, mode_manager, cli_context):
    """Checks the watcher queue and processes one instruction if available."""
    global memory_manager # Access global memory manager if needed by context prep
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
                logger.info(f"Confirmation needed for watched instruction in '{filepath}': '{instruction}'")
                print(f"\n[Watcher] Detected 'AI!' instruction in '{filepath}': '{instruction}'.")
                confirm = input(f"[Watcher] Process? (y/n) > ").strip().lower()
                if confirm == 'y':
                    proceed = True
                else:
                    logger.info("User declined processing watched instruction.")
                    print("[Watcher] Instruction processing declined.")
            else:
                proceed = True
                print(f"\n[Watcher] Auto-processing instruction from '{filepath}': '{instruction}'")


            # Check if mode_manager and current_mode_slug are valid
            if proceed and mode_manager and current_mode_slug:
                logger.info(f"Processing watched instruction from {filepath} with mode '{current_mode_slug}'...")
                try:
                    time.sleep(0.1) # Delay for file write completion
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        file_content = f.read()

                    # --- Prepare context using ModeManager ---
                    initial_context = {
                        "user_id": "cli_user",
                        "session_id": "cli_session",
                        "cli_context": cli_context,
                        "watched_file_path": filepath,
                        "watched_file_content": file_content,
                        "initial_request": instruction # Pass instruction as initial request
                        # global_config, tool_registry, llm_client etc. are added by prepare_initial_store
                    }
                    shared_store = mode_manager.prepare_initial_store(current_mode_slug, initial_context)
                    flow_structure = mode_manager.get_flow_structure(current_mode_slug)

                    if not flow_structure or not shared_store:
                         logger.error(f"Failed to get flow or store for watched instruction (mode: {current_mode_slug}).")
                         print(f"[Watcher Error] Could not prepare flow for mode '{current_mode_slug}'.")
                         instruction_queue.task_done()
                         return True # Item processed (failed)

                    # --- Execute the flow ---
                    mode_display_name = shared_store.get("mode_config", {}).get("display_name", current_mode_slug)
                    print(f"[Watcher] Sending instruction to {mode_display_name}...")
                    flow_structure.run(shared_store) # Run the flow
                    result = shared_store.get("final_output", "[Watcher Error] Flow finished but no final_output set.")
                    # --- End Flow Execution ---

                    logger.info(f"Response from {mode_display_name} (triggered by watch):")
                    print(f"\n--- Watch Trigger Result ({os.path.basename(filepath)}) ---")
                    print(result)
                    print("--- End Watch Trigger Result ---")

                except FileNotFoundError:
                    logger.error(f"File not found when trying to process watched instruction: {filepath}")
                    print(f"[Watcher Error] File not found: {filepath}")
                except Exception as e:
                    logger.error(f"Error processing watched instruction from {filepath}: {e}", exc_info=True)
                    print(f"[Watcher Error] Error processing instruction from {filepath}. See logs.")

        instruction_queue.task_done()
        return True # Indicate an item was processed

    except queue.Empty:
        return False
    except Exception as e:
        logger.error(f"Error processing watcher queue: {e}", exc_info=True)
        print("[Watcher Error] An unexpected error occurred processing the queue. See logs.")
        try:
             instruction_queue.task_done()
        except ValueError:
             pass
        return False


# %% Custom completer for dynamic snippet removal (Unchanged)
class SnippetRemoveCompleter(Completer):
    def get_completions(self, document: Document, complete_event):
        global cli_context
        snippet_names = list(cli_context.get('snippets', {}).keys())
        word_before_cursor = document.get_word_before_cursor()
        for name in snippet_names:
            if name.startswith(word_before_cursor):
                yield Completion(name, start_position=-len(word_before_cursor))

def run():
    """Main entry point for Pocketcode."""
    logger.info("--- Starting Pocketcode ---")
    # Declare globals
    global memory_manager, instruction_queue, file_watcher, global_allow_mode_switching
    global registered_components, current_mode_slug, cli_context, mode_manager # Added mode_manager

    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="Pocketcode AI Assistant CLI")
    parser.add_argument("--mode", help="Specify the starting mode slug.", default='koder') # Default to 'koder'
    args = parser.parse_args()

    # --- Load Configuration ---
    try:
        config = load_settings()
        if not config:
            logger.error("Failed to load configuration. Exiting.")
            sys.exit(1)
        core_config_temp = config.get('core', {})
        log_level_config = core_config_temp.get('log_level', 'INFO').upper()
        numeric_level = getattr(logging, log_level_config, None)
        if isinstance(numeric_level, int):
             logging.getLogger().setLevel(numeric_level)
             logger.info(f"Logging level set to {log_level_config}")
        else:
             logger.warning(f"Invalid log level '{log_level_config}'. Using default.")
        global_allow_mode_switching = core_config_temp.get('allow_mode_switching', True)
        logger.info(f"Mode switching allowed: {global_allow_mode_switching}")
    except Exception as e:
         logger.error(f"Error loading configuration: {e}. Exiting.", exc_info=True)
         sys.exit(1)
    logger.info("Configuration Loaded.")

    # --- Memory Bank Initialization --- (Unchanged logic)
    memory_manager = None
    try:
        project_root = os.getcwd()
        core_config = config.get('core', {})
        if core_config.get('enable_memory_bank', False):
            if 'memory_bank_dir' in core_config and 'memory_bank_files' in core_config:
                memory_manager = MemoryBankManager(core_config, project_root)
                memory_manager.verify_and_prepare()
            else:
                logger.warning("Memory bank enabled but config keys missing. Memory bank inactive.")
        else:
             logger.info("Memory bank is disabled in configuration.")
    except Exception as e:
        logger.error(f"Memory bank initialization error: {e}", exc_info=True)
        logger.error("Proceeding without memory bank.")
        memory_manager = None

    # --- Watcher Initialization --- (Unchanged logic)
    watch_mode_config = config.get('watch_mode', {})
    instruction_queue = queue.Queue()
    file_watcher = FileWatcher(instruction_queue, watch_mode_config)
    logger.info("File watcher initialized.")

    # --- Register Components (Tools primarily now) & Instantiate ModeManager ---
    logger.info("Registering Components...")
    try:
        # Register components (returns dict with 'modes' (paths) and 'tools' (classes))
        registered_components = register_components(config)
        registered_tools = registered_components.get('tools', {}) # Keep tool registry separate for now

        # --- Instantiate ModeManager ---
        mode_manager = ModeManager(
            global_config=config,
            tool_registry=registered_tools,
            memory_manager=memory_manager
        )
        # --- End ModeManager Instantiation ---

    except Exception as e:
        logger.error(f"Error during component registration or ModeManager init: {e}. Exiting.", exc_info=True)
        sys.exit(1)

    registered_mode_flow_paths = mode_manager.get_available_modes() # Get modes from manager
    logger.info("Registered Components Summary:")
    logger.info(f"  Mode Flow Paths: {list(registered_mode_flow_paths.keys())}")
    logger.info(f"  Tools: {list(registered_tools.keys())}")

    # --- Initial Mode Setup ---
    initial_mode_slug = args.mode
    logger.info(f"\n--- Attempting to start in '{initial_mode_slug}' mode ---")

    # Check if the initial mode slug is valid according to the ModeManager
    if initial_mode_slug in registered_mode_flow_paths:
        current_mode_slug = initial_mode_slug # Set the global slug
        initial_mode_config = registered_mode_flow_paths[initial_mode_slug]
        # Ensure initial_mode_config is a dictionary before accessing 'display_name'
        if isinstance(initial_mode_config, dict):
            initial_display_name = initial_mode_config.get('display_name', initial_mode_slug)
        else:
            # Handle case where mode config might not be a dict (though ModeManager should ensure it is)
            initial_display_name = initial_mode_slug
            logger.warning(f"Configuration for mode '{initial_mode_slug}' is not a dictionary. Using slug as display name.")

        logger.info(f"Successfully set initial mode to: {initial_display_name} ({current_mode_slug})")
    else:
        logger.error(f"Initial mode '{initial_mode_slug}' not found in registered modes. Exiting.")
        logger.error(f"Available modes: {list(registered_mode_flow_paths.keys())}")
        sys.exit(1)

    # --- prompt_toolkit Setup --- (Modified completer setup)
    logger.info("Setting up prompt_toolkit...")
    try:
        history_file_path = os.path.expanduser("~/.pocketcode_history")
        history = FileHistory(history_file_path)
        logger.info(f"Command history will be stored in: {history_file_path}")

        # Define completer structure using modes from ModeManager
        completer_dict = {
            '/help': None,
            '/mode': WordCompleter(list(registered_mode_flow_paths.keys())), # Use modes from manager
            '/modes': WordCompleter(list(registered_mode_flow_paths.keys())), # Use modes from manager
            '/tools': WordCompleter(['--all']),
            '/context': {
                'show': WordCompleter(['files', 'folders', 'urls', 'snippets', 'all']),
                'add': { 'file': PathCompleter(), 'folder': PathCompleter(), 'url': None, 'snippet': None },
                'remove': { 'file': PathCompleter(), 'folder': PathCompleter(), 'url': WordCompleter([]), 'snippet': SnippetRemoveCompleter() }, # Dynamic parts updated in loop
                'clear': WordCompleter(['files', 'folders', 'urls', 'snippets', 'all']),
                'help': None
            },
            '/watch': { 'start': PathCompleter(), 'stop': PathCompleter(), 'status': None },
            '/create-memory-bank': None,
            '/mode-switch-status': None
        }
        completer = NestedCompleter.from_nested_dict(completer_dict)
        logger.info("prompt_toolkit completer created.")
    except Exception as e:
        logger.error(f"Failed to initialize prompt_toolkit: {e}", exc_info=True)
        history = None
        completer = None
        auto_suggest = None
        use_prompt_toolkit = False
    else:
        auto_suggest = AutoSuggestFromHistory()
        use_prompt_toolkit = True

    # --- Interactive CLI Loop ---
    logger.info("\n--- Pocketcode Ready. Enter your request or a command (starting with /). ---")
    while True:
        processed_queue_item = False
        try:
            # Check watcher queue
            while True:
                 # Pass mode_manager to watcher processor
                 item_processed_this_cycle = process_watcher_queue(instruction_queue, config, current_mode_slug, mode_manager, cli_context)
                 if item_processed_this_cycle:
                     processed_queue_item = True
                 else:
                     break

            # Get current mode display name for prompt
            if not current_mode_slug or not mode_manager:
                 logger.error("Critical error: No active mode slug or mode manager. Exiting.")
                 break
            # Safely get current mode config and display name
            current_mode_config = mode_manager.get_available_modes().get(current_mode_slug)
            if isinstance(current_mode_config, dict):
                 mode_prompt_name = current_mode_config.get('display_name', current_mode_slug)
            else:
                 mode_prompt_name = current_mode_slug # Fallback if config isn't a dict
                 logger.warning(f"Mode config for '{current_mode_slug}' is not a dictionary.")


            if processed_queue_item:
                 print(f"\n({mode_prompt_name}) > ", end='', flush=True)

            # Get user input
            if use_prompt_toolkit:
                # Update dynamic completers
                completer_dict['/context']['remove']['url'] = WordCompleter(list(cli_context.get('urls', set())))
                completer = NestedCompleter.from_nested_dict(completer_dict)
                user_input = prompt( f"({mode_prompt_name}) > ", history=history, completer=completer, auto_suggest=auto_suggest, complete_while_typing=True )
            else:
                user_input = input(f"({mode_prompt_name}) > ")

            if not user_input:
                continue

            if user_input.startswith('/'):
                # --- Call Command Handler ---
                # Pass mode_manager instead of current_mode_instance
                # Pass current_mode_slug
                new_mode_slug = handle_command(
                    command_input=user_input,
                    config=config,
                    memory_manager=memory_manager,
                    file_watcher=file_watcher,
                    # REMOVED: current_mode_instance=current_mode_instance,
                    mode_manager=mode_manager, # Pass the manager
                    current_mode_slug=current_mode_slug, # Pass the current slug
                    registered_components=registered_components, # Still pass for tools etc.
                    cli_context=cli_context,
                    global_allow_mode_switching=global_allow_mode_switching
                )
                # Update the global slug if the command handler returned a new one
                if new_mode_slug and new_mode_slug != current_mode_slug:
                    # Validate the new slug before setting
                    if mode_manager and new_mode_slug in mode_manager.get_available_modes():
                        logger.info(f"Switching mode from '{current_mode_slug}' to '{new_mode_slug}' based on command result.")
                        current_mode_slug = new_mode_slug
                    else:
                        logger.error(f"Command handler returned invalid mode slug '{new_mode_slug}'. Staying in '{current_mode_slug}'.")
                        print(f"[Error] Invalid mode '{new_mode_slug}' requested.")

            # --- Process Request with Flow ---
            elif current_mode_slug and mode_manager:
                logger.info(f"Processing request with mode '{current_mode_slug}'...")
                # Prepare context and store
                initial_context = {
                    "user_id": "cli_user",
                    "session_id": "cli_session",
                    "cli_context": cli_context.copy(), # Pass a copy of the CLI context
                    "initial_request": user_input
                }
                shared_store = mode_manager.prepare_initial_store(current_mode_slug, initial_context)
                flow_structure = mode_manager.get_flow_structure(current_mode_slug)

                if flow_structure and shared_store:
                    try:
                        # Run the flow
                        flow_structure.run(shared_store)
                        # Get result from store
                        result = shared_store.get("final_output", "[Error] Flow finished but no final_output was set.")
                        logger.info(f"Response from mode '{current_mode_slug}':")
                        print(result)
                    except Exception as flow_error:
                        logger.error(f"Error executing flow for mode '{current_mode_slug}': {flow_error}", exc_info=True)
                        print(f"[Error] An error occurred while processing your request in mode '{current_mode_slug}'. Please check logs.")
                else:
                    logger.error(f"Could not get flow structure or prepare store for mode '{current_mode_slug}'. Cannot process request.")
                    print(f"[Error] Failed to initialize mode '{current_mode_slug}'.")
            else:
                logger.error("No active mode slug or mode manager to process the request.")
                print("[Error] Cannot process request: No active mode.")

        except KeyboardInterrupt:
            logger.info("\nStopping watcher...")
            if file_watcher and file_watcher.is_running():
                file_watcher.stop()
            logger.info("Exiting Pocketcode.")
            break
        except Exception as e:
            logger.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
            logger.info("\nStopping watcher due to error...")
            if file_watcher and file_watcher.is_running():
                file_watcher.stop()
            break

if __name__ == "__main__":
    run()