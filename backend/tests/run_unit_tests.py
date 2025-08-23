#!/usr/bin/env python
"""
Lightweight Unit Test Runner for Agent System

Rapid-execution test runner designed for post-change validation.
Focuses on catching glaring errors (missing awaits, import failures, basic functionality breaks).

Usage:
    # Run all unit tests
    python run_unit_tests.py
    
    # Run specific test suite
    python run_unit_tests.py --suite async_validation
    
    # Run with verbose output
    python run_unit_tests.py --verbose
    
    # Run in Docker environment
    docker-compose exec backend uv run python tests/run_unit_tests.py
"""

import argparse
import subprocess
import sys
import time
import os
from pathlib import Path
from typing import List, Dict, Optional


class TestRunner:
    """Lightweight test runner with performance tracking."""
    
    def __init__(self):
        self.test_dir = Path(__file__).parent / "unit"
        self.test_suites = {
            "async_validation": "test_async_validation.py",
            "import_structure": "test_import_structure.py", 
            "database_operations": "test_database_operations.py",
            "router_agent": "test_router_agent.py",
            "task_execution": "test_task_execution.py",
            "file_manager": "test_file_manager.py",
            "websocket_communication": "test_websocket_communication.py",
            "api_endpoints": "test_api_endpoints.py",
            "file_processing": "test_file_processing.py",
            "llm_service": "test_llm_service.py"
        }
        
        # Performance targets (from test plan)
        self.performance_targets = {
            "total_time": 30.0,  # seconds
            "individual_test": 5.0,  # seconds per test file
            "database_tests": 3.0,  # seconds for database test files
            "import_tests": 1.0  # seconds for import tests
        }

    def run_test_suite(self, suite_name: str, verbose: bool = False) -> Dict[str, any]:
        """Run a specific test suite and return results."""
        if suite_name not in self.test_suites:
            raise ValueError(f"Unknown test suite: {suite_name}")
        
        test_file = self.test_suites[suite_name]
        test_path = self.test_dir / test_file
        
        if not test_path.exists():
            return {
                "suite": suite_name,
                "success": False,
                "error": f"Test file not found: {test_path}",
                "duration": 0.0,
                "output": ""
            }
        
        print(f"🧪 Running {suite_name}...")
        start_time = time.time()
        
        # Build pytest command
        cmd = [
            sys.executable, "-m", "pytest",
            str(test_path),
            "--tb=short",  # Short traceback
            "--no-header",  # No pytest header
            "-q" if not verbose else "-v",  # Quiet or verbose
            "--disable-warnings"  # Suppress warnings for speed
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.performance_targets["individual_test"] * 2  # 2x safety margin
            )
            
            duration = time.time() - start_time
            
            # Check performance target
            target_time = self._get_performance_target(suite_name)
            performance_ok = duration <= target_time
            
            if not performance_ok:
                print(f"⚠️  Performance warning: {suite_name} took {duration:.2f}s (target: {target_time:.1f}s)")
            
            return {
                "suite": suite_name,
                "success": result.returncode == 0,
                "duration": duration,
                "performance_ok": performance_ok,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None
            }
            
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return {
                "suite": suite_name,
                "success": False,
                "duration": duration,
                "performance_ok": False,
                "output": "",
                "error": f"Test suite timed out after {duration:.1f}s"
            }
        except Exception as e:
            duration = time.time() - start_time
            return {
                "suite": suite_name,
                "success": False,
                "duration": duration,
                "performance_ok": False,
                "output": "",
                "error": f"Failed to run test suite: {str(e)}"
            }

    def _get_performance_target(self, suite_name: str) -> float:
        """Get performance target for specific test suite."""
        if suite_name == "import_structure":
            return self.performance_targets["import_tests"]
        elif suite_name == "database_operations":
            return self.performance_targets["database_tests"]
        else:
            return self.performance_targets["individual_test"]

    def run_all_tests(self, verbose: bool = False, fail_fast: bool = False) -> List[Dict[str, any]]:
        """Run all test suites and return results."""
        print("🚀 Starting Agent System Unit Tests")
        print(f"📁 Test directory: {self.test_dir}")
        print(f"🎯 Performance target: <{self.performance_targets['total_time']}s total")
        print("=" * 60)
        
        start_time = time.time()
        results = []
        
        # Prioritise fast tests first for rapid feedback
        ordered_suites = [
            "import_structure",  # Fastest - import validation
            "async_validation",  # Critical - catch await errors
            "database_operations",  # Core functionality
            "file_manager",  # File operations
            "router_agent",  # Main component
            "task_execution",  # Task pipeline
            # Add other suites as they're created
        ]
        
        # Add any remaining suites not in ordered list
        for suite_name in self.test_suites:
            if suite_name not in ordered_suites:
                ordered_suites.append(suite_name)
        
        for suite_name in ordered_suites:
            if suite_name not in self.test_suites:
                continue  # Skip if test file doesn't exist yet
                
            result = self.run_test_suite(suite_name, verbose)
            results.append(result)
            
            if result["success"]:
                status = "✅"
                if not result["performance_ok"]:
                    status = "🐌"  # Slow but passing
                print(f"{status} {suite_name} ({result['duration']:.2f}s)")
            else:
                print(f"❌ {suite_name} ({result['duration']:.2f}s)")
                if verbose and result["error"]:
                    print(f"   Error: {result['error']}")
                
                if fail_fast:
                    print("💥 Stopping on first failure (fail-fast mode)")
                    break
        
        total_duration = time.time() - start_time
        
        print("=" * 60)
        self._print_summary(results, total_duration)
        
        return results

    def _print_summary(self, results: List[Dict[str, any]], total_duration: float):
        """Print test summary with performance analysis."""
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r["success"])
        failed_tests = total_tests - passed_tests
        
        # Performance analysis
        target_met = total_duration <= self.performance_targets["total_time"]
        avg_test_time = total_duration / total_tests if total_tests > 0 else 0
        
        print(f"📊 Test Results Summary")
        print(f"   Total: {total_tests} | Passed: {passed_tests} | Failed: {failed_tests}")
        print(f"   Execution time: {total_duration:.2f}s (target: <{self.performance_targets['total_time']}s)")
        print(f"   Average per test: {avg_test_time:.2f}s")
        
        if target_met:
            print("🎯 Performance target met!")
        else:
            print(f"⚠️  Performance target missed by {total_duration - self.performance_targets['total_time']:.1f}s")
        
        if failed_tests == 0:
            print("🎉 All tests passed!")
        else:
            print(f"💥 {failed_tests} test suite(s) failed:")
            for result in results:
                if not result["success"]:
                    print(f"   ❌ {result['suite']}: {result['error'] or 'Unknown error'}")
        
        # Show slowest tests
        slow_tests = [r for r in results if not r.get("performance_ok", True)]
        if slow_tests:
            print(f"🐌 Slow tests (above target):")
            for result in slow_tests:
                target = self._get_performance_target(result["suite"])
                print(f"   {result['suite']}: {result['duration']:.2f}s (target: {target:.1f}s)")

    def check_docker_environment(self) -> bool:
        """Check if running in Docker environment."""
        return os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER") == "true"

    def suggest_docker_command(self):
        """Suggest Docker command if not running in Docker."""
        print("💡 To run tests in Docker environment:")
        print("   docker-compose exec backend uv run python tests/run_unit_tests.py")


