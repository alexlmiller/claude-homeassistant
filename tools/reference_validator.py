#!/usr/bin/env python3
"""Entity and device reference validator for Home Assistant configuration files.

Validates that all entity references in configuration files actually exist.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TypedDict

import yaml


class DomainSummary(TypedDict):
    """Type definition for domain summary dictionary."""

    count: int
    enabled: int
    disabled: int
    examples: List[str]


class HAYamlLoader(yaml.SafeLoader):
    """Custom YAML loader that handles Home Assistant specific tags."""

    pass


def include_constructor(loader, node):
    """Handle !include tag."""
    filename = loader.construct_scalar(node)
    return f"!include {filename}"


def include_dir_named_constructor(loader, node):
    """Handle !include_dir_named tag."""
    dirname = loader.construct_scalar(node)
    return f"!include_dir_named {dirname}"


def include_dir_merge_named_constructor(loader, node):
    """Handle !include_dir_merge_named tag."""
    dirname = loader.construct_scalar(node)
    return f"!include_dir_merge_named {dirname}"


def include_dir_merge_list_constructor(loader, node):
    """Handle !include_dir_merge_list tag."""
    dirname = loader.construct_scalar(node)
    return f"!include_dir_merge_list {dirname}"


def include_dir_list_constructor(loader, node):
    """Handle !include_dir_list tag."""
    dirname = loader.construct_scalar(node)
    return f"!include_dir_list {dirname}"


def input_constructor(loader, node):
    """Handle !input tag for blueprints."""
    input_name = loader.construct_scalar(node)
    return f"!input {input_name}"


def secret_constructor(loader, node):
    """Handle !secret tag."""
    secret_name = loader.construct_scalar(node)
    return f"!secret {secret_name}"


# Register custom constructors
HAYamlLoader.add_constructor("!include", include_constructor)
HAYamlLoader.add_constructor(
    "!include_dir_named", include_dir_named_constructor
)
HAYamlLoader.add_constructor(
    "!include_dir_merge_named", include_dir_merge_named_constructor
)
HAYamlLoader.add_constructor(
    "!include_dir_merge_list", include_dir_merge_list_constructor
)
HAYamlLoader.add_constructor("!include_dir_list", include_dir_list_constructor)
HAYamlLoader.add_constructor("!input", input_constructor)
HAYamlLoader.add_constructor("!secret", secret_constructor)


class ValidationConfig:
    """Load validation configuration from external file."""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize validation config."""
        if config_path is None:
            config_path = Path(__file__).parent / "validation_config.yaml"

        self.config: Dict = {}
        self.builtin_service_domains: Set[str] = set()

        self._load_config(config_path)

    def _load_config(self, config_path: Path) -> None:
        """Load configuration from YAML file."""
        if not config_path.exists():
            self._use_defaults()
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}

            domains = self.config.get("builtin_service_domains", [])
            self.builtin_service_domains = set(domains)
        except Exception:
            self._use_defaults()

    def _use_defaults(self) -> None:
        """Use default values if config unavailable."""
        self.builtin_service_domains = {
            "homeassistant", "automation", "script", "scene",
            "input_boolean", "input_number", "input_select", "input_text",
            "light", "switch", "cover", "fan", "climate", "media_player",
            "camera", "lock", "vacuum", "notify", "persistent_notification",
        }


