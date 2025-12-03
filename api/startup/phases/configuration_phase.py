"""Configuration validation phase.

Validates configuration before application startup.
"""
from config import default_config
from startup.config_validator import ConfigValidator


class ConfigurationPhase:
    """Validates application configuration.

    First phase of startup - fails fast if configuration is invalid.
    """

    def __init__(self, config=None):
        self._config = config or default_config

    def execute(self):
        """Validate configuration."""
        validator = ConfigValidator(self._config)
        validator.validate()
        print("Configuration validated")
