#!/usr/bin/env python3
"""Official Home Assistant configuration validator using the actual HA package.

This leverages Home Assistant's own validation tools for the most
accurate results.
"""

import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# Import shared modules
from validation_config_loader import ValidationConfig

logger = logging.getLogger(__name__)


class HAOfficialValidator:
    """Validates Home Assistant configuration using the official HA package."""

    def __init__(self, config_dir: str = "config"):
        """Initialize the HAOfficialValidator."""
        self.config_dir = Path(config_dir).resolve()
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        self.validation_config = ValidationConfig.get_instance()
        self.ha_version: Optional[str] = None

    def get_ha_version(self) -> Optional[str]:
        """Get the installed Home Assistant version.

        Returns:
            Version string (e.g., '2024.12.0') or None if not installed.
        """
        if self.ha_version is not None:
            return self.ha_version

        try:
            import homeassistant.const as ha_const

            self.ha_version = ha_const.__version__
            return self.ha_version
        except ImportError:
            logger.warning("Home Assistant package not installed")
            return None
        except Exception as e:
            logger.warning(f"Could not determine HA version: {e}")
            return None

    def check_version_compatibility(self) -> bool:
        """Check if installed HA version meets minimum requirements.

        Returns:
            True if compatible, False otherwise.
        """
        version = self.get_ha_version()
        if version is None:
            self.warnings.append(
                "Could not determine Home Assistant version - skipping version check"
            )
            return True

        min_version = self.validation_config.min_ha_version
        if not min_version:
            return True

        try:
            # Parse versions for comparison (handles versions like 2024.12.0)
            current_parts = self._parse_version(version)
            min_parts = self._parse_version(min_version)

            if current_parts < min_parts:
                self.warnings.append(
                    f"Home Assistant version {version} is below minimum "
                    f"supported version {min_version}"
                )
                return False

            self.info.append(f"Home Assistant version: {version}")
            return True

        except Exception as e:
            logger.warning(f"Version comparison failed: {e}")
            self.info.append(f"Home Assistant version: {version}")
            return True

    def _parse_version(self, version_str: str) -> Tuple[int, ...]:
        """Parse a version string into comparable tuple.

        Args:
            version_str: Version string like '2024.12.0' or '2024.12.0b1'

        Returns:
            Tuple of version components for comparison.
        """
        # Remove any suffix like 'b1', 'dev', etc.
        clean_version = re.sub(r"[a-zA-Z].*$", "", version_str)
        parts = clean_version.split(".")
        return tuple(int(p) for p in parts if p.isdigit())

    def run_ha_check_config(self) -> bool:
        """Run Home Assistant's official check_config script."""
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

            # Run the command with configurable timeout
            timeout = self.validation_config.get_timeout("ha_check_config")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.config_dir),
            )

            # Parse the output
            self.parse_check_config_output(result.stdout, result.stderr)

            # Return success if exit code is 0
            return result.returncode == 0

        except subprocess.TimeoutExpired:
            self.errors.append("Home Assistant configuration check timed out")
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
                        self.errors.append(f"HA Check: {line}")
                elif "ERROR" in line or "Error" in line:
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
            # Get ignore patterns from config
            ignore_patterns = self.validation_config.stderr_ignore_patterns

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Filter out messages matching ignore patterns from config
                if any(pattern.lower() in line.lower() for pattern in ignore_patterns):
                    continue

                # This is likely an actual error
                self.errors.append(f"HA Error: {line}")

    def reclassify_environment_errors(self) -> None:
        """Reclassify environment-specific errors as warnings.

        Some errors occur only in the test environment (missing native libs,
        mobile app integration, etc.) but don't indicate actual config problems.
        This method moves those errors to warnings for clearer output.
        """
        env_patterns = self.validation_config.environment_patterns

        if not env_patterns:
            return

        errors_to_remove = []
        for error in self.errors:
            for pattern in env_patterns:
                if pattern.lower() in error.lower():
                    errors_to_remove.append(error)
                    self.warnings.append(f"[Env] {error}")
                    logger.debug(f"Reclassified as env warning: {error}")
                    break

        for error in errors_to_remove:
            self.errors.remove(error)

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

        # Check HA version compatibility
        self.check_version_compatibility()

        # Run the official Home Assistant validation
        result = self.run_ha_check_config()

        # Reclassify environment-specific errors as warnings
        self.reclassify_environment_errors()

        # Return success if no real errors remain
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
