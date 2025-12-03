"""Startup phase classes.

Each phase encapsulates a specific responsibility during application startup.
StartupManager orchestrates these phases in sequence.
"""
from startup.phases.configuration_phase import ConfigurationPhase
from startup.phases.component_phase import ComponentPhase
from startup.phases.pipeline_phase import PipelinePhase
from startup.phases.sanitization_phase import SanitizationPhase
from startup.phases.indexing_phase import IndexingPhase

__all__ = [
    'ConfigurationPhase',
    'ComponentPhase',
    'PipelinePhase',
    'SanitizationPhase',
    'IndexingPhase',
]
