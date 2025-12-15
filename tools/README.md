# Home Assistant Validation Tools

This directory contains validation and utility tools for Home Assistant configuration management.

## Validation Tools

### yaml_validator.py

Validates YAML syntax and structure for Home Assistant configuration files.

**Usage:**
```bash
python tools/yaml_validator.py [config_dir] [-v|--verbose]
```

**Features:**
- Validates YAML syntax with HA-specific tags (!include, !secret, !input, etc.)
- Checks automation structure (triggers, actions required)
- Checks script structure (sequence required)
- Warns about deprecated patterns (enabled: false, device_id)
- Warns about hardcoded URLs that should be in secrets.yaml

### reference_validator.py

Validates that all entity, device, and area references exist in the HA registry.

**Usage:**
```bash
python tools/reference_validator.py [config_dir] [-v|--verbose]
```

**Features:**
- Validates entity_id references against entity registry
- Validates device_id references against device registry
- Validates area_id references against area registry
- Extracts entity references from Jinja2 templates
- Validates service calls against known domains
- Validates blueprint inputs against blueprint definitions

### ha_official_validator.py

Runs Home Assistant's official check_config validation.

**Usage:**
```bash
python tools/ha_official_validator.py [config_dir]
```

**Features:**
- Uses HA's own validation tools for accurate results
- Detects HA version and checks compatibility
- Reclassifies environment-specific errors as warnings
- Configurable patterns via validation_config.yaml

### run_tests.py

Orchestrates running all validators with parallel execution support.

**Usage:**
```bash
python tools/run_tests.py [config_dir] [-p|--parallel] [-v|--verbose]
```

**Options:**
- `-p, --parallel`: Run validators in parallel (faster)
- `-v, --verbose`: Show debug output
- Default: Sequential execution

## Utility Tools

### entity_explorer.py

Interactive tool for exploring the HA entity registry.

**Usage:**
```bash
python tools/entity_explorer.py [options]
```

**Options:**
- `--search TERM`: Search entities by name, ID, or device class
- `--domain DOMAIN`: Show entities from specific domain (e.g., climate, sensor)
- `--area AREA`: Show entities from specific area
- `--full`: Show complete detailed output

### reload_config.py

Reloads Home Assistant configuration via the API.

**Usage:**
```bash
python tools/reload_config.py
```

### ha_api_diagnostic.py

Diagnostic tool for testing HA API connectivity and inspecting API responses.

### ha_config_validator.py

Additional configuration validation utilities.

## Shared Modules

### ha_yaml_loader.py

Shared YAML loader that handles Home Assistant specific tags:
- `!include` - Include another YAML file
- `!include_dir_named` - Include directory as named dict
- `!include_dir_merge_named` - Include and merge directory as named dict
- `!include_dir_merge_list` - Include and merge directory as list
- `!include_dir_list` - Include directory as list
- `!input` - Blueprint input reference
- `!secret` - Secret value reference

### validation_config_loader.py

Singleton configuration loader for validation settings. Loads configuration from `validation_config.yaml`.

### validation_config.yaml

External configuration for validation patterns and settings:
- `min_ha_version`: Minimum supported HA version
- `environment_patterns`: Error patterns specific to test environments
- `deprecated_patterns`: Patterns to warn about
- `stderr_ignore_patterns`: Stderr messages to ignore
- `timeouts`: Timeout settings for each validator
- `builtin_service_domains`: Known HA service domains
- `hardcoded_url_patterns`: URL patterns that should be in secrets
- `mqtt_warning_patterns`: MQTT topic patterns to warn about

## Running Validation

### Full Validation Suite

```bash
# Sequential (default)
python tools/run_tests.py config/

# Parallel (faster)
python tools/run_tests.py config/ --parallel

# With debug output
python tools/run_tests.py config/ --verbose
```

### Individual Validators

```bash
# YAML syntax only
python tools/yaml_validator.py config/

# Entity references only
python tools/reference_validator.py config/

# Official HA validation only
python tools/ha_official_validator.py config/
```

## Environment Variables

- `HA_TOKEN`: Home Assistant long-lived access token
- `HA_URL`: Home Assistant URL (e.g., http://homeassistant:8123)
- `HA_HOST`: SSH hostname for rsync operations
- `HA_VALIDATION_STRICT`: Set to `false` for warning-only validation hooks

## Development

All tools require Python 3.11+ and the dependencies in `pyproject.toml`:
- `homeassistant`: For official validation
- `voluptuous`: Schema validation
- `pyyaml`: YAML parsing

Activate the virtual environment before running:
```bash
source venv/bin/activate
python tools/<tool>.py
```
