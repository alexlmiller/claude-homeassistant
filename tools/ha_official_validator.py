#!/usr/bin/env python3
"""Official Home Assistant configuration validator using the actual HA package.

This leverages Home Assistant's own validation tools for the most
accurate results.
"""

import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import yaml


class ValidationConfig:
    """Manages validation configuration from external YAML file."""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize validation config from YAML file."""
        if config_path is None:
            config_path = Path(__file__).parent / "validation_config.yaml"

        self.config: Dict = {}
        self.environment_patterns: List[str] = []
        self.stderr_ignore_patterns: List[str] = []
        self.min_ha_version: str = "2024.1.0"

        self._load_config(config_path)

    def _load_config(self, config_path: Path) -> None:
        """Load configuration from YAML file."""
        if not config_path.exists():
            # Use default patterns if config file missing
            self._use_defaults()
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}

            # Extract environment patterns
            env_patterns = self.config.get("environment_patterns", [])
            self.environment_patterns = [
                p.get("pattern", "") for p in env_patterns if p.get("pattern")
            ]

            # Extract stderr ignore patterns
            self.stderr_ignore_patterns = self.config.get(
                "stderr_ignore_patterns", []
            )

            # Get minimum HA version
            self.min_ha_version = self.config.get("min_ha_version", "2024.1.0")

        except Exception as e:
            print(f"Warning: Could not load validation config: {e}")
            self._use_defaults()

    def _use_defaults(self) -> None:
        """Use default patterns if config file unavailable."""
        self.environment_patterns = [
            "Integration 'mobile_app' could not be loaded",
            "Integration 'mobile_app' does not support",
            "Unable to install package",
            "Failed to build `",
            "not a file for dictionary value",
            "Requirements for stream not found",
            "Invalid config for 'http'",
            "libturbojpeg",
            "turbojpeg library",
            "RuntimeError:",
            "raise RuntimeError",
            "Blueprint '",
            "generated invalid automation",
        ]
        self.stderr_ignore_patterns = [
            "debug",
            "info:",
            "starting",
            "voluptuous",
            "setup of domain",
            "setup of platform",
            "loading",
            "initialized",
        ]

    def get_timeout(self, key: str) -> int:
        """Get timeout value from config."""
        timeouts = self.config.get("timeouts", {})
        return timeouts.get(key, 120)


class HAOfficialValidator:
    """Validates Home Assistant configuration using the official HA package."""

    def __init__(self, config_dir: str = "config"):
        """Initialize the HAOfficialValidator."""
        self.config_dir = Path(config_dir).resolve()
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        self.validation_config = ValidationConfig()
        self.ha_version: Optional[str] = None

    def get_ha_version(self) -> Optional[str]:
        """Get the installed Home Assistant version."""
        if self.ha_version is not None:
            return self.ha_version

        try:
            import homeassistant.const as ha_const

            self.ha_version = ha_const.__version__
            return self.ha_version
        except ImportError:
            return None

    def check_version_compatibility(self) -> bool:
        """Check if installed HA version meets minimum requirements."""
        version = self.get_ha_version()
        if version is None:
            self.warnings.append(
                "Could not determine Home Assistant version - "
                "ensure homeassistant package is installed"
            )
            return True  # Continue validation

        min_version = self.validation_config.min_ha_version

        try:
            from packaging import version as pkg_version

            installed = pkg_version.parse(version)
            minimum = pkg_version.parse(min_version)

            if installed < minimum:
                self.warnings.append(
                    f"Home Assistant version {version} is below minimum "
                    f"supported version {min_version}"
                )
                return True  # Continue but warn
        except ImportError:
            # packaging module not available, do simple string comparison
            if version < min_version:
                self.warnings.append(
                    f"Home Assistant version {version} may be below minimum "
                    f"supported version {min_version}"
                )

        self.info.append(f"Home Assistant version: {version}")
        return True

    def run_ha_check_config(self) -> bool:
        """Run Home Assistant's official check_config script."""
        timeout = self.validation_config.get_timeout("ha_check_config")

        try:
            # Use the hass command to check configuration
            cmd = [
                sys.executable,
                "-m",
                "homeassistant",
                "--config",
                str(self.config_dir),
                "--script",
                "check_config",
            ]

            # Run the command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.config_dir),
            )

            # Parse the output
            self.parse_check_config_output(result.stdout, result.stderr)

            # Return success if no actual errors (environment warnings don't count)
            return len(self.errors) == 0

        except subprocess.TimeoutExpired:
            self.errors.append(
                f"Home Assistant configuration check timed out after {timeout}s"
            )
            return False
        except FileNotFoundError:
            self.errors.append(
                "Home Assistant not found. "
                "Please install with: pip install homeassistant"
            )
            return False
        except Exception as e:
            self.errors.append(f"Failed to run Home Assistant config check: {e}")
            return False

    def is_environment_error(self, line: str) -> bool:
        """Check if an error is environment-specific and should be treated as a warning."""
        return any(
            pattern in line
            for pattern in self.validation_config.environment_patterns
        )

    def should_ignore_stderr(self, line: str) -> bool:
        """Check if a stderr line should be ignored."""
        line_lower = line.lower()
        return any(
            pattern.lower() in line_lower
            for pattern in self.validation_config.stderr_ignore_patterns
        )

    def parse_check_config_output(self, stdout: str, stderr: str):
        """Parse Home Assistant check_config output."""
        # Parse stdout
        if stdout:
            lines = stdout.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Look for specific patterns
                if "Testing configuration at" in line:
                    self.info.append(f"HA Check: {line}")
                elif "Configuration check successful!" in line:
                    self.info.append(f"HA Check: {line}")
                elif "errors" in line.lower() and "found" in line.lower():
                    if "0 errors" in line.lower():
                        self.info.append(f"HA Check: {line}")
                    else:
                        # Mark as potential error - will be reclassified later if all
                        # actual errors turn out to be environment-specific
                        self.errors.append(f"HA Check (summary): {line}")
                elif "ERROR" in line or "Error" in line:
                    # Check if this is an environment-specific error
                    if self.is_environment_error(line):
                        self.warnings.append(f"HA Check (env): {line}")
                    else:
                        self.errors.append(f"HA Check: {line}")
                elif "WARNING" in line or "Warning" in line:
                    self.warnings.append(f"HA Check: {line}")
                else:
                    # Include other informational lines
                    if line and not line.startswith("INFO:"):
                        self.info.append(f"HA Check: {line}")

        # Parse stderr for actual errors
        if stderr:
            lines = stderr.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Filter out debug/info messages
                if self.should_ignore_stderr(line):
                    continue

                # Check if this is an environment-specific error
                if self.is_environment_error(line):
                    self.warnings.append(f"HA Check (env): {line}")
                else:
                    # This is likely an actual error
                    self.errors.append(f"HA Error: {line}")

    def reclassify_summary_errors(self):
        """Move summary errors to warnings if all actual errors are environment-specific.

        This handles the case where HA reports "Found N errors:" but all of those
        errors are actually environment-specific (e.g., mobile_app can't be loaded
        in test environment).
        """
        # Check if we only have summary errors (no real errors)
        real_errors = [e for e in self.errors if "(summary)" not in e]
        summary_errors = [e for e in self.errors if "(summary)" in e]

        if not real_errors and summary_errors:
            # All errors are just summaries - move to warnings
            for err in summary_errors:
                self.warnings.append(err.replace("(summary)", "(env-only)"))
            self.errors = []

    def validate_all(self) -> bool:
        """Run complete validation using Home Assistant."""
        if not self.config_dir.exists():
            self.errors.append(f"Config directory {self.config_dir} does not exist")
            return False

        # Check if configuration.yaml exists
        config_file = self.config_dir / "configuration.yaml"
        if not config_file.exists():
            self.errors.append("configuration.yaml not found")
            return False

        # Check version compatibility
        self.check_version_compatibility()

        # Run the official Home Assistant validation
        self.run_ha_check_config()

        # Post-process to reclassify summary-only errors
        self.reclassify_summary_errors()

        # Return true if no real errors remain
        return len(self.errors) == 0

    def print_results(self):
        """Print validation results."""
        if self.info:
            print("INFO:")
            for info in self.info:
                print(f"  ℹ️  {info}")
            print()

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
            print("✅ Home Assistant configuration is valid!")
        elif not self.errors:
            print("✅ Home Assistant configuration is valid (with warnings)")
        else:
            print("❌ Home Assistant configuration validation failed")


def main():
    """Run Home Assistant configuration validation from command line."""
    config_dir = sys.argv[1] if len(sys.argv) > 1 else "config"

    validator = HAOfficialValidator(config_dir)
    is_valid = validator.validate_all()
    validator.print_results()

    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
