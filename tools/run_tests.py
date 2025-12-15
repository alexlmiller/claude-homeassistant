#!/usr/bin/env python3
"""Test suite runner for Home Assistant configuration validation.

Runs all validators and provides a comprehensive report.
"""

import argparse
import logging
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Import shared modules
from validation_config_loader import ValidationConfig

# Configure module logger
logger = logging.getLogger(__name__)


class ValidationTestRunner:
    """Runs all validation tests and reports results."""

    def __init__(self, config_dir: str = "config", parallel: bool = False):
        """Initialize the test runner.

        Args:
            config_dir: Path to Home Assistant config directory
            parallel: If True, run validators in parallel
        """
        self.config_dir = Path(config_dir).resolve()
        self.tools_dir = Path(__file__).parent
        self.venv_dir = self.tools_dir.parent / "venv"
        self.results: Dict[str, Dict[str, Any]] = {}
        self.parallel = parallel
        self.validation_config = ValidationConfig.get_instance()

    def get_python_executable(self) -> str:
        """Get the Python executable from venv if available."""
        venv_python = self.venv_dir / "bin" / "python"
        if venv_python.exists():
            return str(venv_python)
        return sys.executable

    def run_validator(
        self, script_name: str, description: str
    ) -> Tuple[bool, str, str, float]:
        """Run a single validator script.

        Args:
            script_name: Name of the validator script
            description: Human-readable description of the validator

        Returns:
            Tuple of (passed, stdout, stderr, duration)
        """
        script_path = self.tools_dir / script_name
        if not script_path.exists():
            logger.error(f"Validator script not found: {script_path}")
            return False, "", f"Script {script_name} not found", 0.0

        python_exe = self.get_python_executable()
        cmd = [python_exe, str(script_path), str(self.config_dir)]

        # Get timeout from config (default 120s for yaml validation)
        timeout = self.validation_config.get_timeout("yaml_validation")
        logger.debug(f"Running {script_name} with timeout {timeout}s")

        start_time = time.time()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            end_time = time.time()
            duration = end_time - start_time

            logger.debug(f"{script_name} completed in {duration:.2f}s")
            return (
                result.returncode == 0,
                result.stdout,
                result.stderr,
                duration,
            )

        except subprocess.TimeoutExpired:
            end_time = time.time()
            duration = end_time - start_time
            logger.warning(f"{script_name} timed out after {timeout}s")
            return (
                False,
                "",
                f"Validator timed out after {timeout} seconds",
                duration,
            )

        except FileNotFoundError as e:
            end_time = time.time()
            duration = end_time - start_time
            logger.error(f"Python executable not found: {e}")
            return (False, "", f"Python executable not found: {e}", duration)

        except PermissionError as e:
            end_time = time.time()
            duration = end_time - start_time
            logger.error(f"Permission denied running {script_name}: {e}")
            return (False, "", f"Permission denied: {e}", duration)

        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            logger.exception(f"Unexpected error running {script_name}")
            return (False, "", f"Failed to run validator: {e}", duration)

    def run_validators_parallel(
        self, validators: List[Tuple[str, str]], timeout: int = 300
    ) -> Dict[str, Dict[str, Any]]:
        """Run validators in parallel with timeout handling.

        Args:
            validators: List of (script_name, description) tuples
            timeout: Maximum time to wait for all validators (seconds)

        Returns:
            Dict mapping script names to result dictionaries
        """
        results: Dict[str, Dict[str, Any]] = {}
        logger.info(f"Running {len(validators)} validators in parallel")

        with ThreadPoolExecutor(max_workers=len(validators)) as executor:
            future_to_validator = {
                executor.submit(self.run_validator, script_name, description): (
                    script_name,
                    description,
                )
                for script_name, description in validators
            }

            try:
                for future in as_completed(future_to_validator, timeout=timeout):
                    script_name, description = future_to_validator[future]
                    try:
                        passed, stdout, stderr, duration = future.result(timeout=10)
                        results[script_name] = {
                            "description": description,
                            "passed": passed,
                            "stdout": stdout,
                            "stderr": stderr,
                            "duration": duration,
                        }
                        logger.debug(
                            f"{script_name}: {'PASSED' if passed else 'FAILED'}"
                        )
                    except Exception as e:
                        logger.exception(f"Exception getting result for {script_name}")
                        results[script_name] = {
                            "description": description,
                            "passed": False,
                            "stdout": "",
                            "stderr": f"Exception during validation: {e}",
                            "duration": 0.0,
                        }

            except FuturesTimeoutError:
                logger.error(f"Parallel validation timed out after {timeout}s")
                # Handle validators that didn't complete in time
                for future, (script_name, description) in future_to_validator.items():
                    if script_name not in results:
                        future.cancel()
                        logger.warning(f"Cancelling timed out validator: {script_name}")
                        results[script_name] = {
                            "description": description,
                            "passed": False,
                            "stdout": "",
                            "stderr": f"Validator timed out after {timeout}s",
                            "duration": float(timeout),
                        }

        return results

    def run_validators_sequential(
        self, validators: List[Tuple[str, str]]
    ) -> Dict[str, Dict[str, Any]]:
        """Run validators sequentially.

        Args:
            validators: List of (script_name, description) tuples

        Returns:
            Dict mapping script names to result dictionaries
        """
        results: Dict[str, Dict[str, Any]] = {}
        logger.info(f"Running {len(validators)} validators sequentially")

        for script_name, description in validators:
            print(f"Running {description}...")

            passed, stdout, stderr, duration = self.run_validator(
                script_name, description
            )

            results[script_name] = {
                "description": description,
                "passed": passed,
                "stdout": stdout,
                "stderr": stderr,
                "duration": duration,
            }

            if passed:
                print(f"  ✅ PASSED ({duration:.2f}s)")
            else:
                print(f"  ❌ FAILED ({duration:.2f}s)")

            print()

        return results

    def run_all_tests(self) -> bool:
        """Run all validation tests."""
        validators: List[Tuple[str, str]] = [
            ("yaml_validator.py", "YAML Syntax Validation"),
            ("reference_validator.py", "Entity/Device Reference Validation"),
            (
                "ha_official_validator.py",
                "Official Home Assistant Configuration Validation",
            ),
        ]

        print("🔍 Running Home Assistant Configuration Validation Tests")
        print("=" * 60)
        if self.parallel:
            print("Mode: Parallel execution")
        else:
            print("Mode: Sequential execution")
        print()

        start_time = time.time()

        if self.parallel:
            # Get overall timeout from config (default to sum of individual timeouts)
            overall_timeout = self.validation_config.get_timeout("reference_validation")
            overall_timeout += self.validation_config.get_timeout("yaml_validation")
            overall_timeout += self.validation_config.get_timeout("ha_check_config")
            self.results = self.run_validators_parallel(validators, overall_timeout)

            # Print results after parallel execution
            for script_name, description in validators:
                if script_name in self.results:
                    result = self.results[script_name]
                    status = "✅ PASSED" if result["passed"] else "❌ FAILED"
                    print(f"{description}: {status} ({result['duration']:.2f}s)")
        else:
            self.results = self.run_validators_sequential(validators)

        total_duration = time.time() - start_time
        all_passed = all(r["passed"] for r in self.results.values())

        print()
        print(f"Total execution time: {total_duration:.2f}s")
        print("=" * 60)

        return all_passed

    def print_detailed_results(self):
        """Print detailed results for each validator."""
        for _script_name, result in self.results.items():
            print(f"\n📋 {result['description']}")
            print("-" * 50)

            if result["passed"]:
                print("Status: ✅ PASSED")
            else:
                print("Status: ❌ FAILED")

            print(f"Duration: {result['duration']:.2f}s")

            if result["stdout"].strip():
                print("\nOutput:")
                for line in result["stdout"].strip().split("\n"):
                    print(f"  {line}")

            if result["stderr"].strip():
                print("\nErrors:")
                for line in result["stderr"].strip().split("\n"):
                    print(f"  {line}")

            print()

    def print_summary(self):
        """Print test summary."""
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results.values() if r["passed"])
        failed_tests = total_tests - passed_tests

        print("\n📊 TEST SUMMARY")
        print("=" * 30)
        print(f"Total tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")

        if failed_tests == 0:
            print("\n🎉 All tests passed! Your Home Assistant configuration is valid.")
        else:
            print(
                f"\n⚠️  {failed_tests} test(s) failed. "
                "Please review the errors above."
            )

        print()

    def check_dependencies(self) -> bool:
        """Check if all required dependencies are available.

        Returns:
            True if all dependencies are available, False otherwise
        """
        python_exe = self.get_python_executable()
        logger.debug(f"Checking dependencies using Python: {python_exe}")

        required_modules = ["yaml", "voluptuous", "jsonschema"]
        missing_modules = []

        for module in required_modules:
            try:
                result = subprocess.run(
                    [python_exe, "-c", f"import {module}"],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    logger.warning(f"Module {module} import failed")
                    missing_modules.append(module)
                else:
                    logger.debug(f"Module {module} is available")
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout checking module {module}")
                missing_modules.append(module)
            except FileNotFoundError:
                logger.error(f"Python executable not found: {python_exe}")
                missing_modules.append(module)
            except Exception as e:
                logger.warning(f"Error checking module {module}: {e}")
                missing_modules.append(module)

        if missing_modules:
            modules_str = ", ".join(missing_modules)
            logger.error(f"Missing required modules: {modules_str}")
            print(f"❌ Missing required Python modules: {modules_str}")
            print("Please install them with:")
            modules_to_install = " ".join(missing_modules)
            print(f"  {python_exe} -m pip install {modules_to_install}")
            return False

        logger.debug("All required dependencies are available")
        return True

    def run(self) -> bool:
        """Run the complete test suite.

        Returns:
            True if all tests passed, False otherwise
        """
        logger.info(f"Starting validation for config directory: {self.config_dir}")

        if not self.config_dir.exists():
            logger.error(f"Config directory not found: {self.config_dir}")
            print(f"❌ Config directory not found: {self.config_dir}")
            return False

        if not self.check_dependencies():
            return False

        all_passed = self.run_all_tests()

        self.print_detailed_results()
        self.print_summary()

        logger.info(f"Validation complete: {'PASSED' if all_passed else 'FAILED'}")
        return all_passed


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
    logger.debug("Verbose logging enabled")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Run Home Assistant configuration validation tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    Run validators sequentially
  %(prog)s --parallel         Run validators in parallel
  %(prog)s --verbose          Show debug output
  %(prog)s config/ --parallel Run parallel validation on config/
        """,
    )
    parser.add_argument(
        "config_dir",
        nargs="?",
        default="config",
        help="Path to Home Assistant config directory (default: config)",
    )
    parser.add_argument(
        "-p",
        "--parallel",
        action="store_true",
        help="Run validators in parallel for faster execution",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug output",
    )

    return parser.parse_args()


def main():
    """Run main function for command line usage."""
    args = parse_args()

    setup_logging(args.verbose)

    runner = ValidationTestRunner(args.config_dir, parallel=args.parallel)
    success = runner.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
