#!/usr/bin/env python3
"""YAML syntax validator for Home Assistant configuration files."""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

# Import shared modules
from ha_yaml_loader import HAYamlLoader
from validation_config_loader import ValidationConfig

# Configure module logger
logger = logging.getLogger(__name__)


class YAMLValidator:
    """Validates YAML syntax and basic structure for Home Assistant files."""

    def __init__(self, config_dir: str = "config"):
        """Initialize the YAMLValidator."""
        self.config_dir = Path(config_dir)
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.validation_config = ValidationConfig.get_instance()

    def validate_yaml_syntax(self, file_path: Path) -> bool:
        """Validate YAML syntax of a single file.

        Args:
            file_path: Path to the YAML file to validate

        Returns:
            True if YAML syntax is valid, False otherwise
        """
        logger.debug(f"Validating YAML syntax: {file_path}")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                yaml.load(f, Loader=HAYamlLoader)
            logger.debug(f"YAML syntax valid: {file_path}")
            return True
        except yaml.YAMLError as e:
            logger.warning(f"YAML syntax error in {file_path}: {e}")
            self.errors.append(f"{file_path}: YAML syntax error - {e}")
            return False
        except UnicodeDecodeError as e:
            logger.warning(f"Encoding error in {file_path}: {e}")
            self.errors.append(f"{file_path}: Encoding error - {e}")
            return False
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            self.errors.append(f"{file_path}: File not found")
            return False
        except PermissionError:
            logger.error(f"Permission denied reading: {file_path}")
            self.errors.append(f"{file_path}: Permission denied")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error validating {file_path}")
            self.errors.append(f"{file_path}: Unexpected error - {e}")
            return False

    def validate_file_encoding(self, file_path: Path) -> bool:
        """Ensure file is UTF-8 encoded as required by Home Assistant."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                f.read()
            return True
        except UnicodeDecodeError:
            self.errors.append(f"{file_path}: File must be UTF-8 encoded")
            return False

    def validate_configuration_structure(self, file_path: Path) -> bool:
        """Validate basic Home Assistant configuration.yaml structure."""
        if file_path.name != "configuration.yaml":
            return True

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = yaml.load(f, Loader=HAYamlLoader)

            if not isinstance(config, dict):
                self.errors.append(f"{file_path}: Configuration must be a dictionary")
                return False

            # Check for common configuration issues
            if "homeassistant" not in config:
                self.warnings.append(f"{file_path}: Missing 'homeassistant' section")

            # Check for deprecated keys
            deprecated_keys = ["discovery", "introduction"]
            for key in deprecated_keys:
                if key in config:
                    self.warnings.append(f"{file_path}: '{key}' is deprecated")

            return True
        except Exception as e:
            self.errors.append(f"{file_path}: Failed to validate structure - {e}")
            return False

    def validate_automations_structure(self, file_path: Path) -> bool:
        """Validate automations.yaml structure."""
        if file_path.name != "automations.yaml":
            return True

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                automations = yaml.load(f, Loader=HAYamlLoader)

            if automations is None:
                return True  # Empty file is valid

            if not isinstance(automations, list):
                self.errors.append(f"{file_path}: Automations must be a list")
                return False

            all_valid = True
            for i, automation in enumerate(automations):
                if not isinstance(automation, dict):
                    self.errors.append(
                        f"{file_path}: Automation {i} must be a dictionary"
                    )
                    all_valid = False
                    continue

                # Check required fields (both singular and plural forms are valid)
                # Blueprint automations use 'use_blueprint' instead of
                # direct triggers/actions
                if "use_blueprint" not in automation:
                    if "trigger" not in automation and "triggers" not in automation:
                        self.errors.append(
                            f"{file_path}: Automation {i} missing 'trigger' "
                            f"or 'triggers'"
                        )
                        all_valid = False
                    if "action" not in automation and "actions" not in automation:
                        self.errors.append(
                            f"{file_path}: Automation {i} missing 'action' or 'actions'"
                        )
                        all_valid = False

                # Check for alias (recommended)
                if "alias" not in automation:
                    self.warnings.append(
                        f"{file_path}: Automation {i} missing 'alias' (recommended)"
                    )

                # Check automation best practices
                self._check_automation_best_practices(automation, file_path, i)

            return all_valid
        except Exception as e:
            self.errors.append(
                f"{file_path}: Failed to validate automations structure - {e}"
            )
            return False

    def _check_automation_best_practices(
        self, automation: Dict, file_path: Path, index: int
    ) -> None:
        """Check automation for best practices and recommended fields."""
        # Check for mode field (recommended to be explicit)
        if "mode" not in automation and "use_blueprint" not in automation:
            alias = automation.get("alias", f"Automation {index}")
            self.warnings.append(
                f"{file_path}: '{alias}' - "
                "Consider specifying 'mode' explicitly (single, restart, queued, parallel)"
            )

    def validate_scripts_structure(self, file_path: Path) -> bool:
        """Validate scripts.yaml structure."""
        if file_path.name != "scripts.yaml":
            return True

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                scripts = yaml.load(f, Loader=HAYamlLoader)

            if scripts is None:
                return True  # Empty file is valid

            if not isinstance(scripts, dict):
                self.errors.append(f"{file_path}: Scripts must be a dictionary")
                return False

            all_valid = True
            for script_name, script_config in scripts.items():
                if not isinstance(script_config, dict):
                    self.errors.append(
                        f"{file_path}: Script '{script_name}' must be a dictionary"
                    )
                    all_valid = False
                    continue

                # Check required fields
                # Blueprint scripts use 'use_blueprint' instead of direct sequence
                if (
                    "use_blueprint" not in script_config
                    and "sequence" not in script_config
                ):
                    self.errors.append(
                        f"{file_path}: Script '{script_name}' missing required "
                        f"'sequence' or 'use_blueprint'"
                    )
                    all_valid = False

            return all_valid
        except Exception as e:
            self.errors.append(
                f"{file_path}: Failed to validate scripts structure - {e}"
            )
            return False

    def check_deprecated_patterns(
        self, data: Any, file_path: Path, context: str = "any", path: str = ""
    ) -> None:
        """Recursively check for deprecated patterns in configuration data."""
        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key

                # Check for 'enabled: false' at automation level
                if key == "enabled" and value is False:
                    self.warnings.append(
                        f"{file_path}: '{current_path}' - "
                        "Consider disabling automations via the UI instead of 'enabled: false'"
                    )

                # Check for device_id usage
                if key in ("device_id", "device_ids"):
                    self.warnings.append(
                        f"{file_path}: '{current_path}' - "
                        "device_id references are fragile; consider using entity_id instead"
                    )

                # Recursively check nested structures
                self.check_deprecated_patterns(value, file_path, context, current_path)

        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]"
                self.check_deprecated_patterns(item, file_path, context, current_path)

    def check_hardcoded_urls(self, data: Any, file_path: Path, path: str = "") -> None:
        """Check for hardcoded URLs that should be in secrets.yaml."""
        if isinstance(data, str):
            for pattern_config in self.validation_config.hardcoded_url_patterns:
                pattern = pattern_config.get("pattern", "")
                message = pattern_config.get(
                    "message", f"Hardcoded URL containing '{pattern}'"
                )
                if pattern and pattern in data:
                    self.warnings.append(f"{file_path}: {path} - {message}")

        elif isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key
                self.check_hardcoded_urls(value, file_path, current_path)

        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]"
                self.check_hardcoded_urls(item, file_path, current_path)

    def check_mqtt_topics(self, data: Any, file_path: Path, path: str = "") -> None:
        """Check for placeholder or invalid MQTT topics."""
        if isinstance(data, str):
            for pattern_config in self.validation_config.mqtt_warning_patterns:
                pattern = pattern_config.get("pattern", "")
                message = pattern_config.get("message", "MQTT topic may be invalid")
                if pattern and pattern.lower() in data.lower():
                    self.warnings.append(f"{file_path}: {path} - {message}")

        elif isinstance(data, dict):
            # Only check values in MQTT-related keys
            mqtt_keys = ("topic", "state_topic", "command_topic", "availability_topic")
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key
                if key in mqtt_keys:
                    self.check_mqtt_topics(value, file_path, current_path)
                elif isinstance(value, (dict, list)):
                    self.check_mqtt_topics(value, file_path, current_path)

        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]"
                self.check_mqtt_topics(item, file_path, current_path)

    def validate_deprecated_patterns_in_file(self, file_path: Path) -> None:
        """Validate a file for deprecated patterns.

        Args:
            file_path: Path to the YAML file to check
        """
        logger.debug(f"Checking deprecated patterns in: {file_path}")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.load(f, Loader=HAYamlLoader)

            if data is None:
                logger.debug(f"File is empty, skipping pattern check: {file_path}")
                return

            # Check for deprecated patterns
            self.check_deprecated_patterns(data, file_path)

            # Check for hardcoded URLs
            self.check_hardcoded_urls(data, file_path)

            # Check for MQTT topic issues in MQTT config files
            if "mqtt" in file_path.name.lower():
                self.check_mqtt_topics(data, file_path)

        except yaml.YAMLError:
            # Syntax errors are already caught and reported by validate_yaml_syntax
            logger.debug(f"Skipping pattern check due to YAML error: {file_path}")
        except Exception as e:
            # Log unexpected errors but don't fail - pattern checking is advisory
            logger.warning(
                f"Could not check deprecated patterns in {file_path}: {e}"
            )

    def get_yaml_files(self) -> List[Path]:
        """Get all YAML files in the config directory."""
        yaml_files: List[Path] = []
        for pattern in ["*.yaml", "*.yml"]:
            yaml_files.extend(self.config_dir.glob(pattern))

        # Skip blueprints directory - these are templates and don't need validation
        return yaml_files

    def validate_all(self) -> bool:
        """Validate all YAML files in the config directory."""
        if not self.config_dir.exists():
            self.errors.append(f"Config directory {self.config_dir} does not exist")
            return False

        yaml_files = self.get_yaml_files()
        if not yaml_files:
            self.warnings.append("No YAML files found in config directory")
            return True

        all_valid = True

        for file_path in yaml_files:
            # Skip secrets.yaml as it may contain sensitive data
            if file_path.name == "secrets.yaml":
                continue

            if not self.validate_file_encoding(file_path):
                all_valid = False
                continue

            if not self.validate_yaml_syntax(file_path):
                all_valid = False
                continue

            # Structure validation for specific files
            self.validate_configuration_structure(file_path)
            self.validate_automations_structure(file_path)
            self.validate_scripts_structure(file_path)

            # Check for deprecated patterns and best practices
            self.validate_deprecated_patterns_in_file(file_path)

        return all_valid

    def print_results(self):
        """Print validation results."""
        if self.errors:
            print("ERRORS:")
            for error in self.errors:
                print(f"  ❌ {error}")
            print()

        if self.warnings:
            print("WARNINGS:")
            for warning in self.warnings:
                print(f"  ⚠️  {warning}")
            print()

        if not self.errors and not self.warnings:
            print("✅ All YAML files are valid!")
        elif not self.errors:
            print("✅ YAML syntax is valid (with warnings)")
        else:
            print("❌ YAML validation failed")


def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity level.

    Args:
        verbose: If True, set logging to DEBUG level
    """
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Validate YAML syntax for Home Assistant configuration files",
    )
    parser.add_argument(
        "config_dir",
        nargs="?",
        default="config",
        help="Path to Home Assistant config directory (default: config)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug output",
    )

    return parser.parse_args()


def main():
    """Run YAML syntax validation from command line."""
    args = parse_args()

    setup_logging(args.verbose)
    logger.info(f"Starting YAML validation for: {args.config_dir}")

    validator = YAMLValidator(args.config_dir)
    is_valid = validator.validate_all()
    validator.print_results()

    logger.info(f"Validation complete: {'PASSED' if is_valid else 'FAILED'}")
    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