def main():
    """Main entry point for test runner."""
    parser = argparse.ArgumentParser(
        description="Agent System Unit Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_unit_tests.py                    # Run all tests
  python run_unit_tests.py --suite async_validation  # Run specific suite
  python run_unit_tests.py --verbose          # Verbose output
  python run_unit_tests.py --fail-fast        # Stop on first failure
        """
    )
    
    parser.add_argument(
        "--suite", 
        help="Run specific test suite",
        choices=["async_validation", "import_structure", "database_operations", 
                "router_agent", "task_execution", "file_manager"]
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose test output"
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true", 
        help="Stop on first test failure"
    )
    parser.add_argument(
        "--docker-suggest",
        action="store_true",
        help="Show Docker command suggestion"
    )
    
    args = parser.parse_args()
    
    runner = TestRunner()
    
    # Show Docker suggestion if requested
    if args.docker_suggest:
        runner.suggest_docker_command()
        return 0
    
    try:
        if args.suite:
            # Run specific test suite
            result = runner.run_test_suite(args.suite, args.verbose)
            
            print("=" * 60)
            if result["success"]:
                print(f"✅ {args.suite} passed ({result['duration']:.2f}s)")
                return 0
            else:
                print(f"❌ {args.suite} failed ({result['duration']:.2f}s)")
                if result["error"]:
                    print(f"Error: {result['error']}")
                if result["output"]:
                    print("Output:")
                    print(result["output"])
                return 1
        else:
            # Run all test suites
            results = runner.run_all_tests(args.verbose, args.fail_fast)
            
            # Return exit code based on results
            failed_tests = sum(1 for r in results if not r["success"])
            return min(failed_tests, 1)  # Return 1 if any failures, 0 if all passed
            
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
        return 130
    except Exception as e:
        print(f"💥 Test runner error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())