"""Tests for yaml_validator.py."""

import sys
from pathlib import Path

import pytest
import yaml

# Add tools directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from yaml_validator import YAMLValidator


class TestYAMLValidator:
    """Tests for the YAMLValidator class."""

    def test_validate_yaml_syntax_valid_file(self, temp_config_dir):
        """Test validation of valid YAML file."""
        yaml_file = temp_config_dir / "test.yaml"
        yaml_file.write_text("key: value\nlist:\n  - item1\n  - item2\n")

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_yaml_syntax(yaml_file) is True
        assert len(validator.errors) == 0

    def test_validate_yaml_syntax_invalid_yaml(self, temp_config_dir):
        """Test validation of invalid YAML file."""
        yaml_file = temp_config_dir / "invalid.yaml"
        yaml_file.write_text("key: value\n  bad_indent: oops\n")

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_yaml_syntax(yaml_file) is False
        assert len(validator.errors) == 1
        assert "YAML syntax error" in validator.errors[0]

    def test_validate_yaml_syntax_file_not_found(self, temp_config_dir):
        """Test validation of non-existent file."""
        yaml_file = temp_config_dir / "nonexistent.yaml"

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_yaml_syntax(yaml_file) is False
        assert len(validator.errors) == 1
        assert "File not found" in validator.errors[0]

    def test_validate_file_encoding_utf8(self, temp_config_dir):
        """Test UTF-8 encoding validation passes."""
        yaml_file = temp_config_dir / "utf8.yaml"
        yaml_file.write_text("key: value with unicode \u00e9\n", encoding="utf-8")

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_file_encoding(yaml_file) is True
        assert len(validator.errors) == 0

    def test_validate_file_encoding_non_utf8(self, temp_config_dir):
        """Test non-UTF-8 encoding validation fails."""
        yaml_file = temp_config_dir / "latin1.yaml"
        yaml_file.write_bytes(b"key: value with \xe9\n")  # Latin-1 encoded

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_file_encoding(yaml_file) is False
        assert len(validator.errors) == 1
        assert "UTF-8 encoded" in validator.errors[0]


class TestAutomationValidation:
    """Tests for automation structure validation."""

    def test_valid_automation(self, temp_config_dir, valid_automation_yaml):
        """Test valid automation passes validation."""
        yaml_file = temp_config_dir / "automations.yaml"
        yaml_file.write_text(valid_automation_yaml)

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_automations_structure(yaml_file) is True
        assert len(validator.errors) == 0

    def test_automation_missing_trigger(self, temp_config_dir, invalid_automation_yaml):
        """Test automation missing trigger fails validation."""
        yaml_file = temp_config_dir / "automations.yaml"
        yaml_file.write_text(invalid_automation_yaml)

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_automations_structure(yaml_file) is False
        assert any("missing 'trigger'" in e for e in validator.errors)

    def test_automation_missing_action(self, temp_config_dir):
        """Test automation missing action fails validation."""
        yaml_content = """
- id: missing_action_automation
  alias: "Missing Action"
  trigger:
    - platform: state
      entity_id: binary_sensor.test
"""
        yaml_file = temp_config_dir / "automations.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_automations_structure(yaml_file) is False
        assert any("missing 'action'" in e for e in validator.errors)

    def test_blueprint_automation_valid(self, temp_config_dir, blueprint_automation_yaml):
        """Test blueprint automation passes validation."""
        yaml_file = temp_config_dir / "automations.yaml"
        yaml_file.write_text(blueprint_automation_yaml)

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_automations_structure(yaml_file) is True
        # Blueprint automations shouldn't require trigger/action
        assert not any("missing 'trigger'" in e for e in validator.errors)
        assert not any("missing 'action'" in e for e in validator.errors)

    def test_empty_automations_file(self, temp_config_dir):
        """Test empty automations file is valid."""
        yaml_file = temp_config_dir / "automations.yaml"
        yaml_file.write_text("")

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_automations_structure(yaml_file) is True

    def test_automations_not_a_list(self, temp_config_dir):
        """Test automations file that's not a list fails."""
        yaml_content = """
automation_1:
  alias: "Not a list"
  trigger: []
"""
        yaml_file = temp_config_dir / "automations.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_automations_structure(yaml_file) is False
        assert any("must be a list" in e for e in validator.errors)

    def test_automation_missing_alias_warning(self, temp_config_dir):
        """Test automation missing alias generates warning."""
        yaml_content = """
- id: no_alias_automation
  trigger:
    - platform: state
      entity_id: binary_sensor.test
  action:
    - service: light.turn_on
"""
        yaml_file = temp_config_dir / "automations.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        validator.validate_automations_structure(yaml_file)
        assert any("missing 'alias'" in w for w in validator.warnings)

    def test_automation_with_triggers_plural(self, temp_config_dir):
        """Test automation with plural 'triggers' is valid."""
        yaml_content = """
- id: plural_triggers
  alias: "Plural Triggers Test"
  triggers:
    - trigger: state
      entity_id: binary_sensor.test
  actions:
    - action: light.turn_on
"""
        yaml_file = temp_config_dir / "automations.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_automations_structure(yaml_file) is True


