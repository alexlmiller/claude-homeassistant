"""Tests for reference_validator.py."""

import json
import sys
from pathlib import Path

import pytest

# Add tools directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from reference_validator import ReferenceValidator, _ENTITY_PATTERNS


class TestEntityRegistry:
    """Tests for entity registry loading and validation."""

    def test_load_entity_registry(self, temp_config_dir, mock_entity_registry):
        """Test loading entity registry."""
        validator = ReferenceValidator(str(temp_config_dir))
        entities = validator.load_entity_registry()

        assert "light.living_room" in entities
        assert "sensor.temperature" in entities
        assert "switch.disabled_switch" in entities
        assert len(entities) == 5

    def test_load_entity_registry_missing(self, temp_config_dir):
        """Test handling of missing entity registry."""
        validator = ReferenceValidator(str(temp_config_dir))
        entities = validator.load_entity_registry()

        assert entities == {}
        assert len(validator.errors) == 1
        assert "not found" in validator.errors[0].lower()

    def test_load_entity_registry_invalid_json(self, temp_config_dir):
        """Test handling of invalid JSON in entity registry."""
        storage_dir = temp_config_dir / ".storage"
        storage_dir.mkdir(exist_ok=True)
        registry_file = storage_dir / "core.entity_registry"
        registry_file.write_text("not valid json {")

        validator = ReferenceValidator(str(temp_config_dir))
        entities = validator.load_entity_registry()

        assert entities == {}
        assert any("invalid json" in e.lower() for e in validator.errors)


class TestDeviceRegistry:
    """Tests for device registry loading."""

    def test_load_device_registry(self, temp_config_dir, mock_device_registry):
        """Test loading device registry."""
        validator = ReferenceValidator(str(temp_config_dir))
        devices = validator.load_device_registry()

        assert "device123" in devices
        assert "device456" in devices
        assert len(devices) == 2

    def test_load_device_registry_missing(self, temp_config_dir):
        """Test handling of missing device registry."""
        # Create storage dir without device registry
        (temp_config_dir / ".storage").mkdir(exist_ok=True)

        validator = ReferenceValidator(str(temp_config_dir))
        devices = validator.load_device_registry()

        assert devices == {}


class TestAreaRegistry:
    """Tests for area registry loading."""

    def test_load_area_registry(self, temp_config_dir, mock_area_registry):
        """Test loading area registry."""
        validator = ReferenceValidator(str(temp_config_dir))
        areas = validator.load_area_registry()

        assert "living_room" in areas
        assert "kitchen" in areas
        assert "hallway" in areas
        assert len(areas) == 3


class TestEntityReferenceExtraction:
    """Tests for extracting entity references from config data."""

    def test_extract_entity_id_simple(self, temp_config_dir, mock_registries):
        """Test simple entity_id extraction."""
        validator = ReferenceValidator(str(temp_config_dir))

        data = {
            "action": [
                {
                    "service": "light.turn_on",
                    "target": {"entity_id": "light.living_room"}
                }
            ]
        }

        entities = validator.extract_entity_references(data)
        assert "light.living_room" in entities

    def test_extract_entity_ids_list(self, temp_config_dir, mock_registries):
        """Test entity_id list extraction."""
        validator = ReferenceValidator(str(temp_config_dir))

        data = {
            "action": {
                "service": "light.turn_on",
                "target": {
                    "entity_id": [
                        "light.living_room",
                        "light.kitchen",
                        "light.bedroom"
                    ]
                }
            }
        }

        entities = validator.extract_entity_references(data)
        assert "light.living_room" in entities
        assert "light.kitchen" in entities
        assert "light.bedroom" in entities

    def test_extract_entities_key(self, temp_config_dir, mock_registries):
        """Test extraction from 'entities' key."""
        validator = ReferenceValidator(str(temp_config_dir))

        data = {
            "entities": ["sensor.temperature", "sensor.humidity"]
        }

        entities = validator.extract_entity_references(data)
        assert "sensor.temperature" in entities
        assert "sensor.humidity" in entities

    def test_extract_nested_entities(self, temp_config_dir, mock_registries):
        """Test nested entity extraction."""
        validator = ReferenceValidator(str(temp_config_dir))

        data = {
            "automations": [
                {
                    "trigger": {
                        "entity_id": "binary_sensor.motion"
                    },
                    "action": [
                        {
                            "service": "light.turn_on",
                            "data": {
                                "entity_id": "light.living_room"
                            }
                        }
                    ]
                }
            ]
        }

        entities = validator.extract_entity_references(data)
        assert "binary_sensor.motion" in entities
        assert "light.living_room" in entities


