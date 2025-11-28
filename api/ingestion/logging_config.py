"""
Centralized logging configuration for the ingestion module.

Suppresses verbose warnings from third-party PDF/document processing libraries
that would otherwise flood logs with non-actionable messages.

This module should be imported early in any module that processes documents.
Import triggers configuration - no function call needed.
"""
import logging

# Suppress verbose third-party library warnings
_SUPPRESSED_LOGGERS = [
    'pdfminer',
    'PIL',
    'docling',
    'docling_parse',
    'docling_core',
    'pdfium',
]

for _logger_name in _SUPPRESSED_LOGGERS:
    logging.getLogger(_logger_name).setLevel(logging.CRITICAL)
