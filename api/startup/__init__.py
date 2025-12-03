"""Startup modules for component initialization.

Phase classes provide focused responsibilities for startup:
- ConfigurationPhase: config validation
- ComponentPhase: model, stores, processor, cache, reranker
- PipelinePhase: queue, worker, concurrent pipeline
- SanitizationPhase: resume incomplete, repair orphans, self-healing
- IndexingPhase: background indexing, file watching
"""

from .component_factory import ComponentFactory
from .sanitizer import Sanitizer
from .manager import StartupManager
from .phases import (
    ConfigurationPhase,
    ComponentPhase,
    PipelinePhase,
    SanitizationPhase,
    IndexingPhase,
)

__all__ = [
    'ComponentFactory',
    'Sanitizer',
    'StartupManager',
    'ConfigurationPhase',
    'ComponentPhase',
    'PipelinePhase',
    'SanitizationPhase',
    'IndexingPhase',
]