class TestTemplateEntityExtraction:
    """Tests for extracting entities from Jinja2 templates."""

    def test_extract_states_single_quotes(self, temp_config_dir, mock_registries):
        """Test entity extraction from states('entity') pattern."""
        validator = ReferenceValidator(str(temp_config_dir))

        template = "{{ states('sensor.temperature') }}"
        entities = validator.extract_entities_from_template(template)

        assert "sensor.temperature" in entities

    def test_extract_states_double_quotes(self, temp_config_dir, mock_registries):
        """Test entity extraction from states("entity") pattern."""
        validator = ReferenceValidator(str(temp_config_dir))

        template = '{{ states("sensor.humidity") }}'
        entities = validator.extract_entities_from_template(template)

        assert "sensor.humidity" in entities

    def test_extract_states_dot_notation(self, temp_config_dir, mock_registries):
        """Test entity extraction from states.domain.entity pattern."""
        validator = ReferenceValidator(str(temp_config_dir))

        template = "{{ states.sensor.temperature.state }}"
        entities = validator.extract_entities_from_template(template)

        assert "sensor.temperature" in entities

    def test_extract_is_state(self, temp_config_dir, mock_registries):
        """Test entity extraction from is_state() pattern."""
        validator = ReferenceValidator(str(temp_config_dir))

        template = "{{ is_state('binary_sensor.motion', 'on') }}"
        entities = validator.extract_entities_from_template(template)

        assert "binary_sensor.motion" in entities

    def test_extract_state_attr(self, temp_config_dir, mock_registries):
        """Test entity extraction from state_attr() pattern."""
        validator = ReferenceValidator(str(temp_config_dir))

        template = "{{ state_attr('climate.thermostat', 'current_temperature') }}"
        entities = validator.extract_entities_from_template(template)

        assert "climate.thermostat" in entities

    def test_extract_multiple_entities(self, temp_config_dir, mock_registries):
        """Test extraction of multiple entities from complex template."""
        validator = ReferenceValidator(str(temp_config_dir))

        template = """
        {% if is_state('binary_sensor.motion', 'on') %}
          {{ states('sensor.temperature') }}
        {% else %}
          {{ state_attr('climate.thermostat', 'temperature') }}
        {% endif %}
        """
        entities = validator.extract_entities_from_template(template)

        assert "binary_sensor.motion" in entities
        assert "sensor.temperature" in entities
        assert "climate.thermostat" in entities

    def test_precompiled_patterns_exist(self):
        """Test that precompiled patterns are available."""
        assert len(_ENTITY_PATTERNS) > 0
        # Verify patterns are compiled (have findall method)
        for pattern in _ENTITY_PATTERNS:
            assert hasattr(pattern, "findall")


