#!/usr/bin/env python
"""
Integration Test Runner for Agent System

Comprehensive integration test runner for performance, concurrency, and end-to-end validation.
These tests complement the lightweight unit tests with thorough scenario coverage.

Usage:
    # Run all integration tests
    python run_integration_tests.py
    
    # Run specific integration test
    python run_integration_tests.py --suite background_processor_efficiency
    
    # Run with verbose output
    python run_integration_tests.py --verbose
    
    # Run in Docker environment
    docker-compose exec backend uv run python tests/run_integration_tests.py
"""

import argparse
import subprocess
import sys
import time
import os
from pathlib import Path
from typing import List, Dict, Optional


class IntegrationTestRunner:
    """Integration test runner with performance analysis."""
    
    def __init__(self):
        self.test_dir = Path(__file__).parent / "integration"
        self.integration_suites = {
            "background_processor_efficiency": "test_background_processor_efficiency.py",
            "concurrent_planner_execution": "test_concurrent_planner_execution.py", 
            "multiple_conversations_concurrent": "test_multiple_conversations_concurrent.py",
            "fastapi_immediate_response": "test_fastapi_immediate_response.py",
            "file_storage": "test_file_storage.py",
            "websocket_updates_execution": "test_websocket_updates_execution.py"
        }
        
        # Performance tracking (no strict limits for integration tests)
        self.performance_data = {}

    def run_integration_suite(self, suite_name: str, verbose: bool = False) -> Dict[str, any]:
        """Run a specific integration test suite and return results."""
        if suite_name not in self.integration_suites:
            raise ValueError(f"Unknown integration test suite: {suite_name}")
        
        test_file = self.integration_suites[suite_name]
        test_path = self.test_dir / test_file
        
        if not test_path.exists():
            return {
                "suite": suite_name,
                "success": False,
                "error": f"Integration test file not found: {test_path}",
                "duration": 0.0,
                "output": ""
            }
        
        print(f"🧪 Running integration test: {suite_name}...")
        start_time = time.time()
        
        # Build pytest command for integration tests
        cmd = [
            sys.executable, "-m", "pytest",
            str(test_path),
            "--tb=long",  # Detailed traceback for integration tests
            "-v" if verbose else "-q",
            "--disable-warnings",
            "--durations=10"  # Show 10 slowest tests
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout for integration tests
            )
            
            duration = time.time() - start_time
            
            return {
                "suite": suite_name,
                "success": result.returncode == 0,
                "duration": duration,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
                "performance_notes": self._analyze_performance(suite_name, duration)
            }
            
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return {
                "suite": suite_name,
                "success": False,
                "duration": duration,
                "output": "",
                "error": f"Integration test suite timed out after {duration:.1f}s",
                "performance_notes": f"Test exceeded 5 minute limit"
            }
        except Exception as e:
            duration = time.time() - start_time
            return {
                "suite": suite_name,
                "success": False,
                "duration": duration,
                "output": "",
                "error": f"Failed to run integration test suite: {str(e)}",
                "performance_notes": ""
            }

    def _analyze_performance(self, suite_name: str, duration: float) -> str:
        """Analyze performance characteristics of integration test."""
        if suite_name == "background_processor_efficiency":
            if duration > 60:
                return f"Performance test took {duration:.1f}s - may indicate system performance issues"
            elif duration < 10:
                return f"Performance test completed quickly ({duration:.1f}s) - good system performance"
            else:
                return f"Performance test completed in {duration:.1f}s - normal range"
        
        elif suite_name == "concurrent_planner_execution":
            if duration > 45:
                return f"Concurrency test took {duration:.1f}s - may indicate resource contention"
            else:
                return f"Concurrency test completed in {duration:.1f}s"
        
        elif suite_name == "multiple_conversations_concurrent":
            if duration > 30:
                return f"Multi-conversation test took {duration:.1f}s - check router isolation efficiency"
            else:
                return f"Multi-conversation test completed in {duration:.1f}s"
        
        else:
            return f"Completed in {duration:.1f}s"

    def run_all_integration_tests(self, verbose: bool = False, fail_fast: bool = False) -> List[Dict[str, any]]:
        """Run all integration test suites and return results."""
        print("🚀 Starting Agent System Integration Tests")
        print(f"📁 Integration test directory: {self.test_dir}")
        print("🎯 Purpose: Comprehensive validation of performance, concurrency, and end-to-end scenarios")
        print("=" * 70)
        
        start_time = time.time()
        results = []
        
        # Order tests by expected execution time (fastest first for early feedback)
        ordered_suites = [
            "fastapi_immediate_response",        # ~10-30s
            "file_storage",                      # ~15-35s  
            "websocket_updates_execution",       # ~20-40s
            "multiple_conversations_concurrent", # ~20-40s
            "concurrent_planner_execution",      # ~30-60s
            "background_processor_efficiency"    # ~45-120s
        ]
        
        for suite_name in ordered_suites:
            if suite_name not in self.integration_suites:
                continue  # Skip if test file doesn't exist
                
            result = self.run_integration_suite(suite_name, verbose)
            results.append(result)
            
            if result["success"]:
                status = "✅"
                print(f"{status} {suite_name} ({result['duration']:.1f}s)")
                if result["performance_notes"]:
                    print(f"   📊 {result['performance_notes']}")
            else:
                print(f"❌ {suite_name} ({result['duration']:.1f}s)")
                if verbose and result["error"]:
                    print(f"   Error: {result['error']}")
                
                if fail_fast:
                    print("💥 Stopping on first failure (fail-fast mode)")
                    break
        
        total_duration = time.time() - start_time
        
        print("=" * 70)
        self._print_integration_summary(results, total_duration)
        
        return results

    def _print_integration_summary(self, results: List[Dict[str, any]], total_duration: float):
        """Print integration test summary with performance analysis."""
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"📊 Integration Test Results Summary")
        print(f"   Total: {total_tests} | Passed: {passed_tests} | Failed: {failed_tests}")
        print(f"   Total execution time: {total_duration:.1f}s")
        
        if total_tests > 0:
            avg_test_time = total_duration / total_tests
            print(f"   Average per test: {avg_test_time:.1f}s")
        
        if failed_tests == 0:
            print("🎉 All integration tests passed!")
            print("✅ System performance, concurrency, and end-to-end scenarios validated")
        else:
            print(f"💥 {failed_tests} integration test(s) failed:")
            for result in results:
                if not result["success"]:
                    print(f"   ❌ {result['suite']}: {result['error'] or 'Unknown error'}")
        
        # Performance insights
        longest_test = max(results, key=lambda r: r["duration"]) if results else None
        if longest_test:
            print(f"🐌 Longest test: {longest_test['suite']} ({longest_test['duration']:.1f}s)")
        
        # System performance indicators
        total_test_time = sum(r["duration"] for r in results)
        if total_test_time > 0:
            efficiency_ratio = total_duration / total_test_time
            if efficiency_ratio > 1.2:
                print(f"⚠️  Test overhead detected: {efficiency_ratio:.1f}x ratio suggests system resource constraints")

    def check_integration_prerequisites(self) -> bool:
        """Check if system meets integration test prerequisites."""
        print("🔍 Checking integration test prerequisites...")
        
        # Check Docker environment
        if not (os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER")):
            print("⚠️  Integration tests recommended to run in Docker environment")
            print("   Run: docker-compose exec backend uv run python tests/run_integration_tests.py")
            return False
        
        # Check test directory exists
        if not self.test_dir.exists():
            print(f"❌ Integration test directory not found: {self.test_dir}")
            return False
        
        # Check test files exist
        missing_files = []
        for suite_name, test_file in self.integration_suites.items():
            test_path = self.test_dir / test_file
            if not test_path.exists():
                missing_files.append(test_file)
        
        if missing_files:
            print(f"⚠️  Missing integration test files: {', '.join(missing_files)}")
            return False
        
        print("✅ Prerequisites check passed")
        return True

    def get_performance_baseline(self) -> Dict[str, float]:
        """Get expected performance baseline for comparison."""
        return {
            "fastapi_immediate_response": 15.0,      # Should be quick
            "file_storage": 25.0,                    # File operations
            "websocket_updates_execution": 30.0,     # Real-time communication
            "multiple_conversations_concurrent": 35.0, # Moderate complexity  
            "concurrent_planner_execution": 50.0,    # High complexity
            "background_processor_efficiency": 90.0   # Most comprehensive
        }


def main():
    """Main entry point for integration test runner."""
    parser = argparse.ArgumentParser(
        description="Agent System Integration Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_integration_tests.py                          # Run all integration tests
  python run_integration_tests.py --suite background_processor_efficiency  # Run specific suite
  python run_integration_tests.py --verbose               # Verbose output
  python run_integration_tests.py --fail-fast             # Stop on first failure
        """
    )
    
    parser.add_argument(
        "--suite",
        help="Run specific integration test suite",
        choices=["background_processor_efficiency", "concurrent_planner_execution", 
                "multiple_conversations_concurrent", "fastapi_immediate_response",
                "file_storage", "websocket_updates_execution"]
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
        "--check-prereqs",
        action="store_true",
        help="Check integration test prerequisites"
    )
    
    args = parser.parse_args()
    
    runner = IntegrationTestRunner()
    
    # Check prerequisites if requested
    if args.check_prereqs:
        if runner.check_integration_prerequisites():
            print("✅ Ready to run integration tests")
            return 0
        else:
            print("❌ Prerequisites not met")
            return 1
    
    try:
        if args.suite:
            # Run specific integration test suite
            result = runner.run_integration_suite(args.suite, args.verbose)
            
            print("=" * 70)
            if result["success"]:
                print(f"✅ {args.suite} passed ({result['duration']:.1f}s)")
                if result["performance_notes"]:
                    print(f"📊 {result['performance_notes']}")
                return 0
            else:
                print(f"❌ {args.suite} failed ({result['duration']:.1f}s)")
                if result["error"]:
                    print(f"Error: {result['error']}")
                if result["output"]:
                    print("Output:")
                    print(result["output"])
                return 1
        else:
            # Check prerequisites first
            if not runner.check_integration_prerequisites():
                return 1
                
            # Run all integration test suites
            results = runner.run_all_integration_tests(args.verbose, args.fail_fast)
            
            # Return exit code based on results
            failed_tests = sum(1 for r in results if not r["success"])
            return min(failed_tests, 1)  # Return 1 if any failures, 0 if all passed
            
    except KeyboardInterrupt:
        print("\n🛑 Integration tests interrupted by user")
        return 130
    except Exception as e:
        print(f"💥 Integration test runner error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())