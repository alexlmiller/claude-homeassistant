#!/usr/bin/env python3
"""Entity and device reference validator for Home Assistant configuration files.

Validates that all entity references in configuration files actually exist.
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict

import yaml

# Import shared modules
from ha_yaml_loader import HAYamlLoader
from validation_config_loader import ValidationConfig

# Configure module logger
logger = logging.getLogger(__name__)


class DomainSummary(TypedDict):
    """Type definition for domain summary dictionary."""

    count: int
    enabled: int
    disabled: int
    examples: List[str]


class ReferenceValidator:
    """Validates entity and device references in Home Assistant config."""

    # Special keywords that are not entity IDs
    SPECIAL_KEYWORDS = {"all", "none"}

    def __init__(self, config_dir: str = "config"):
        """Initialize the ReferenceValidator."""
        self.config_dir = Path(config_dir)
        self.storage_dir = self.config_dir / ".storage"
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.validation_config = ValidationConfig.get_instance()

        # Cache for loaded registries
        self._entities: Optional[Dict[str, Any]] = None
        self._devices: Optional[Dict[str, Any]] = None
        self._areas: Optional[Dict[str, Any]] = None
        self._blueprints: Optional[Dict[str, Dict[str, Any]]] = None

    def load_entity_registry(self) -> Dict[str, Any]:
        """Load and cache entity registry.

        Returns:
            Dict mapping entity_id to entity data
        """
        if self._entities is None:
            registry_file = self.storage_dir / "core.entity_registry"
            if not registry_file.exists():
                logger.error(f"Entity registry not found: {registry_file}")
                self.errors.append(f"Entity registry not found: {registry_file}")
                return {}

            try:
                logger.debug(f"Loading entity registry from: {registry_file}")
                with open(registry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._entities = {
                        entity["entity_id"]: entity
                        for entity in data.get("data", {}).get("entities", [])
                    }
                logger.debug(f"Loaded {len(self._entities)} entities")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in entity registry: {e}")
                self.errors.append(f"Invalid JSON in entity registry: {e}")
                return {}
            except PermissionError:
                logger.error(f"Permission denied reading: {registry_file}")
                self.errors.append(f"Permission denied reading entity registry")
                return {}
            except Exception as e:
                logger.exception(f"Failed to load entity registry")
                self.errors.append(f"Failed to load entity registry: {e}")
                return {}

        return self._entities

    def load_device_registry(self) -> Dict[str, Any]:
        """Load and cache device registry.

        Returns:
            Dict mapping device_id to device data
        """
        if self._devices is None:
            registry_file = self.storage_dir / "core.device_registry"
            if not registry_file.exists():
                logger.error(f"Device registry not found: {registry_file}")
                self.errors.append(f"Device registry not found: {registry_file}")
                return {}

            try:
                logger.debug(f"Loading device registry from: {registry_file}")
                with open(registry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._devices = {
                        device["id"]: device
                        for device in data.get("data", {}).get("devices", [])
                    }
                logger.debug(f"Loaded {len(self._devices)} devices")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in device registry: {e}")
                self.errors.append(f"Invalid JSON in device registry: {e}")
                return {}
            except PermissionError:
                logger.error(f"Permission denied reading: {registry_file}")
                self.errors.append(f"Permission denied reading device registry")
                return {}
            except Exception as e:
                logger.exception(f"Failed to load device registry")
                self.errors.append(f"Failed to load device registry: {e}")
                return {}

        return self._devices

    def load_area_registry(self) -> Dict[str, Any]:
        """Load and cache area registry.

        Returns:
            Dict mapping area_id to area data
        """
        if self._areas is None:
            registry_file = self.storage_dir / "core.area_registry"
            if not registry_file.exists():
                logger.debug(f"Area registry not found: {registry_file}")
                self.warnings.append(f"Area registry not found: {registry_file}")
                return {}

            try:
                logger.debug(f"Loading area registry from: {registry_file}")
                with open(registry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._areas = {
                        area["id"]: area
                        for area in data.get("data", {}).get("areas", [])
                    }
                logger.debug(f"Loaded {len(self._areas)} areas")
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in area registry: {e}")
                self.warnings.append(f"Invalid JSON in area registry: {e}")
                return {}
            except PermissionError:
                logger.warning(f"Permission denied reading: {registry_file}")
                self.warnings.append(f"Permission denied reading area registry")
                return {}
            except Exception as e:
                logger.warning(f"Failed to load area registry: {e}")
                self.warnings.append(f"Failed to load area registry: {e}")
                return {}

        return self._areas

    def is_uuid_format(self, value: str) -> bool:
        """Check if a string matches UUID format (32 hex characters)."""
        # UUID format: 8-4-4-4-12 hex digits, but HA often stores without hyphens
        uuid_pattern = r"^[a-f0-9]{32}$"
        return bool(re.match(uuid_pattern, value))

    def is_template(self, value: str) -> bool:
        """Check if value is a Jinja2 template expression."""
        # Match template expressions like {{ ... }}
        return bool(re.search(r"\{\{.*?\}\}", value))

    def should_skip_entity_validation(self, value: str) -> bool:
        """Check if entity reference should be skipped during validation."""
        return (
            value.startswith("!")
            or self.is_uuid_format(value)  # HA tags like !input, !secret
            or self.is_template(value)  # UUID format (device-based)
            or value  # Template expressions
            in self.SPECIAL_KEYWORDS  # Special keywords like "all", "none"
        )

    def extract_entity_references(self, data: Any, path: str = "") -> Set[str]:
        """Extract entity references from configuration data."""
        entities = set()

        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key

                # Common entity reference keys
                if key in ["entity_id", "entity_ids", "entities"]:
                    if isinstance(value, str):
                        if not self.should_skip_entity_validation(value):
                            entities.add(value)
                    elif isinstance(value, list):
                        for entity in value:
                            if isinstance(
                                entity, str
                            ) and not self.should_skip_entity_validation(entity):
                                entities.add(entity)

                # Device-related keys
                elif key in ["device_id", "device_ids"]:
                    # Device IDs are handled separately
                    pass

                # Area-related keys
                elif key in ["area_id", "area_ids"]:
                    # Area IDs are handled separately
                    pass

                # Service data might contain entity references
                elif key == "data" and isinstance(value, dict):
                    entities.update(self.extract_entity_references(value, current_path))

                # Templates might contain entity references
                elif isinstance(value, str) and any(
                    x in value for x in ["state_attr(", "states(", "is_state("]
                ):
                    entities.update(self.extract_entities_from_template(value))

                # Recursive search
                else:
                    entities.update(self.extract_entity_references(value, current_path))

        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]" if path else f"[{i}]"
                entities.update(self.extract_entity_references(item, current_path))

        return entities

    def extract_entities_from_template(self, template: str) -> Set[str]:
        """Extract entity references from Jinja2 templates."""
        entities = set()

        # Common patterns for entity references in templates
        patterns = [
            r"states\('([^']+)'\)",  # states('entity.id')
            r'states\("([^"]+)"\)',  # states("entity.id")
            # states.domain.entity
            r"states\.([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)",
            r"is_state\('([^']+)'",  # is_state('entity.id', ...)
            r'is_state\("([^"]+)"',  # is_state("entity.id", ...)
            r"state_attr\('([^']+)'",  # state_attr('entity.id', ...)
            r'state_attr\("([^"]+)"',  # state_attr("entity.id", ...)
        ]

        for pattern in patterns:
            matches = re.findall(pattern, template)
            for match in matches:
                # Validate entity ID format
                if "." in match and len(match.split(".")) == 2:
                    entities.add(match)

        return entities

    def extract_device_references(self, data: Any) -> Set[str]:
        """Extract device references from configuration data."""
        devices = set()

        if isinstance(data, dict):
            for key, value in data.items():
                if key in ["device_id", "device_ids"]:
                    if isinstance(value, str):
                        # Skip blueprint inputs and other HA tags
                        if not value.startswith("!"):
                            devices.add(value)
                    elif isinstance(value, list):
                        for device in value:
                            if isinstance(device, str) and not device.startswith("!"):
                                devices.add(device)
                else:
                    devices.update(self.extract_device_references(value))

        elif isinstance(data, list):
            for item in data:
                devices.update(self.extract_device_references(item))

        return devices

    def extract_area_references(self, data: Any) -> Set[str]:
        """Extract area references from configuration data."""
        areas = set()

        if isinstance(data, dict):
            for key, value in data.items():
                if key in ["area_id", "area_ids"]:
                    if isinstance(value, str):
                        # Skip blueprint inputs and other HA tags
                        if not value.startswith("!"):
                            areas.add(value)
                    elif isinstance(value, list):
                        for area in value:
                            if isinstance(area, str) and not area.startswith("!"):
                                areas.add(area)
                else:
                    areas.update(self.extract_area_references(value))

        elif isinstance(data, list):
            for item in data:
                areas.update(self.extract_area_references(item))

        return areas

    # -------------------------------------------------------------------------
    # Service Call Validation
    # -------------------------------------------------------------------------

    def extract_service_calls(self, data: Any, path: str = "") -> Set[str]:
        """Extract service call references from configuration data.

        Args:
            data: Configuration data to search
            path: Current path in the config (for debugging)

        Returns:
            Set of service call strings (e.g., 'light.turn_on', 'notify.mobile')
        """
        services = set()

        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key

                # 'service' key contains service calls
                if key == "service" and isinstance(value, str):
                    # Skip templates and HA tags
                    if not value.startswith("!") and not self.is_template(value):
                        services.add(value)

                # 'action' key can also contain service calls (newer HA syntax)
                elif key == "action" and isinstance(value, str):
                    if "." in value and not value.startswith("!"):
                        services.add(value)

                # Recurse into nested structures
                else:
                    services.update(self.extract_service_calls(value, current_path))

        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]" if path else f"[{i}]"
                services.update(self.extract_service_calls(item, current_path))

        return services

    def validate_service_calls(
        self, services: Set[str], file_path: Path
    ) -> bool:
        """Validate extracted service calls against known domains.

        Args:
            services: Set of service call strings
            file_path: Source file path for error messages

        Returns:
            True if all services are valid, False otherwise
        """
        all_valid = True
        builtin_domains = self.validation_config.builtin_service_domains

        # Also load entities to check for script.* and scene.* services
        entities = self.load_entity_registry()
        script_entities = {
            e.split(".")[1] for e in entities if e.startswith("script.")
        }
        scene_entities = {
            e.split(".")[1] for e in entities if e.startswith("scene.")
        }

        for service in services:
            if "." not in service:
                self.warnings.append(
                    f"{file_path}: Invalid service format '{service}' "
                    "(expected 'domain.action')"
                )
                continue

            domain, action = service.split(".", 1)

            # Check if domain is known
            if domain in builtin_domains:
                logger.debug(f"Service '{service}' uses builtin domain")
                continue

            # Check for script.* services - action should match a script entity
            if domain == "script":
                if action not in script_entities and action != "reload":
                    self.warnings.append(
                        f"{file_path}: Service '{service}' references "
                        f"unknown script (no script.{action} entity found)"
                    )

            # Check for scene.* services
            elif domain == "scene":
                if action not in scene_entities and action not in (
                    "reload",
                    "apply",
                    "create",
                ):
                    self.warnings.append(
                        f"{file_path}: Service '{service}' references "
                        f"unknown scene (no scene.{action} entity found)"
                    )

            # Unknown domain - might be a custom integration
            else:
                logger.debug(
                    f"Service '{service}' uses unknown domain '{domain}' "
                    "(may be custom integration)"
                )
                # Only warn, don't error - custom integrations are common
                self.warnings.append(
                    f"{file_path}: Service '{service}' uses domain '{domain}' "
                    "(not a builtin domain - may be custom integration)"
                )

        return all_valid

    # -------------------------------------------------------------------------
    # Blueprint Validation
    # -------------------------------------------------------------------------

    def load_blueprints(self) -> Dict[str, Dict[str, Any]]:
        """Load all blueprint definitions from the blueprints directory.

        Returns:
            Dict mapping blueprint path to blueprint schema
        """
        if self._blueprints is not None:
            return self._blueprints

        self._blueprints = {}
        blueprints_dir = self.config_dir / "blueprints"

        if not blueprints_dir.exists():
            logger.debug("No blueprints directory found")
            return self._blueprints

        # Search for all blueprint YAML files
        for blueprint_file in blueprints_dir.rglob("*.yaml"):
            try:
                with open(blueprint_file, "r", encoding="utf-8") as f:
                    data = yaml.load(f, Loader=HAYamlLoader)

                if data and isinstance(data, dict) and "blueprint" in data:
                    # Use relative path as key
                    rel_path = blueprint_file.relative_to(blueprints_dir)
                    self._blueprints[str(rel_path)] = data.get("blueprint", {})
                    logger.debug(f"Loaded blueprint: {rel_path}")

            except Exception as e:
                logger.warning(f"Failed to load blueprint {blueprint_file}: {e}")

        logger.info(f"Loaded {len(self._blueprints)} blueprints")
        return self._blueprints

    def get_blueprint_inputs(
        self, blueprint_path: str
    ) -> Tuple[Set[str], Set[str]]:
        """Get required and optional inputs for a blueprint.

        Args:
            blueprint_path: Path to blueprint relative to blueprints dir

        Returns:
            Tuple of (required_inputs, optional_inputs) sets
        """
        blueprints = self.load_blueprints()

        if blueprint_path not in blueprints:
            return set(), set()

        blueprint = blueprints[blueprint_path]
        inputs = blueprint.get("input", {})

        required = set()
        optional = set()

        for input_name, input_config in inputs.items():
            if isinstance(input_config, dict):
                # Has 'default' means it's optional
                if "default" in input_config:
                    optional.add(input_name)
                else:
                    required.add(input_name)
            else:
                # Simple input without config is required
                required.add(input_name)

        return required, optional

    def validate_blueprint_automation(
        self, automation: Dict[str, Any], file_path: Path
    ) -> bool:
        """Validate an automation that uses a blueprint.

        Args:
            automation: Automation configuration dict
            file_path: Source file for error messages

        Returns:
            True if valid, False otherwise
        """
        if "use_blueprint" not in automation:
            return True  # Not a blueprint-based automation

        use_blueprint = automation["use_blueprint"]
        if not isinstance(use_blueprint, dict):
            return True

        blueprint_path = use_blueprint.get("path", "")
        if not blueprint_path:
            self.warnings.append(
                f"{file_path}: Blueprint automation missing 'path'"
            )
            return False

        # Normalize blueprint path
        # HA uses format: domain/author/blueprint_name.yaml
        # or homeassistant/domain/name.yaml for official blueprints

        # Load blueprints
        blueprints = self.load_blueprints()

        # Try to find the blueprint
        blueprint_found = False
        matched_path = None

        for bp_path in blueprints:
            if bp_path == blueprint_path or bp_path.endswith(blueprint_path):
                blueprint_found = True
                matched_path = bp_path
                break

        if not blueprint_found:
            # Blueprint not found locally - might be from HA community
            logger.debug(
                f"Blueprint '{blueprint_path}' not found locally "
                "(may be community blueprint)"
            )
            return True  # Don't error on community blueprints

        # Validate inputs
        required_inputs, optional_inputs = self.get_blueprint_inputs(matched_path)
        provided_inputs = set(use_blueprint.get("input", {}).keys())

        # Check for missing required inputs
        missing_required = required_inputs - provided_inputs
        if missing_required:
            self.errors.append(
                f"{file_path}: Blueprint automation missing required inputs: "
                f"{', '.join(sorted(missing_required))}"
            )
            return False

        # Warn about missing optional inputs (informational)
        missing_optional = optional_inputs - provided_inputs
        if missing_optional:
            logger.debug(
                f"{file_path}: Blueprint automation using defaults for: "
                f"{', '.join(sorted(missing_optional))}"
            )

        # Check for unknown inputs
        all_valid_inputs = required_inputs | optional_inputs
        unknown_inputs = provided_inputs - all_valid_inputs
        if unknown_inputs:
            self.warnings.append(
                f"{file_path}: Blueprint automation has unknown inputs: "
                f"{', '.join(sorted(unknown_inputs))}"
            )

        return True

    def extract_entity_registry_ids(self, data: Any) -> Set[str]:
        """Extract entity registry UUID references from configuration data."""
        entity_registry_ids = set()

        if isinstance(data, dict):
            for key, value in data.items():
                # Look for entity_id fields containing UUIDs (device-based automations)
                if key == "entity_id" and isinstance(value, str):
                    if self.is_uuid_format(value):
                        entity_registry_ids.add(value)
                else:
                    entity_registry_ids.update(self.extract_entity_registry_ids(value))
        elif isinstance(data, list):
            for item in data:
                entity_registry_ids.update(self.extract_entity_registry_ids(item))

        return entity_registry_ids

    def get_entity_registry_id_mapping(self) -> Dict[str, str]:
        """Get mapping from entity registry ID to entity_id."""
        entities = self.load_entity_registry()
        return {
            entity_data["id"]: entity_data["entity_id"]
            for entity_data in entities.values()
            if "id" in entity_data
        }

    def validate_file_references(self, file_path: Path) -> bool:
        """Validate all references in a single file."""
        if file_path.name == "secrets.yaml":
            return True  # Skip secrets file

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.load(f, Loader=HAYamlLoader)
        except Exception as e:
            self.errors.append(f"{file_path}: Failed to load YAML - {e}")
            return False

        if data is None:
            return True  # Empty file is valid

        # Extract references
        entity_refs = self.extract_entity_references(data)
        device_refs = self.extract_device_references(data)
        area_refs = self.extract_area_references(data)
        entity_registry_ids = self.extract_entity_registry_ids(data)
        service_calls = self.extract_service_calls(data)

        # Load registries
        entities = self.load_entity_registry()
        devices = self.load_device_registry()
        areas = self.load_area_registry()
        entity_id_mapping = self.get_entity_registry_id_mapping()

        all_valid = True

        # Validate entity references (normal entity_id format)
        for entity_id in entity_refs:
            # Skip UUID-format entity IDs, they're handled separately
            if self.is_uuid_format(entity_id):
                continue

            if entity_id not in entities:
                # Check if it's a disabled entity
                disabled_entities = {
                    e["entity_id"]: e
                    for e in entities.values()
                    if e.get("disabled_by") is not None
                }

                if entity_id in disabled_entities:
                    self.warnings.append(
                        f"{file_path}: References disabled entity " f"'{entity_id}'"
                    )
                else:
                    self.errors.append(f"{file_path}: Unknown entity '{entity_id}'")
                    all_valid = False

        # Validate entity registry ID references (UUID format)
        for registry_id in entity_registry_ids:
            if registry_id not in entity_id_mapping:
                self.errors.append(
                    f"{file_path}: Unknown entity registry ID '{registry_id}'"
                )
                all_valid = False
            else:
                # Check if the mapped entity is disabled
                actual_entity_id = entity_id_mapping[registry_id]
                if actual_entity_id in entities:
                    entity_data = entities[actual_entity_id]
                    if entity_data.get("disabled_by") is not None:
                        self.warnings.append(
                            f"{file_path}: Entity registry ID '{registry_id}' "
                            f"references disabled entity '{actual_entity_id}'"
                        )

        # Validate device references
        for device_id in device_refs:
            if device_id not in devices:
                self.errors.append(f"{file_path}: Unknown device '{device_id}'")
                all_valid = False

        # Validate area references
        for area_id in area_refs:
            if area_id not in areas:
                self.warnings.append(f"{file_path}: Unknown area '{area_id}'")

        # Validate service calls
        if service_calls:
            self.validate_service_calls(service_calls, file_path)

        # Validate blueprint automations
        if file_path.name in ("automations.yaml", "automations"):
            self._validate_automations_blueprints(data, file_path)

        return all_valid

    def _validate_automations_blueprints(
        self, data: Any, file_path: Path
    ) -> None:
        """Validate blueprint usage in automations file.

        Args:
            data: Automations file content (list of automations)
            file_path: Source file path for error messages
        """
        if not isinstance(data, list):
            return

        for automation in data:
            if isinstance(automation, dict):
                self.validate_blueprint_automation(automation, file_path)

    def get_yaml_files(self) -> List[Path]:
        """Get all YAML files to validate."""
        yaml_files: List[Path] = []
        for pattern in ["*.yaml", "*.yml"]:
            yaml_files.extend(self.config_dir.glob(pattern))

        # Skip blueprints directory - these are templates with !input tags
        return yaml_files

    def validate_all(self) -> bool:
        """Validate all references in the config directory."""
        if not self.config_dir.exists():
            self.errors.append(f"Config directory {self.config_dir} does not exist")
            return False

        yaml_files = self.get_yaml_files()
        if not yaml_files:
            self.warnings.append("No YAML files found in config directory")
            return True

        all_valid = True

        for file_path in yaml_files:
            if not self.validate_file_references(file_path):
                all_valid = False

        return all_valid

    def get_entity_summary(self) -> Dict[str, DomainSummary]:
        """Get summary of available entities by domain."""
        entities = self.load_entity_registry()

        summary: Dict[str, DomainSummary] = {}
        for entity_id, entity_data in entities.items():
            domain = entity_id.split(".")[0]
            if domain not in summary:
                summary[domain] = {
                    "count": 0,
                    "enabled": 0,
                    "disabled": 0,
                    "examples": [],
                }

            summary[domain]["count"] += 1
            if entity_data.get("disabled_by") is None:
                summary[domain]["enabled"] += 1
            else:
                summary[domain]["disabled"] += 1

            # Add some examples
            if len(summary[domain]["examples"]) < 3:
                summary[domain]["examples"].append(entity_id)

        return summary

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

        # Print entity summary
        summary = self.get_entity_summary()
        if summary:
            print("AVAILABLE ENTITIES BY DOMAIN:")
            for domain, info in sorted(summary.items()):
                enabled_count = info["enabled"]
                disabled_count = info["disabled"]
                print(
                    f"  {domain}: {enabled_count} enabled, "
                    f"{disabled_count} disabled"
                )
                if info["examples"]:
                    print(f"    Examples: {', '.join(info['examples'])}")
            print()

        if not self.errors and not self.warnings:
            print("✅ All entity/device references are valid!")
        elif not self.errors:
            print("✅ Entity/device references are valid (with warnings)")
        else:
            print("❌ Invalid entity/device references found")


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
        description="Validate entity and device references in Home Assistant config",
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
    """Run entity and device reference validation from command line."""
    args = parse_args()

    setup_logging(args.verbose)
    logger.info(f"Starting reference validation for: {args.config_dir}")

    validator = ReferenceValidator(args.config_dir)
    is_valid = validator.validate_all()
    validator.print_results()

    logger.info(f"Validation complete: {'PASSED' if is_valid else 'FAILED'}")
    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