class TestSkipValidation:
    """Tests for should_skip_entity_validation method."""

    def test_skip_ha_input_tag(self, temp_config_dir, mock_registries):
        """Test skipping !input tags."""
        validator = ReferenceValidator(str(temp_config_dir))
        assert validator.should_skip_entity_validation("!input entity_selector") is True

    def test_skip_ha_secret_tag(self, temp_config_dir, mock_registries):
        """Test skipping !secret tags."""
        validator = ReferenceValidator(str(temp_config_dir))
        assert validator.should_skip_entity_validation("!secret some_entity") is True

    def test_skip_uuid_format(self, temp_config_dir, mock_registries):
        """Test skipping UUID format strings."""
        validator = ReferenceValidator(str(temp_config_dir))
        uuid = "abcdef0123456789abcdef0123456789"
        assert validator.should_skip_entity_validation(uuid) is True

    def test_skip_template(self, temp_config_dir, mock_registries):
        """Test skipping Jinja2 templates."""
        validator = ReferenceValidator(str(temp_config_dir))
        assert validator.should_skip_entity_validation("{{ states('sensor.test') }}") is True

    def test_skip_all_keyword(self, temp_config_dir, mock_registries):
        """Test skipping 'all' keyword."""
        validator = ReferenceValidator(str(temp_config_dir))
        assert validator.should_skip_entity_validation("all") is True

    def test_skip_none_keyword(self, temp_config_dir, mock_registries):
        """Test skipping 'none' keyword."""
        validator = ReferenceValidator(str(temp_config_dir))
        assert validator.should_skip_entity_validation("none") is True

    def test_no_skip_normal_entity(self, temp_config_dir, mock_registries):
        """Test normal entity ID is not skipped."""
        validator = ReferenceValidator(str(temp_config_dir))
        assert validator.should_skip_entity_validation("light.living_room") is False


class TestServiceCallExtraction:
    """Tests for service call extraction."""

    def test_extract_simple_service(self, temp_config_dir, mock_registries):
        """Test simple service extraction."""
        validator = ReferenceValidator(str(temp_config_dir))

        data = {
            "action": {
                "service": "light.turn_on",
                "target": {"entity_id": "light.living_room"}
            }
        }

        services = validator.extract_service_calls(data)
        assert "light.turn_on" in services

    def test_extract_nested_services(self, temp_config_dir, mock_registries):
        """Test nested service extraction."""
        validator = ReferenceValidator(str(temp_config_dir))

        data = {
            "action": [
                {"service": "light.turn_on"},
                {"service": "notify.mobile_app"},
                {
                    "choose": [
                        {
                            "sequence": [
                                {"service": "script.run_morning_routine"}
                            ]
                        }
                    ]
                }
            ]
        }

        services = validator.extract_service_calls(data)
        assert "light.turn_on" in services
        assert "notify.mobile_app" in services
        assert "script.run_morning_routine" in services

    def test_skip_template_services(self, temp_config_dir, mock_registries):
        """Test template service calls are skipped."""
        validator = ReferenceValidator(str(temp_config_dir))

        data = {
            "action": {
                "service": "{{ states.automation.test.attributes.service }}"
            }
        }

        services = validator.extract_service_calls(data)
        assert len(services) == 0


class TestServiceCallValidation:
    """Tests for service call validation."""

    def test_builtin_domain_valid(self, temp_config_dir, mock_registries):
        """Test builtin domain services pass validation."""
        validator = ReferenceValidator(str(temp_config_dir))

        services = {"light.turn_on", "switch.turn_off", "climate.set_temperature"}
        validator.validate_service_calls(services, Path("test.yaml"))

        # No errors for builtin domains
        assert not any("light.turn_on" in w for w in validator.warnings)
        assert not any("switch.turn_off" in w for w in validator.warnings)

    def test_unknown_domain_warning(self, temp_config_dir, mock_registries):
        """Test unknown domain generates warning."""
        validator = ReferenceValidator(str(temp_config_dir))

        services = {"custom_integration.do_something"}
        validator.validate_service_calls(services, Path("test.yaml"))

        assert any("custom_integration" in w for w in validator.warnings)

    def test_script_domain_is_builtin(self, temp_config_dir, mock_registries):
        """Test script domain is recognized as builtin (no warning for any script.* service)."""
        # Note: script is a builtin domain, so validate_service_calls doesn't
        # do entity-level validation for scripts. The builtin domain check
        # short-circuits before the script-specific entity check.
        validator = ReferenceValidator(str(temp_config_dir))

        services = {"script.any_script"}
        validator.validate_service_calls(services, Path("test.yaml"))
        # Script is a builtin domain, so no warnings expected
        assert len(validator.warnings) == 0