class TestScriptValidation:
    """Tests for script structure validation."""

    def test_valid_script(self, temp_config_dir, valid_script_yaml):
        """Test valid script passes validation."""
        yaml_file = temp_config_dir / "scripts.yaml"
        yaml_file.write_text(valid_script_yaml)

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_scripts_structure(yaml_file) is True
        assert len(validator.errors) == 0

    def test_script_missing_sequence(self, temp_config_dir):
        """Test script missing sequence fails validation."""
        yaml_content = """
bad_script:
  alias: "Missing Sequence"
"""
        yaml_file = temp_config_dir / "scripts.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_scripts_structure(yaml_file) is False
        assert any("missing required 'sequence'" in e for e in validator.errors)

    def test_empty_scripts_file(self, temp_config_dir):
        """Test empty scripts file is valid."""
        yaml_file = temp_config_dir / "scripts.yaml"
        yaml_file.write_text("")

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_scripts_structure(yaml_file) is True

    def test_blueprint_script_valid(self, temp_config_dir):
        """Test blueprint script passes validation."""
        yaml_content = """
blueprint_script:
  alias: "Blueprint Script"
  use_blueprint:
    path: homeassistant/script.yaml
    input:
      target_entity: light.living_room
"""
        yaml_file = temp_config_dir / "scripts.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_scripts_structure(yaml_file) is True


class TestDeprecatedPatterns:
    """Tests for deprecated pattern detection."""

    def test_enabled_false_warning(self, temp_config_dir, automation_with_deprecated_patterns):
        """Test 'enabled: false' generates warning."""
        yaml_file = temp_config_dir / "automations.yaml"
        yaml_file.write_text(automation_with_deprecated_patterns)

        validator = YAMLValidator(str(temp_config_dir))
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        validator.check_deprecated_patterns(data, yaml_file)

        assert any("enabled: false" in w or "disabling automations via the UI" in w
                   for w in validator.warnings)

    def test_device_id_warning(self, temp_config_dir, automation_with_deprecated_patterns):
        """Test device_id usage generates warning."""
        yaml_file = temp_config_dir / "automations.yaml"
        yaml_file.write_text(automation_with_deprecated_patterns)

        validator = YAMLValidator(str(temp_config_dir))
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        validator.check_deprecated_patterns(data, yaml_file)

        assert any("device_id" in w for w in validator.warnings)

    def test_no_deprecation_warnings_for_clean_config(self, temp_config_dir, valid_automation_yaml):
        """Test clean config doesn't generate deprecation warnings."""
        yaml_file = temp_config_dir / "automations.yaml"
        yaml_file.write_text(valid_automation_yaml)

        validator = YAMLValidator(str(temp_config_dir))
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        validator.check_deprecated_patterns(data, yaml_file)

        # Should only have best practice warnings, not deprecation warnings
        assert not any("device_id" in w for w in validator.warnings)
        assert not any("enabled: false" in w for w in validator.warnings)


class TestHardcodedURLs:
    """Tests for hardcoded URL detection."""

    def test_nabu_casa_url_warning(self, temp_config_dir):
        """Test nabu.casa URL generates warning."""
        yaml_content = """
external_url: "https://my-home.ui.nabu.casa"
"""
        yaml_file = temp_config_dir / "configuration.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        validator.check_hardcoded_urls(data, yaml_file)

        assert any("nabu.casa" in w.lower() or "secrets.yaml" in w.lower()
                   for w in validator.warnings)

    def test_duckdns_url_warning(self, temp_config_dir):
        """Test duckdns.org URL generates warning."""
        yaml_content = """
http:
  base_url: "https://myhome.duckdns.org"
"""
        yaml_file = temp_config_dir / "configuration.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        validator.check_hardcoded_urls(data, yaml_file)

        assert any("duckdns" in w.lower() or "secrets.yaml" in w.lower()
                   for w in validator.warnings)


class TestMQTTTopics:
    """Tests for MQTT topic validation."""

    def test_placeholder_topic_warning(self, temp_config_dir):
        """Test placeholder MQTT topic generates warning."""
        yaml_content = """
mqtt:
  sensor:
    - name: "Test Sensor"
      state_topic: "placeholder/topic"
"""
        yaml_file = temp_config_dir / "config-mqtt-sensors.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        validator.check_mqtt_topics(data, yaml_file)

        assert any("placeholder" in w.lower() for w in validator.warnings)

    def test_example_topic_warning(self, temp_config_dir):
        """Test example MQTT topic generates warning."""
        yaml_content = """
sensor:
  - name: "Test"
    state_topic: "example/sensor/state"
"""
        yaml_file = temp_config_dir / "config-mqtt-sensors.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        validator.check_mqtt_topics(data, yaml_file)

        assert any("example" in w.lower() for w in validator.warnings)


