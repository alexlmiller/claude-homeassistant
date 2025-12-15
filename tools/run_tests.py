#!/usr/bin/env python3
"""Test suite runner for Home Assistant configuration validation.

Runs all validators and provides a comprehensive report.
Supports parallel execution for faster validation.
"""

import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple


class ValidationTestRunner:
    """Runs all validation tests and reports results."""

    def __init__(self, config_dir: str = "config"):
        """Initialize the test runner."""
        self.config_dir = Path(config_dir).resolve()
        self.tools_dir = Path(__file__).parent
        self.venv_dir = self.tools_dir.parent / "venv"
        self.results: Dict[str, Dict[str, Any]] = {}

    def get_python_executable(self) -> str:
        """Get the Python executable from venv if available."""
        venv_python = self.venv_dir / "bin" / "python"
        if venv_python.exists():
            return str(venv_python)
        return sys.executable

    def run_validator(
        self, script_name: str, description: str
    ) -> Tuple[bool, str, str, float]:
        """Run a single validator script."""
        script_path = self.tools_dir / script_name
        if not script_path.exists():
            return False, "", f"Script {script_name} not found", 0.0

        python_exe = self.get_python_executable()
        cmd = [python_exe, str(script_path), str(self.config_dir)]

        start_time = time.time()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            end_time = time.time()
            duration = end_time - start_time

            return (
                result.returncode == 0,
                result.stdout,
                result.stderr,
                duration,
            )

        except subprocess.TimeoutExpired:
            end_time = time.time()
            duration = end_time - start_time
            return (
                False,
                "",
                "Validator timed out after 120 seconds",
                duration,
            )

        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            return (False, "", f"Failed to run validator: {e}", duration)

    def run_validators_parallel(
        self, validators: List[Tuple[str, str]]
    ) -> Dict[str, Dict[str, Any]]:
        """Run multiple validators in parallel using ThreadPoolExecutor.

        Args:
            validators: List of (script_name, description) tuples

        Returns:
            Dictionary of results keyed by script_name
        """
        results = {}

        with ThreadPoolExecutor(max_workers=len(validators)) as executor:
            # Submit all validators
            future_to_validator = {
                executor.submit(
                    self.run_validator, script_name, description
                ): (script_name, description)
                for script_name, description in validators
            }

            # Collect results as they complete
            for future in as_completed(future_to_validator):
                script_name, description = future_to_validator[future]
                try:
                    passed, stdout, stderr, duration = future.result()
                    results[script_name] = {
                        "description": description,
                        "passed": passed,
                        "stdout": stdout,
                        "stderr": stderr,
                        "duration": duration,
                    }
                except Exception as e:
                    results[script_name] = {
                        "description": description,
                        "passed": False,
                        "stdout": "",
                        "stderr": f"Exception during validation: {e}",
                        "duration": 0.0,
                    }

        return results

    def run_all_tests(self, parallel: bool = True) -> bool:
        """Run all validation tests.

        Args:
            parallel: If True, run independent validators in parallel

        Returns:
            True if all tests passed, False otherwise
        """
        # First phase: YAML syntax validation (must pass before others)
        yaml_validator = ("yaml_validator.py", "YAML Syntax Validation")

        # Second phase: these can run in parallel
        parallel_validators = [
            ("reference_validator.py", "Entity/Device Reference Validation"),
            (
                "ha_official_validator.py",
                "Official Home Assistant Configuration Validation",
            ),
        ]

        all_passed = True
        total_duration = 0.0

        print("🔍 Running Home Assistant Configuration Validation Tests")
        print("=" * 60)
        print()

        # Phase 1: Run YAML validator first (quick sanity check)
        print(f"Phase 1: {yaml_validator[1]}...")
        passed, stdout, stderr, duration = self.run_validator(*yaml_validator)
        total_duration += duration

        self.results[yaml_validator[0]] = {
            "description": yaml_validator[1],
            "passed": passed,
            "stdout": stdout,
            "stderr": stderr,
            "duration": duration,
        }

        if passed:
            print(f"  ✅ PASSED ({duration:.2f}s)")
        else:
            print(f"  ❌ FAILED ({duration:.2f}s)")
            all_passed = False

        print()

        # Phase 2: Run remaining validators (parallel if enabled)
        if parallel and len(parallel_validators) > 1:
            print(f"Phase 2: Running {len(parallel_validators)} validators in parallel...")
            start_time = time.time()

            parallel_results = self.run_validators_parallel(parallel_validators)

            parallel_duration = time.time() - start_time
            total_duration += parallel_duration

            # Process results
            for script_name, result in parallel_results.items():
                self.results[script_name] = result
                if result["passed"]:
                    print(f"  ✅ {result['description']} ({result['duration']:.2f}s)")
                else:
                    print(f"  ❌ {result['description']} ({result['duration']:.2f}s)")
                    all_passed = False

            print(f"  (Parallel phase completed in {parallel_duration:.2f}s)")
        else:
            # Sequential execution
            for script_name, description in parallel_validators:
                print(f"Running {description}...")

                passed, stdout, stderr, duration = self.run_validator(
                    script_name, description
                )
                total_duration += duration

                self.results[script_name] = {
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
                    all_passed = False

                print()

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
        """Check if all required dependencies are available."""
        python_exe = self.get_python_executable()

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
                    missing_modules.append(module)
            except Exception:
                missing_modules.append(module)

        if missing_modules:
            modules_str = ", ".join(missing_modules)
            print(f"❌ Missing required Python modules: {modules_str}")
            print("Please install them with:")
            modules_to_install = " ".join(missing_modules)
            print(f"  {python_exe} -m pip install {modules_to_install}")
            return False

        return True

    def run(self, parallel: bool = True) -> bool:
        """Run the complete test suite.

        Args:
            parallel: If True, run independent validators in parallel

        Returns:
            True if all tests passed, False otherwise
        """
        if not self.config_dir.exists():
            print(f"❌ Config directory not found: {self.config_dir}")
            return False

        if not self.check_dependencies():
            return False

        all_passed = self.run_all_tests(parallel=parallel)

        self.print_detailed_results()
        self.print_summary()

        return all_passed


def main():
    """Run main function for command line usage.

    Usage: run_tests.py [config_dir] [--sequential]

    Options:
        config_dir: Path to the config directory (default: config)
        --sequential: Run validators sequentially instead of in parallel
    """
    # Parse arguments
    args = sys.argv[1:]
    parallel = True
    config_dir = "config"

    for arg in args:
        if arg == "--sequential":
            parallel = False
        elif not arg.startswith("-"):
            config_dir = arg

    runner = ValidationTestRunner(config_dir)
    success = runner.run(parallel=parallel)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
