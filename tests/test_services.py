# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for services."""

from io import StringIO
from services import Logger
from services.logger import LogLevel


class TestLogger:
    """Test Logger service."""

    def test_info_logging(self):
        output = StringIO()
        logger = Logger(level=LogLevel.INFO, output=output)
        logger.info("test message")
        assert output.getvalue() == "test message\n"

    def test_error_logging(self):
        output = StringIO()
        logger = Logger(level=LogLevel.INFO, output=output)
        logger.error("error message")
        assert output.getvalue() == "ERROR: error message\n"

    def test_warning_logging(self):
        output = StringIO()
        logger = Logger(level=LogLevel.INFO, output=output)
        logger.warning("warning message")
        assert output.getvalue() == "WARNING: warning message\n"

    def test_debug_logging_enabled(self):
        output = StringIO()
        logger = Logger(level=LogLevel.DEBUG, output=output)
        logger.debug("debug message")
        assert output.getvalue() == "DEBUG: debug message\n"

    def test_debug_logging_disabled(self):
        output = StringIO()
        logger = Logger(level=LogLevel.INFO, output=output)
        logger.debug("debug message")
        assert output.getvalue() == ""

    def test_log_level_filtering(self):
        output = StringIO()
        logger = Logger(level=LogLevel.ERROR, output=output)
        logger.info("info message")
        logger.warning("warning message")
        logger.error("error message")
        assert "info message" not in output.getvalue()
        assert "warning message" not in output.getvalue()
        assert "error message" in output.getvalue()
