#%% pocketcode/core/watcher.py
import logging
import os
import queue
import threading
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

logger = logging.getLogger(__name__)

class WatcherEventHandler(FileSystemEventHandler):
    """Handles file system events from watchdog."""

    def __init__(self, instruction_queue, config):
        self.instruction_queue = instruction_queue
        self.config = config # Watch mode specific config
        self.trigger_string = self.config.get('trigger_string', 'AI!')
        self.instruction_source = self.config.get('instruction_source', 'after_trigger')
        self.debounce_ms = int(self.config.get("debounce_ms", 500))
        self._debounce_timers = {}
        self._lock = threading.Lock()
        logger.debug(f"WatcherEventHandler initialized. Trigger: '{self.trigger_string}', Source: '{self.instruction_source}'")

    def _enqueue_instruction(self, event_data):
        self.instruction_queue.put(event_data)

    def _debounced_enqueue(self, key: str, event_data):
        with self._lock:
            existing = self._debounce_timers.get(key)
            if existing:
                existing.cancel()
            timer = threading.Timer(self.debounce_ms / 1000.0, self._enqueue_instruction, args=(event_data,))
            self._debounce_timers[key] = timer
            timer.daemon = True
            timer.start()

    def on_modified(self, event):
        """Called when a file or directory is modified."""
        if event.is_directory:
            # We are interested in file modifications, not directory metadata changes
            return

        filepath = event.src_path
        logger.info(f"Detected modification in: {filepath}")

        # Avoid processing temporary files or files we shouldn't process
        # Add more robust checks if needed (e.g., based on file extensions)
        if os.path.basename(filepath).startswith('.') or '~' in filepath:
             logger.debug(f"Ignoring temporary/hidden file modification: {filepath}")
             return

        try:
            # Add a small delay to ensure file write is complete
            time.sleep(0.1)
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            for line_num, line in enumerate(lines):
                if self.trigger_string in line:
                    logger.info(f"Trigger '{self.trigger_string}' found in {filepath}:{line_num + 1}")
                    instruction = ""
                    if self.instruction_source == 'after_trigger':
                        parts = line.split(self.trigger_string, 1)
                        if len(parts) > 1:
                            instruction = parts[1].strip()
                    elif self.instruction_source == 'full_line':
                        instruction = line.strip()
                    else: # Default to after_trigger if config is invalid
                         parts = line.split(self.trigger_string, 1)
                         if len(parts) > 1:
                             instruction = parts[1].strip()

                    if instruction:
                        logger.info(f"Extracted instruction: '{instruction}'")
                        # Put event details onto the queue for main thread processing
                        event_data = {
                            "type": "instruction",
                            "filepath": filepath,
                            "instruction": instruction,
                            "timestamp": time.time()
                        }
                        debounce_key = f"{filepath}:{instruction}"
                        self._debounced_enqueue(debounce_key, event_data)
                        # Process only the first trigger found in the file for now
                        break
                    else:
                        logger.warning(f"Trigger found in {filepath}:{line_num + 1}, but no instruction could be extracted based on source '{self.instruction_source}'.")

        except FileNotFoundError:
             logger.warning(f"File modified but not found immediately after: {filepath}. Might be a temporary file.")
        except Exception as e:
            logger.error(f"Error processing modified file {filepath}: {e}", exc_info=True)


