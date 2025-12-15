#!/usr/bin/env python3
"""Centralized validation configuration loader.

This module provides a single source of truth for loading validation
configuration across all validation tools. It implements a singleton
pattern for efficient reuse.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

# Configure module logger
logger = logging.getLogger(__name__)


class ValidationConfig:
    """Unified validation configuration loader.

    Loads configuration from validation_config.yaml and provides
    typed access to all configuration sections.

    Implements singleton pattern - use get_instance() for shared access.
    """

    _instance: Optional["ValidationConfig"] = None

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize validation config from YAML file.

        Args:
            config_path: Path to config file. Defaults to validation_config.yaml
                        in the same directory as this module.
        """
        if config_path is None:
            config_path = Path(__file__).parent / "validation_config.yaml"

        self._config_path = config_path
        self._config: Dict[str, Any] = {}
        self._load_config()

    @classmethod
    def get_instance(cls, config_path: Optional[Path] = None) -> "ValidationConfig":
        """Get singleton instance of ValidationConfig.

        Args:
            config_path: Optional path to config file. Only used on first call.

        Returns:
            Shared ValidationConfig instance
        """
        if cls._instance is None:
            cls._instance = cls(config_path)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance. Useful for testing."""
        cls._instance = None

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        if not self._config_path.exists():
            logger.debug(
                f"Config file not found: {self._config_path}, using defaults"
            )
            self._use_defaults()
            return

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
            logger.debug(f"Loaded validation config from {self._config_path}")
        except yaml.YAMLError as e:
            logger.warning(f"Invalid YAML in config file {self._config_path}: {e}")
            self._use_defaults()
        except PermissionError as e:
            logger.warning(f"Cannot read config file {self._config_path}: {e}")
            self._use_defaults()
        except Exception as e:
            logger.warning(f"Unexpected error loading config {self._config_path}: {e}")
            self._use_defaults()

    def _use_defaults(self) -> None:
        """Use default configuration values."""
        self._config = {
            "min_ha_version": "2024.1.0",
            "environment_patterns": [
                {"pattern": "Integration 'mobile_app' could not be loaded"},
                {"pattern": "Unable to install package"},
                {"pattern": "RuntimeError:"},
            ],
            "deprecated_patterns": [],
            "recommended_fields": {},
            "stderr_ignore_patterns": [
                "debug",
                "info:",
                "starting",
                "voluptuous",
            ],
            "timeouts": {
                "ha_check_config": 120,
                "yaml_validation": 30,
                "reference_validation": 60,
            },
            "builtin_service_domains": [
                "homeassistant",
                "automation",
                "script",
                "scene",
                "input_boolean",
                "input_number",
                "input_select",
                "input_text",
                "light",
                "switch",
                "cover",
                "fan",
                "climate",
                "media_player",
                "camera",
                "lock",
                "vacuum",
                "notify",
                "persistent_notification",
            ],
            "hardcoded_url_patterns": [],
            "mqtt_warning_patterns": [],
        }

    # -------------------------------------------------------------------------
    # Property accessors for each config section
    # -------------------------------------------------------------------------

    @property
    def min_ha_version(self) -> str:
        """Get minimum supported Home Assistant version."""
        return self._config.get("min_ha_version", "2024.1.0")

    @property
    def environment_patterns(self) -> List[str]:
        """Get list of environment-specific error patterns.

        Returns:
            List of pattern strings that indicate environment-specific errors
        """
        patterns = self._config.get("environment_patterns", [])
        return [p.get("pattern", "") for p in patterns if p.get("pattern")]

    @property
    def deprecated_patterns(self) -> List[Dict[str, Any]]:
        """Get list of deprecated pattern definitions.

        Returns:
            List of dicts with 'pattern', 'context', 'message', 'severity' keys
        """
        return self._config.get("deprecated_patterns", [])

    @property
    def recommended_fields(self) -> Dict[str, List[Dict[str, str]]]:
        """Get recommended fields by entity type.

        Returns:
            Dict mapping entity types to lists of recommended field definitions
        """
        return self._config.get("recommended_fields", {})

    @property
    def stderr_ignore_patterns(self) -> List[str]:
        """Get patterns to ignore in stderr output.

        Returns:
            List of substrings that indicate ignorable stderr lines
        """
        return self._config.get("stderr_ignore_patterns", [])

    @property
    def builtin_service_domains(self) -> Set[str]:
        """Get set of built-in service domains.

        Returns:
            Set of domain names that are always valid for service calls
        """
        domains = self._config.get("builtin_service_domains", [])
        return set(domains)

    @property
    def hardcoded_url_patterns(self) -> List[Dict[str, str]]:
        """Get patterns for hardcoded URLs that should be in secrets.

        Returns:
            List of dicts with 'pattern' and 'message' keys
        """
        return self._config.get("hardcoded_url_patterns", [])

    @property
    def mqtt_warning_patterns(self) -> List[Dict[str, str]]:
        """Get patterns for MQTT topics that may be invalid.

        Returns:
            List of dicts with 'pattern' and 'message' keys
        """
        return self._config.get("mqtt_warning_patterns", [])

    def get_timeout(self, key: str) -> int:
        """Get timeout value by key.

        Args:
            key: Timeout key (e.g., 'ha_check_config', 'yaml_validation')

        Returns:
            Timeout in seconds, defaults to 120 if key not found
        """
        timeouts = self._config.get("timeouts", {})
        return timeouts.get(key, 120)

    def get_raw_config(self) -> Dict[str, Any]:
        """Get raw configuration dictionary.

        Returns:
            Complete configuration dictionary
        """
        return self._config.copy()