class ReferenceValidator:
    """Validates entity and device references in Home Assistant config."""

    # Special keywords that are not entity IDs
    SPECIAL_KEYWORDS = {"all", "none"}

    # Built-in Home Assistant entities that are always available
    # These are not stored in the entity registry but are valid references
    BUILTIN_ENTITIES = {
        "sun.sun",  # Sun integration
        "zone.home",  # Home zone
    }

    # Built-in entity domain prefixes that are always valid
    # Some entities like zones might be dynamically created
    BUILTIN_DOMAINS = {
        "sun",  # Sun integration (sun.sun)
        # Note: zone domain is partially built-in (zone.home) but can have custom zones
        # We'll validate zone.home specifically but check others in registry
    }

    # Dynamic service domains that are created based on config
    # These don't need to be validated against a fixed list
    DYNAMIC_SERVICE_DOMAINS = {
        "notify",  # notify.* services are created dynamically
        "tts",  # text-to-speech services
        "rest_command",  # REST commands defined in config
        "shell_command",  # Shell commands defined in config
        "pyscript",  # Python scripts (if installed)
    }

    def __init__(self, config_dir: str = "config"):
        """Initialize the ReferenceValidator."""
        self.config_dir = Path(config_dir)
        self.storage_dir = self.config_dir / ".storage"
        self.errors: List[str] = []
        self.warnings: List[str] = []

        # Load validation configuration
        self.validation_config = ValidationConfig()

        # Cache for loaded registries
        self._entities: Optional[Dict[str, Any]] = None
        self._devices: Optional[Dict[str, Any]] = None
        self._areas: Optional[Dict[str, Any]] = None
        self._scripts: Optional[Set[str]] = None
        self._scenes: Optional[Set[str]] = None
        self._blueprints: Optional[Dict[str, Dict]] = None

    def load_entity_registry(self) -> Dict[str, Any]:
        """Load and cache entity registry."""
        if self._entities is None:
            registry_file = self.storage_dir / "core.entity_registry"
            if not registry_file.exists():
                self.errors.append(f"Entity registry not found: {registry_file}")
                return {}

            try:
                with open(registry_file, "r") as f:
                    data = json.load(f)
                    self._entities = {
                        entity["entity_id"]: entity
                        for entity in data.get("data", {}).get("entities", [])
                    }
            except Exception as e:
                self.errors.append(f"Failed to load entity registry: {e}")
                return {}

        return self._entities

    def load_device_registry(self) -> Dict[str, Any]:
        """Load and cache device registry."""
        if self._devices is None:
            registry_file = self.storage_dir / "core.device_registry"
            if not registry_file.exists():
                self.errors.append(f"Device registry not found: {registry_file}")
                return {}

            try:
                with open(registry_file, "r") as f:
                    data = json.load(f)
                    self._devices = {
                        device["id"]: device
                        for device in data.get("data", {}).get("devices", [])
                    }
            except Exception as e:
                self.errors.append(f"Failed to load device registry: {e}")
                return {}

        return self._devices

    def load_area_registry(self) -> Dict[str, Any]:
        """Load and cache area registry."""
        if self._areas is None:
            registry_file = self.storage_dir / "core.area_registry"
            if not registry_file.exists():
                self.warnings.append(f"Area registry not found: {registry_file}")
                return {}

            try:
                with open(registry_file, "r") as f:
                    data = json.load(f)
                    self._areas = {
                        area["id"]: area
                        for area in data.get("data", {}).get("areas", [])
                    }
            except Exception as e:
                self.warnings.append(f"Failed to load area registry: {e}")
                return {}

        return self._areas

    def load_scripts(self) -> Set[str]:
        """Load script names from scripts.yaml."""
        if self._scripts is not None:
            return self._scripts

        self._scripts = set()
        scripts_file = self.config_dir / "scripts.yaml"

        if not scripts_file.exists():
            return self._scripts

        try:
            with open(scripts_file, "r", encoding="utf-8") as f:
                data = yaml.load(f, Loader=HAYamlLoader)
                if isinstance(data, dict):
                    self._scripts = set(data.keys())
        except Exception:
            pass  # Scripts file may not be valid YAML

        return self._scripts

    def load_scenes(self) -> Set[str]:
        """Load scene names from scenes.yaml."""
        if self._scenes is not None:
            return self._scenes

        self._scenes = set()
        scenes_file = self.config_dir / "scenes.yaml"

        if not scenes_file.exists():
            return self._scenes

        try:
            with open(scenes_file, "r", encoding="utf-8") as f:
                data = yaml.load(f, Loader=HAYamlLoader)
                if isinstance(data, list):
                    for scene in data:
                        if isinstance(scene, dict) and "id" in scene:
                            self._scenes.add(scene["id"])
        except Exception:
            pass  # Scenes file may not be valid YAML

        return self._scenes

    def load_blueprints(self) -> Dict[str, Dict]:
        """Load all blueprint definitions from blueprints directory."""
        if self._blueprints is not None:
            return self._blueprints

        self._blueprints = {}
        blueprints_dir = self.config_dir / "blueprints" / "automation"

        if not blueprints_dir.exists():
            return self._blueprints

        # Recursively find all blueprint YAML files
        for blueprint_file in blueprints_dir.rglob("*.yaml"):
            try:
                with open(blueprint_file, "r", encoding="utf-8") as f:
                    data = yaml.load(f, Loader=HAYamlLoader)

                if isinstance(data, dict) and "blueprint" in data:
                    # Create a path-based key for the blueprint
                    rel_path = blueprint_file.relative_to(blueprints_dir)
                    blueprint_key = str(rel_path)
                    self._blueprints[blueprint_key] = data
            except Exception:
                pass  # Skip invalid blueprint files

        return self._blueprints

    def get_blueprint_inputs(self, blueprint_data: Dict) -> Dict[str, Dict]:
        """Extract input definitions from a blueprint."""
        blueprint_section = blueprint_data.get("blueprint", {})
        return blueprint_section.get("input", {})

    def validate_blueprint_automation(
        self, automation: Dict, file_path: Path, index: int
    ) -> bool:
        """Validate a blueprint-based automation has required inputs.

        Returns True if valid, False otherwise.
        """
        if "use_blueprint" not in automation:
            return True  # Not a blueprint automation

        use_blueprint = automation["use_blueprint"]
        if not isinstance(use_blueprint, dict):
            return True

        blueprint_path = use_blueprint.get("path", "")
        automation_inputs = use_blueprint.get("input", {})

        # Skip if blueprint path is a template or external
        if not blueprint_path or blueprint_path.startswith("!"):
            return True

        # Load blueprints
        blueprints = self.load_blueprints()

        # Find matching blueprint - handle both with and without leading path
        blueprint_data = None
        for key, data in blueprints.items():
            if blueprint_path.endswith(key) or key.endswith(blueprint_path):
                blueprint_data = data
                break

        if blueprint_data is None:
            # Blueprint not found locally - could be a community blueprint
            self.warnings.append(
                f"{file_path}: Automation {index} uses blueprint '{blueprint_path}' "
                f"which was not found locally"
            )
            return True

        # Get required inputs from blueprint
        blueprint_inputs = self.get_blueprint_inputs(blueprint_data)
        all_valid = True

        for input_name, input_config in blueprint_inputs.items():
            # Check if input is required (no default value)
            if isinstance(input_config, dict):
                has_default = "default" in input_config
                is_optional = input_config.get("default") is not None or has_default
            else:
                is_optional = False

            # Check if the automation provides this input
            if input_name not in automation_inputs:
                if not is_optional:
                    alias = automation.get("alias", f"Automation {index}")
                    self.warnings.append(
                        f"{file_path}: '{alias}' - Blueprint input '{input_name}' "
                        f"not provided (may use default)"
                    )

        return all_valid

    def validate_blueprints_in_file(self, file_path: Path, data: Any) -> bool:
        """Validate all blueprint automations in a file."""
        if not isinstance(data, list):
            return True

        all_valid = True
        for i, item in enumerate(data):
            if isinstance(item, dict) and "use_blueprint" in item:
                if not self.validate_blueprint_automation(item, file_path, i):
                    all_valid = False

        return all_valid

    def extract_service_calls(self, data: Any, path: str = "") -> Set[str]:
        """Extract service calls from configuration data.

        Service calls are in the format 'domain.service' and appear in:
        - action.service fields
        - service fields in automations/scripts
        """
        services = set()

        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key

                # Look for service key
                if key == "service" and isinstance(value, str):
                    # Skip template services and !input references
                    if not value.startswith("!") and not self.is_template(value):
                        if "." in value:
                            services.add(value)

                # Also check 'action' key when it contains a service call string
                elif key == "action" and isinstance(value, str):
                    if "." in value and not value.startswith("!"):
                        services.add(value)

                # Recursive search
                else:
                    services.update(self.extract_service_calls(value, current_path))

        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]"
                services.update(self.extract_service_calls(item, current_path))

        return services

    def validate_service_calls(
        self, services: Set[str], file_path: Path
    ) -> bool:
        """Validate that service calls reference valid domains.

        Returns True if all service calls are valid, False otherwise.
        """
        all_valid = True
        scripts = self.load_scripts()
        scenes = self.load_scenes()
        entities = self.load_entity_registry()

        # Get domains from entity registry
        entity_domains = {
            entity_id.split(".")[0]
            for entity_id in entities.keys()
        }

        for service in services:
            parts = service.split(".", 1)
            if len(parts) != 2:
                continue

            domain, action = parts

            # Check if it's a built-in service domain
            if domain in self.validation_config.builtin_service_domains:
                # Special validation for script.* and scene.* calls
                if domain == "script" and action not in scripts:
                    if action != "reload" and action != "turn_on" and action != "turn_off":
                        self.warnings.append(
                            f"{file_path}: Service 'script.{action}' - "
                            f"script '{action}' not found in scripts.yaml"
                        )

                elif domain == "scene" and action not in scenes:
                    if action != "reload" and action != "turn_on":
                        self.warnings.append(
                            f"{file_path}: Service 'scene.{action}' - "
                            f"scene '{action}' not found in scenes.yaml"
                        )
                continue

            # Check if it's a dynamic domain (notify, tts, etc.)
            if domain in self.DYNAMIC_SERVICE_DOMAINS:
                continue

            # Check if domain exists in entity registry
            if domain in entity_domains:
                continue

            # Unknown domain - warn but don't fail
            self.warnings.append(
                f"{file_path}: Unknown service domain '{domain}' in service call "
                f"'{service}'"
            )

        return all_valid

    def is_uuid_format(self, value: str) -> bool:
        """Check if a string matches UUID format (32 hex characters)."""
        # UUID format: 8-4-4-4-12 hex digits, but HA often stores without hyphens
        uuid_pattern = r"^[a-f0-9]{32}$"
        return bool(re.match(uuid_pattern, value))

    def is_template(self, value: str) -> bool:
        """Check if value is a Jinja2 template expression."""
        # Match template expressions like {{ ... }}
        return bool(re.search(r"\{\{.*?\}\}", value))

    def is_builtin_entity(self, entity_id: str) -> bool:
        """Check if entity is a built-in Home Assistant entity.

        Built-in entities are always available but may not appear in the entity registry.
        Examples: sun.sun, zone.home

        Args:
            entity_id: The entity ID to check

        Returns:
            True if the entity is a built-in HA entity, False otherwise
        """
        # Check against known built-in entities
        if entity_id in self.BUILTIN_ENTITIES:
            return True

        # Check if entity belongs to a built-in domain
        if "." in entity_id:
            domain = entity_id.split(".")[0]
            if domain in self.BUILTIN_DOMAINS:
                return True

        return False

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

            # Skip built-in Home Assistant entities (sun.sun, zone.home, etc.)
            if self.is_builtin_entity(entity_id):
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
        self.validate_service_calls(service_calls, file_path)

        # Validate blueprint inputs for automations.yaml
        if file_path.name == "automations.yaml":
            self.validate_blueprints_in_file(file_path, data)

        return all_valid

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


def main():
    """Run entity and device reference validation from command line."""
    config_dir = sys.argv[1] if len(sys.argv) > 1 else "config"

    validator = ReferenceValidator(config_dir)
    is_valid = validator.validate_all()
    validator.print_results()

    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
