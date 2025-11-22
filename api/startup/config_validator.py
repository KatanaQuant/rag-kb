"""
Configuration validator for startup checks.

Validates configuration settings early to provide clear error messages
before the application attempts to use invalid paths or settings.
"""
import os
from pathlib import Path
from typing import List, Optional


class ConfigValidationError(Exception):
    """Configuration validation failed"""
    pass


class ConfigValidator:
    """Validates configuration settings on startup"""

    def __init__(self, config):
        self.config = config
        self.errors: List[str] = []

    def validate(self) -> None:
        """Validate all configuration settings

        Raises:
            ConfigValidationError: If validation fails
        """
        self._validate_knowledge_base_path()
        self._validate_data_dir()

        if self.errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(
                f"  - {error}" for error in self.errors
            )
            raise ConfigValidationError(error_msg)

    def _validate_knowledge_base_path(self) -> None:
        """Validate knowledge base directory path"""
        kb_path = self.config.paths.knowledge_base

        # Check if path exists
        if not kb_path.exists():
            self.errors.append(
                f"Knowledge base directory does not exist: {kb_path}\n"
                f"    Create it with: mkdir -p {kb_path}\n"
                f"    Or update KNOWLEDGE_BASE_PATH in .env"
            )
            return

        # Check if it's a directory
        if not kb_path.is_dir():
            self.errors.append(
                f"Knowledge base path is not a directory: {kb_path}\n"
                f"    Update KNOWLEDGE_BASE_PATH in .env to point to a directory"
            )
            return

        # Check if readable
        if not os.access(kb_path, os.R_OK):
            self.errors.append(
                f"Knowledge base directory is not readable: {kb_path}\n"
                f"    Fix with: chmod +r {kb_path}"
            )

        # Check if writable (needed for watcher and temp files)
        if not os.access(kb_path, os.W_OK):
            # This is a warning, not a hard error
            print(f"Warning: Knowledge base directory is not writable: {kb_path}")
            print("  File watcher may not work properly")
            print(f"  Fix with: chmod +w {kb_path}")

    def _validate_data_dir(self) -> None:
        """Validate data directory for database"""
        data_dir = self.config.paths.data_dir

        # Check if parent exists
        if not data_dir.parent.exists():
            self.errors.append(
                f"Data directory parent does not exist: {data_dir.parent}\n"
                f"    Create it with: mkdir -p {data_dir.parent}"
            )
            return

        # If data_dir doesn't exist, try to create it
        if not data_dir.exists():
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
                print(f"Created data directory: {data_dir}")
            except PermissionError:
                self.errors.append(
                    f"Cannot create data directory (permission denied): {data_dir}\n"
                    f"    Fix with: sudo mkdir -p {data_dir} && sudo chown $USER {data_dir}"
                )
            except Exception as e:
                self.errors.append(
                    f"Cannot create data directory: {data_dir}\n"
                    f"    Error: {e}"
                )

        # Check if writable (needed for database)
        if data_dir.exists() and not os.access(data_dir, os.W_OK):
            self.errors.append(
                f"Data directory is not writable: {data_dir}\n"
                f"    Fix with: chmod +w {data_dir}"
            )
