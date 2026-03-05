#%% pocketcode/core/watcher.py
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

if TYPE_CHECKING:
    from pocketcode.core.plugin_manager import PluginManager
    from pocketcode.core.namespace_registry import RegistryHolder

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


# ---------------------------------------------------------------------------
# Plugin Hot-Reload Support (FR-011)
# ---------------------------------------------------------------------------

class PluginHotReloadHandler(FileSystemEventHandler):
    """
    Watches plugin directories for file changes and triggers a PluginManager
    rebuild + atomic registry swap via ``RegistryHolder.swap()``.

    Rebuild sequence (from research.md Topic 2):
      (a) BUILD   — create new PluginManager + call .load() outside the lock
      (b) SWAP    — holder.swap(new_pm) — single GIL-atomic store
      (c) DISCARD — old_pm falls out of scope; GC handles cleanup

    ``_rebuild_in_progress`` serialises concurrent rebuild attempts caused by
    editors emitting 2–3 inotify events per save. The existing 500 ms debounce
    timer ensures that a burst of events collapses to a single rebuild trigger.
    """

    def __init__(
        self,
        holder: "RegistryHolder",
        config: dict,
        workspace_root: "Path",
        debounce_ms: int = 500,
    ) -> None:
        super().__init__()
        self._holder = holder
        self._config = config
        self._workspace_root = workspace_root
        self._debounce_ms = debounce_ms
        self._rebuild_in_progress = threading.Event()
        self._debounce_timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    # ── Internal helpers ────────────────────────────────────────────────────

    def _debounced_enqueue(self, key: str) -> None:
        """Collapse rapid consecutive events; trigger rebuild after quiet period."""
        with self._lock:
            existing = self._debounce_timers.get(key)
            if existing:
                existing.cancel()
            timer = threading.Timer(
                self._debounce_ms / 1000.0,
                self._trigger_rebuild,
            )
            self._debounce_timers[key] = timer
            timer.daemon = True
            timer.start()

    def _trigger_rebuild(self) -> None:
        """Build a new PluginManager snapshot and atomically swap the holder."""
        if self._rebuild_in_progress.is_set():
            logger.debug("PluginHotReloadHandler: rebuild already in progress; skipping.")
            return

        self._rebuild_in_progress.set()
        try:
            # Import lazily to avoid circular imports at module level
            from pocketcode.core.plugin_manager import PluginManager  # noqa: PLC0415

            logger.info("PluginHotReloadHandler: rebuilding plugin registry…")
            new_pm = PluginManager(config=self._config, workspace_root=self._workspace_root)
            new_pm.load()
            self._holder.swap(new_pm)
            logger.info("PluginHotReloadHandler: registry swapped successfully.")
        except Exception as exc:
            logger.error("PluginHotReloadHandler: rebuild failed: %s", exc, exc_info=True)
        finally:
            self._rebuild_in_progress.clear()

    # ── FileSystemEventHandler overrides ────────────────────────────────────

    def on_modified(self, event) -> None:
        if event.is_directory:
            return
        filepath = event.src_path
        basename = os.path.basename(filepath)
        # Ignore hidden files, temp files, and compiled Python artefacts
        if basename.startswith(".") or "~" in filepath or basename.endswith(".pyc"):
            return
        logger.debug("PluginHotReloadHandler: detected change in %s", filepath)
        self._debounced_enqueue(filepath)

    on_created = on_modified  # type: ignore[assignment]
    on_deleted = on_modified  # type: ignore[assignment]


class PluginWatcher:
    """
    Manages a watchdog Observer that monitors all plugin directories and
    triggers hot-reload via ``PluginHotReloadHandler`` on any file change.

    Usage::

        pw = PluginWatcher(holder=registry_holder, config=cfg, workspace_root=root)
        pw.start()
        # … runtime …
        pw.stop()
    """

    def __init__(
        self,
        holder: "RegistryHolder",
        config: dict,
        workspace_root: "Path",
        plugin_dirs: Optional[list] = None,
        debounce_ms: int = 500,
    ) -> None:
        self._holder = holder
        self._config = config
        self._workspace_root = workspace_root
        self._plugin_dirs: list[Path] = [Path(d) for d in (plugin_dirs or [])]
        self._debounce_ms = debounce_ms
        self._observer: Optional[Observer] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _default_plugin_dirs(self) -> list[Path]:
        """Resolve built-in plugin root if no explicit dirs given."""
        from pocketcode.core.plugin_manager import PluginManager  # noqa: PLC0415
        built_in = Path(PluginManager.__module__.rsplit(".", 1)[0].replace(".", "/"))
        # More robustly: use the known relative path
        built_in = self._workspace_root / "pocketcode" / "plugins"
        return [built_in] if built_in.exists() else []

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.info("PluginWatcher already running.")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="plugin-hot-reload")
        self._thread.start()
        logger.info("PluginWatcher started.")

    def stop(self) -> None:
        self._stop_event.set()
        if self._observer and self._observer.is_alive():
            self._observer.stop()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("PluginWatcher stopped.")

    def _run(self) -> None:
        handler = PluginHotReloadHandler(
            holder=self._holder,
            config=self._config,
            workspace_root=self._workspace_root,
            debounce_ms=self._debounce_ms,
        )
        self._observer = Observer()
        dirs_to_watch = self._plugin_dirs or self._default_plugin_dirs()
        for d in dirs_to_watch:
            if d.exists():
                self._observer.schedule(handler, str(d), recursive=True)
                logger.info("PluginWatcher monitoring: %s", d)
            else:
                logger.warning("PluginWatcher: directory does not exist: %s", d)

        self._observer.start()
        try:
            while not self._stop_event.is_set():
                time.sleep(1)
        finally:
            if self._observer.is_alive():
                self._observer.stop()
            self._observer.join()
