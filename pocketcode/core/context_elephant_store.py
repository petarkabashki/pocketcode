# pocketcode/core/context_elephant_store.py
import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Removed MemoryBankIncompleteError as verification failure doesn't halt execution anymore

class ContextElephantStoreManager:
    """
    Manages the verification, creation, and loading of context elephant store files
    located in the project's root directory (CWD).
    Context elephant store functionality can be enabled/disabled via configuration.
    """
    def __init__(self, core_config: Dict, project_root: str):
        """
        Initializes the ContextElephantStoreManager.

        Args:
            core_config: The 'core' section of the loaded settings.
            project_root: The root directory of the user's project (usually CWD).
        """
        self.enabled: bool = core_config.get('enable_context_elephant_store', False) # Check if enabled
        self.context_elephant_store_dir_name: str = core_config.get('context_elephant_store_dir', 'context_elephant_store')
        self.required_files: List[str] = core_config.get('context_elephant_store_files', [])
        self.project_root: str = project_root
        self.context_elephant_store_path: str = os.path.join(self.project_root, self.context_elephant_store_dir_name)
        logger.debug(
            f"ContextElephantStoreManager initialized. Enabled: {self.enabled}, "
            f"Path: {self.context_elephant_store_path}, Required Files: {self.required_files}"
        )

    def get_context_elephant_store_path(self) -> str:
        """Returns the full path to the context elephant store directory."""
        return self.context_elephant_store_path

    def verify_and_prepare(self) -> None:
        """
        If context elephant store is enabled:
        - Ensures the context elephant store directory exists (creates if missing).
        - Ensures all required files exist (creates empty files if missing).
        - Logs warnings for missing or empty files.

        Raises:
            OSError: If directory creation fails or the path exists but isn't a directory.
        """
        if not self.enabled:
            logger.info("Context elephant store is disabled in configuration. Skipping verification and preparation.")
            return

        logger.info(f"Verifying context elephant store structure in: {self.context_elephant_store_path}")

        # 1. Ensure Directory Exists
        try:
            if not os.path.exists(self.context_elephant_store_path):
                os.makedirs(self.context_elephant_store_path)
                logger.info(f"Created context elephant store directory: {self.context_elephant_store_path}")
            elif not os.path.isdir(self.context_elephant_store_path):
                # Path exists but is not a directory - this is a critical error
                error_msg = f"Context elephant store path exists but is not a directory: {self.context_elephant_store_path}"
                logger.error(error_msg)
                raise OSError(error_msg) # Raise OSError for consistency
        except OSError as e:
            logger.error(f"Failed to ensure context elephant store directory {self.context_elephant_store_path}: {e}")
            raise # Re-raise the OSError

        # 2. Check/Create Required Files
        if not self.required_files:
            logger.warning("No required context elephant store files specified in configuration.")
            return # Nothing more to verify/create

        created_count = 0
        empty_count = 0
        for filename in self.required_files:
            file_path = os.path.join(self.context_elephant_store_path, filename)
            try:
                if not os.path.exists(file_path):
                    # Create empty file if missing
                    with open(file_path, 'a'): # 'a' mode creates if not exists, doesn't truncate
                        pass
                    logger.warning(f"Required context elephant store file was missing, created empty file: {filename}")
                    created_count += 1
                elif os.path.getsize(file_path) == 0:
                    # Log warning if file exists but is empty
                    logger.warning(f"Required context elephant store file exists but is empty: {filename}")
                    empty_count += 1
            except OSError as e:
                 logger.error(f"Error checking or creating context elephant store file {file_path}: {e}")
                 # Decide if we should raise here or just log and continue?
                 # For now, log and continue, as directory is the main blocker.

        if created_count > 0 or empty_count > 0:
             logger.info(f"Context elephant store verification complete. Created: {created_count}, Found empty: {empty_count}.")
        else:
             logger.info("Context elephant store verification successful (all files present and non-empty).")


    def create_context_elephant_store_structure(self) -> bool:
        """
        Explicitly creates the context elephant store directory and all required files as empty files.
        This ignores the 'enable_context_elephant_store' setting.

        Returns:
            True if the structure was created or already existed successfully, False otherwise.
        """
        logger.info(f"Explicitly creating context elephant store structure in: {self.context_elephant_store_path}")

        # 1. Ensure Directory Exists
        try:
            os.makedirs(self.context_elephant_store_path, exist_ok=True) # exist_ok=True prevents error if dir exists
            if not os.path.isdir(self.context_elephant_store_path):
                 # Should not happen with makedirs unless race condition or permissions issue
                 logger.error(f"Failed to create or access context elephant store directory (path is not a directory): {self.context_elephant_store_path}")
                 return False
            logger.info(f"Ensured context elephant store directory exists: {self.context_elephant_store_path}")
        except OSError as e:
            logger.error(f"Failed to create context elephant store directory {self.context_elephant_store_path}: {e}")
            return False

        # 2. Create Required Files
        if not self.required_files:
            logger.warning("No required context elephant store files specified in configuration. Only directory created.")
            return True # Directory creation succeeded

        created_count = 0
        existed_count = 0
        error_count = 0
        for filename in self.required_files:
            file_path = os.path.join(self.context_elephant_store_path, filename)
            try:
                if not os.path.exists(file_path):
                    with open(file_path, 'a'):
                        pass
                    logger.info(f"Created empty context elephant store file: {filename}")
                    created_count += 1
                else:
                     logger.debug(f"Context elephant store file already exists: {filename}")
                     existed_count += 1
            except OSError as e:
                 logger.error(f"Error creating context elephant store file {file_path}: {e}")
                 error_count += 1

        if error_count > 0:
             logger.error(f"Finished creating structure with {error_count} file errors.")
             return False
        else:
             logger.info(f"Context elephant store structure creation complete. Created: {created_count}, Existed: {existed_count}.")
             return True


    def load_content(self) -> Dict[str, str]:
        """
        Loads the content of all required context elephant store files if enabled and directory exists.

        Returns:
            A dictionary mapping filenames to their content. Returns empty if disabled,
            directory doesn't exist, or no files are required.

        Raises:
            IOError: If reading a file fails (and context elephant store is enabled).
        """
        content: Dict[str, str] = {}
        if not self.enabled:
            logger.debug("Context elephant store disabled, not loading content.")
            return content
        if not os.path.isdir(self.context_elephant_store_path):
             logger.error(f"Context elephant store directory not found or not a directory at {self.context_elephant_store_path}. Cannot load content.")
             return content
        if not self.required_files:
            return content # Return empty if no files are required

        logger.debug(f"Loading content from context elephant store: {self.context_elephant_store_path}")
        for filename in self.required_files:
            file_path = os.path.join(self.context_elephant_store_path, filename)
            if not os.path.exists(file_path):
                 logger.warning(f"Required context elephant store file {filename} not found during load. Skipping.")
                 continue # Skip missing files during load
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content[filename] = f.read()
                # logger.debug(f"Successfully loaded content from {filename}") # Reduce log noise
            except IOError as e:
                logger.error(f"Failed to read context elephant store file {file_path}: {e}")
                # Decide whether to raise or just skip the file
                # For robustness, let's skip and log error, but maybe raise later?
                # raise # Re-raise the IOError
            except Exception as e: # Catch potential encoding errors etc.
                 logger.error(f"An unexpected error occurred reading {file_path}: {e}")
                 # raise

        logger.info(f"Loaded content for {len(content)} context elephant store files.")
        return content

    def get_file_content(self, filename: str) -> Optional[str]:
        """
        Loads the content of a single specified context elephant store file if enabled.

        Args:
            filename: The name of the file within the context elephant store directory.

        Returns:
            The content of the file as a string, or None if disabled, file
            doesn't exist, or an error occurs.
        """
        if not self.enabled:
            logger.debug("Context elephant store disabled, not loading single file content.")
            return None

        file_path = os.path.join(self.context_elephant_store_path, filename)
        logger.debug(f"Attempting to load single file: {file_path}")

        if not os.path.exists(file_path):
            logger.warning(f"Context elephant store file not found: {file_path}")
            return None
        if not os.path.isfile(file_path):
             logger.warning(f"Path exists but is not a file: {file_path}")
             return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except IOError as e:
            logger.error(f"Failed to read context elephant store file {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred reading {file_path}: {e}")
            return None