class FileWatcher:
    """Manages file system watching in a separate thread."""

    def __init__(self, instruction_queue, config):
        self.instruction_queue = instruction_queue
        self.config = config # Watch mode specific config
        self.watch_recursive = self.config.get('watch_recursive', True)
        self.observer = None
        self.watched_paths = set() # Store paths being watched
        self.watch_handles = {} # Store observer watch handles {path: handle}
        self.thread = None
        self.stop_event = threading.Event()
        self._lock = threading.Lock() # To protect watched_paths and watch_handles

    def _run(self):
        """Internal method run by the watcher thread."""
        logger.info("Watcher thread started.")
        self.observer = Observer()
        event_handler = WatcherEventHandler(self.instruction_queue, self.config)

        with self._lock:
            # Schedule watches for paths already added before start
            current_paths = list(self.watched_paths) # Copy to avoid issues if modified during iteration
            for path in current_paths:
                if os.path.exists(path):
                    try:
                        handle = self.observer.schedule(event_handler, path, recursive=self.watch_recursive)
                        self.watch_handles[path] = handle
                        logger.info(f"Scheduled watch for: {path} (Recursive: {self.watch_recursive})")
                    except Exception as e:
                         logger.error(f"Failed to schedule watch for {path}: {e}")
                else:
                     logger.warning(f"Path '{path}' does not exist. Cannot schedule watch.")


        if not self.watch_handles:
             logger.warning("Watcher thread starting, but no valid paths currently scheduled.")

        self.observer.start()
        logger.info("Watchdog observer started.")

        try:
            while not self.stop_event.is_set():
                # Keep the thread alive, observer runs in background
                time.sleep(1)
        except Exception as e:
             logger.error(f"Exception in watcher thread loop: {e}", exc_info=True)
        finally:
            if self.observer.is_alive():
                self.observer.stop()
                logger.info("Watchdog observer stopped.")
            self.observer.join()
            logger.info("Watcher thread finished.")

    def start(self):
        """Starts the watcher thread if not already running."""
        with self._lock:
            if self.thread is None or not self.thread.is_alive():
                self.stop_event.clear()
                self.thread = threading.Thread(target=self._run, daemon=True)
                self.thread.start()
                logger.info("Requested watcher thread start.")
            else:
                 logger.info("Watcher thread already running.")

    def stop(self):
        """Stops the watcher thread."""
        with self._lock:
            if self.thread and self.thread.is_alive():
                logger.info("Requesting watcher thread stop...")
                self.stop_event.set()
                # Observer stop is handled in _run finally block
                # Wait for thread to finish
                self.thread.join(timeout=5) # Wait up to 5 seconds
                if self.thread.is_alive():
                     logger.warning("Watcher thread did not stop gracefully within timeout.")
                else:
                     logger.info("Watcher thread stopped successfully.")
                self.thread = None
                self.observer = None # Clear observer instance
                self.watch_handles.clear() # Clear handles as observer is stopped
            else:
                 logger.info("Watcher thread not running.")


    def add_watch(self, path_to_watch):
        """Adds a path to the watch list."""
        abs_path = os.path.abspath(path_to_watch)
        logger.debug(f"Request to add watch for: {abs_path}")

        if not os.path.exists(abs_path):
             logger.warning(f"Path does not exist, cannot add watch: {abs_path}")
             return False

        with self._lock:
            if abs_path in self.watched_paths:
                logger.info(f"Path already being watched: {abs_path}")
                return True # Already watching

            self.watched_paths.add(abs_path)
            logger.info(f"Added path to watch list: {abs_path}")

            # If observer is running, schedule the new watch immediately
            if self.observer and self.observer.is_alive():
                try:
                    event_handler = WatcherEventHandler(self.instruction_queue, self.config) # Need handler instance
                    handle = self.observer.schedule(event_handler, abs_path, recursive=self.watch_recursive)
                    self.watch_handles[abs_path] = handle
                    logger.info(f"Dynamically scheduled watch for: {abs_path}")
                except Exception as e:
                    logger.error(f"Failed to dynamically schedule watch for {abs_path}: {e}")
                    # Rollback adding to watched_paths if schedule fails? Maybe not, allow retry later.
                    return False
            return True

    def remove_watch(self, path_to_remove):
        """Removes a path from the watch list."""
        abs_path = os.path.abspath(path_to_remove)
        logger.debug(f"Request to remove watch for: {abs_path}")

        with self._lock:
            if abs_path not in self.watched_paths:
                logger.warning(f"Path not in watch list: {abs_path}")
                return False

            self.watched_paths.remove(abs_path)
            logger.info(f"Removed path from watch list: {abs_path}")

            # If observer is running, unschedule the watch
            if self.observer and self.observer.is_alive() and abs_path in self.watch_handles:
                try:
                    watch_handle = self.watch_handles.pop(abs_path) # Remove and get handle
                    self.observer.unschedule(watch_handle)
                    logger.info(f"Dynamically unscheduled watch for: {abs_path}")
                except Exception as e:
                    logger.error(f"Failed to dynamically unschedule watch for {abs_path}: {e}")
                    # Put handle back? Or assume it's gone? Log error and continue.
                    # self.watch_handles[abs_path] = watch_handle # Optional: Put back if failed
                    return False # Indicate potential issue
            elif abs_path in self.watch_handles:
                 # Observer not running, just remove the handle reference
                 del self.watch_handles[abs_path]

            return True

    def get_watched_paths(self):
        """Returns a copy of the set of watched paths."""
        with self._lock:
            return self.watched_paths.copy()

    def is_running(self):
        """Checks if the watcher thread is alive."""
        with self._lock:
            return self.thread is not None and self.thread.is_alive()