class TestDeviceReferenceExtraction:
    """Tests for device reference extraction."""

    def test_extract_device_id(self, temp_config_dir, mock_registries):
        """Test device_id extraction."""
        validator = ReferenceValidator(str(temp_config_dir))

        data = {
            "trigger": {
                "platform": "device",
                "device_id": "device123",
                "type": "turned_on"
            }
        }

        devices = validator.extract_device_references(data)
        assert "device123" in devices

    def test_extract_device_ids_list(self, temp_config_dir, mock_registries):
        """Test device_ids list extraction."""
        validator = ReferenceValidator(str(temp_config_dir))

        data = {
            "device_ids": ["device123", "device456"]
        }

        devices = validator.extract_device_references(data)
        assert "device123" in devices
        assert "device456" in devices

    def test_skip_input_device(self, temp_config_dir, mock_registries):
        """Test !input device_id is skipped."""
        validator = ReferenceValidator(str(temp_config_dir))

        data = {
            "device_id": "!input device_selector"
        }

        devices = validator.extract_device_references(data)
        assert len(devices) == 0


class TestAreaReferenceExtraction:
    """Tests for area reference extraction."""

    def test_extract_area_id(self, temp_config_dir, mock_registries):
        """Test area_id extraction."""
        validator = ReferenceValidator(str(temp_config_dir))

        data = {
            "target": {
                "area_id": "living_room"
            }
        }

        areas = validator.extract_area_references(data)
        assert "living_room" in areas

    def test_extract_area_ids_list(self, temp_config_dir, mock_registries):
        """Test area_ids list extraction."""
        validator = ReferenceValidator(str(temp_config_dir))

        data = {
            "target": {
                "area_ids": ["living_room", "kitchen", "bedroom"]
            }
        }

        areas = validator.extract_area_references(data)
        assert "living_room" in areas
        assert "kitchen" in areas
        assert "bedroom" in areas


class TestIsUUIDFormat:
    """Tests for UUID format detection."""

    def test_valid_uuid(self, temp_config_dir, mock_registries):
        """Test valid UUID format detection."""
        validator = ReferenceValidator(str(temp_config_dir))

        # 32 hex characters
        assert validator.is_uuid_format("abcdef0123456789abcdef0123456789") is True
        assert validator.is_uuid_format("00000000000000000000000000000000") is True

    def test_invalid_uuid(self, temp_config_dir, mock_registries):
        """Test invalid UUID format detection."""
        validator = ReferenceValidator(str(temp_config_dir))

        # Entity ID format
        assert validator.is_uuid_format("light.living_room") is False
        # Too short
        assert validator.is_uuid_format("abc123") is False
        # Contains non-hex
        assert validator.is_uuid_format("ghijkl0123456789abcdef0123456789") is False


class TestIsTemplate:
    """Tests for template detection."""

    def test_simple_template(self, temp_config_dir, mock_registries):
        """Test simple template detection."""
        validator = ReferenceValidator(str(temp_config_dir))

        assert validator.is_template("{{ states('sensor.temp') }}") is True
        assert validator.is_template("{{ 1 + 1 }}") is True

    def test_multiline_template(self, temp_config_dir, mock_registries):
        """Test multiline template detection."""
        validator = ReferenceValidator(str(temp_config_dir))

        template = """{% if is_state('light.living_room', 'on') %}
on
{% else %}
off
{% endif %}"""
        # Note: This won't match {{ }} pattern - it's a statement template
        # The is_template function only checks for {{ }}
        assert validator.is_template(template) is False

    def test_not_a_template(self, temp_config_dir, mock_registries):
        """Test non-template strings."""
        validator = ReferenceValidator(str(temp_config_dir))

        assert validator.is_template("light.living_room") is False
        assert validator.is_template("on") is False
        assert validator.is_template("{ not a template }") is False