class TestConfigurationValidation:
    """Tests for configuration.yaml structure validation."""

    def test_missing_homeassistant_section_warning(self, temp_config_dir):
        """Test missing homeassistant section generates warning."""
        yaml_content = """
default_config:
logger:
  default: info
"""
        yaml_file = temp_config_dir / "configuration.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        validator.validate_configuration_structure(yaml_file)

        assert any("homeassistant" in w for w in validator.warnings)

    def test_configuration_not_dict_error(self, temp_config_dir):
        """Test configuration that's not a dict fails."""
        yaml_content = """
- item1
- item2
"""
        yaml_file = temp_config_dir / "configuration.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_configuration_structure(yaml_file) is False
        assert any("must be a dictionary" in e for e in validator.errors)

    def test_deprecated_key_warning(self, temp_config_dir):
        """Test deprecated key generates warning."""
        yaml_content = """
homeassistant:
  name: Test
discovery:
introduction:
"""
        yaml_file = temp_config_dir / "configuration.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        validator.validate_configuration_structure(yaml_file)

        assert any("discovery" in w and "deprecated" in w for w in validator.warnings)
        assert any("introduction" in w and "deprecated" in w for w in validator.warnings)


class TestValidateAll:
    """Tests for validate_all method."""

    def test_validate_all_valid_config(self, temp_config_dir, valid_automation_yaml, valid_script_yaml):
        """Test validate_all passes with valid config."""
        # Create configuration.yaml
        config_yaml = """
homeassistant:
  name: "Test Home"
default_config:
"""
        (temp_config_dir / "configuration.yaml").write_text(config_yaml)
        (temp_config_dir / "automations.yaml").write_text(valid_automation_yaml)
        (temp_config_dir / "scripts.yaml").write_text(valid_script_yaml)

        validator = YAMLValidator(str(temp_config_dir))
        assert validator.validate_all() is True

    def test_validate_all_skips_secrets(self, temp_config_dir):
        """Test validate_all skips secrets.yaml."""
        # Create secrets.yaml with invalid YAML (should be skipped)
        (temp_config_dir / "secrets.yaml").write_text("invalid: yaml\n  bad: indent")
        (temp_config_dir / "configuration.yaml").write_text("homeassistant:\n  name: Test")

        validator = YAMLValidator(str(temp_config_dir))
        # Should not fail because secrets.yaml is skipped
        result = validator.validate_all()
        assert not any("secrets.yaml" in e for e in validator.errors)

    def test_validate_all_nonexistent_directory(self):
        """Test validate_all with non-existent directory."""
        validator = YAMLValidator("/nonexistent/path")
        assert validator.validate_all() is False
        assert any("does not exist" in e for e in validator.errors)

    def test_validate_all_empty_directory(self, temp_config_dir):
        """Test validate_all with empty directory."""
        validator = YAMLValidator(str(temp_config_dir))
        result = validator.validate_all()
        # Empty directory should pass but generate warning
        assert result is True
        assert any("No YAML files found" in w for w in validator.warnings)


class TestHAYamlTags:
    """Tests for Home Assistant specific YAML tags."""

    def test_include_tag_valid(self, temp_config_dir):
        """Test !include tag is handled."""
        yaml_content = """
automation: !include automations.yaml
script: !include scripts.yaml
"""
        yaml_file = temp_config_dir / "configuration.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        # Should not error on !include tags
        assert validator.validate_yaml_syntax(yaml_file) is True

    def test_secret_tag_valid(self, temp_config_dir):
        """Test !secret tag is handled."""
        yaml_content = """
homeassistant:
  auth_providers:
    - type: homeassistant
  latitude: !secret latitude
  longitude: !secret longitude
"""
        yaml_file = temp_config_dir / "configuration.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        # Should not error on !secret tags
        assert validator.validate_yaml_syntax(yaml_file) is True

    def test_input_tag_valid(self, temp_config_dir):
        """Test !input tag is handled (used in blueprints)."""
        yaml_content = """
variables:
  motion_entity: !input motion_sensor
  light_entity: !input light_target
"""
        yaml_file = temp_config_dir / "test.yaml"
        yaml_file.write_text(yaml_content)

        validator = YAMLValidator(str(temp_config_dir))
        # Should not error on !input tags
        assert validator.validate_yaml_syntax(yaml_file) is True
