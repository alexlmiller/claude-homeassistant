"""Shared fixtures for Home Assistant validation tool tests."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with basic structure."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create .storage directory
    storage_dir = config_dir / ".storage"
    storage_dir.mkdir()

    return config_dir


@pytest.fixture
def mock_entity_registry(temp_config_dir: Path) -> Path:
    """Create a mock entity registry with sample entities."""
    storage_dir = temp_config_dir / ".storage"
    registry_file = storage_dir / "core.entity_registry"

    registry_data = {
        "version": 1,
        "minor_version": 12,
        "key": "core.entity_registry",
        "data": {
            "entities": [
                {
                    "entity_id": "light.living_room",
                    "platform": "hue",
                    "unique_id": "abc123",
                    "disabled_by": None,
                    "area_id": "living_room"
                },
                {
                    "entity_id": "sensor.temperature",
                    "platform": "template",
                    "unique_id": "temp123",
                    "disabled_by": None,
                    "area_id": "living_room"
                },
                {
                    "entity_id": "switch.disabled_switch",
                    "platform": "template",
                    "unique_id": "sw123",
                    "disabled_by": "user",
                    "area_id": None
                },
                {
                    "entity_id": "binary_sensor.motion",
                    "platform": "template",
                    "unique_id": "motion123",
                    "disabled_by": None,
                    "area_id": "hallway"
                },
                {
                    "entity_id": "climate.thermostat",
                    "platform": "generic_thermostat",
                    "unique_id": "therm123",
                    "disabled_by": None,
                    "area_id": "living_room"
                }
            ]
        }
    }

    registry_file.write_text(json.dumps(registry_data))
    return registry_file


@pytest.fixture
def mock_device_registry(temp_config_dir: Path) -> Path:
    """Create a mock device registry."""
    storage_dir = temp_config_dir / ".storage"
    registry_file = storage_dir / "core.device_registry"

    registry_data = {
        "version": 1,
        "minor_version": 6,
        "key": "core.device_registry",
        "data": {
            "devices": [
                {
                    "id": "device123",
                    "name": "Living Room Light",
                    "area_id": "living_room"
                },
                {
                    "id": "device456",
                    "name": "Temperature Sensor",
                    "area_id": "kitchen"
                }
            ]
        }
    }

    registry_file.write_text(json.dumps(registry_data))
    return registry_file


@pytest.fixture
def mock_area_registry(temp_config_dir: Path) -> Path:
    """Create a mock area registry."""
    storage_dir = temp_config_dir / ".storage"
    registry_file = storage_dir / "core.area_registry"

    registry_data = {
        "version": 1,
        "minor_version": 6,
        "key": "core.area_registry",
        "data": {
            "areas": [
                {"id": "living_room", "name": "Living Room"},
                {"id": "kitchen", "name": "Kitchen"},
                {"id": "hallway", "name": "Hallway"}
            ]
        }
    }

    registry_file.write_text(json.dumps(registry_data))
    return registry_file


@pytest.fixture
def mock_registries(mock_entity_registry, mock_device_registry, mock_area_registry):
    """Create all mock registries."""
    return {
        "entity": mock_entity_registry,
        "device": mock_device_registry,
        "area": mock_area_registry
    }


@pytest.fixture
def valid_automation_yaml() -> str:
    """Return valid automation YAML content."""
    return """
- id: test_automation_1
  alias: "Test Automation"
  trigger:
    - platform: state
      entity_id: binary_sensor.motion
      to: "on"
  action:
    - service: light.turn_on
      target:
        entity_id: light.living_room
"""


@pytest.fixture
def invalid_automation_yaml() -> str:
    """Return invalid automation YAML (missing trigger)."""
    return """
- id: test_automation_missing_trigger
  alias: "Missing Trigger Automation"
  action:
    - service: light.turn_on
      target:
        entity_id: light.living_room
"""


@pytest.fixture
def blueprint_automation_yaml() -> str:
    """Return blueprint automation YAML content."""
    return """
- id: blueprint_automation
  alias: "Blueprint Test"
  use_blueprint:
    path: homeassistant/motion_light.yaml
    input:
      motion_entity: binary_sensor.motion
      light_target:
        entity_id: light.living_room
"""


@pytest.fixture
def valid_script_yaml() -> str:
    """Return valid script YAML content."""
    return """
test_script:
  alias: "Test Script"
  sequence:
    - service: light.turn_off
      target:
        entity_id: light.living_room
"""


@pytest.fixture
def automation_with_templates() -> str:
    """Return automation with Jinja2 templates."""
    return """
- id: template_automation
  alias: "Template Test"
  trigger:
    - platform: template
      value_template: "{{ states('sensor.temperature') | float > 25 }}"
  action:
    - service: light.turn_on
      target:
        entity_id: >-
          {% if is_state('binary_sensor.motion', 'on') %}
            light.living_room
          {% else %}
            light.kitchen
          {% endif %}
"""


@pytest.fixture
def automation_with_deprecated_patterns() -> str:
    """Return automation with deprecated patterns."""
    return """
- id: deprecated_automation
  alias: "Deprecated Test"
  enabled: false
  trigger:
    - platform: device
      device_id: abc123
      domain: light
      type: turned_on
  action:
    - service: light.turn_off
      target:
        entity_id: light.living_room
"""


@pytest.fixture
def write_yaml_file(temp_config_dir: Path):
    """Fixture factory to write YAML files to temp config dir."""
    def _write(filename: str, content: str) -> Path:
        filepath = temp_config_dir / filename
        filepath.write_text(content)
        return filepath
    return _write
