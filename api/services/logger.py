# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""
Logger service - provides structured logging with levels.

Replaces raw print() statements throughout the codebase.
Makes logging testable and configurable.
"""

from enum import Enum
from typing import Optional
import sys

class LogLevel(Enum):
    """Log levels"""
    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4

class Logger:
    """Simple logger service.

    Single Responsibility: Handle all logging concerns
    Small class: < 100 lines
    Few instance variables: 2 (level, output)
    """

    def __init__(self, level: LogLevel = LogLevel.INFO, output=None):
        self.level = level
        self.output = output or sys.stdout

    def debug(self, message: str):
        """Log debug message"""
        if self.level.value <= LogLevel.DEBUG.value:
            self._write(f"DEBUG: {message}")

    def info(self, message: str):
        """Log info message"""
        if self.level.value <= LogLevel.INFO.value:
            self._write(message)

    def warning(self, message: str):
        """Log warning message"""
        if self.level.value <= LogLevel.WARNING.value:
            self._write(f"WARNING: {message}")

    def error(self, message: str):
        """Log error message"""
        if self.level.value <= LogLevel.ERROR.value:
            self._write(f"ERROR: {message}")

    def _write(self, message: str):
        """Write message to output"""
        print(message, file=self.output)
