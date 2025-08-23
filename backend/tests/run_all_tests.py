#!/usr/bin/env python
"""
Combined Test Runner for Agent System

Orchestrates both unit and integration tests with intelligent execution order.
Runs fast unit tests first for immediate feedback, then comprehensive integration tests.

Usage:
    # Run all tests (unit first, then integration)
    python run_all_tests.py
    
    # Run only unit tests
    python run_all_tests.py --unit-only
    
    # Run only integration tests  
    python run_all_tests.py --integration-only
    
    # Verbose output
    python run_all_tests.py --verbose
    
    # Fail fast on first error
    python run_all_tests.py --fail-fast
    
    # Docker environment
    docker-compose exec backend uv run python tests/run_all_tests.py
"""

import argparse
import subprocess
import sys
import time
import os
from pathlib import Path
from typing import Dict, List, Optional

# Import our test runners
from run_unit_tests import UnitTestRunner
from run_integration_tests import IntegrationTestRunner


class CombinedTestRunner:
    """Combined test runner orchestrating unit and integration tests."""
    
    def __init__(self):
        self.unit_runner = UnitTestRunner()
        self.integration_runner = IntegrationTestRunner()
        
        self.execution_summary = {
            "unit_tests": {"executed": False, "results": None},
            "integration_tests": {"executed": False, "results": None},
            "total_duration": 0.0,
            "overall_success": False
        }
    
    def run_unit_tests_only(self, verbose: bool = False, fail_fast: bool = False) -> Dict:
        """Run only unit tests."""
        print("🏃‍♂️ Running Unit Tests Only")
        print("=" * 50)
        
        start_time = time.time()
        unit_results = self.unit_runner.run_all_unit_tests(verbose, fail_fast)
        duration = time.time() - start_time
        
        self.execution_summary["unit_tests"] = {
            "executed": True,
            "results": unit_results
        }
        self.execution_summary["total_duration"] = duration
        self.execution_summary["overall_success"] = all(r["success"] for r in unit_results)
        
        self._print_combined_summary()
        return self.execution_summary
    
    def run_integration_tests_only(self, verbose: bool = False, fail_fast: bool = False) -> Dict:
        """Run only integration tests."""
        print("🏃‍♂️ Running Integration Tests Only")
        print("=" * 50)
        
        # Check prerequisites first
        if not self.integration_runner.check_integration_prerequisites():
            self.execution_summary["integration_tests"] = {
                "executed": False,
                "results": [],
                "error": "Prerequisites not met"
            }
            self.execution_summary["overall_success"] = False
            return self.execution_summary
        
        start_time = time.time()
        integration_results = self.integration_runner.run_all_integration_tests(verbose, fail_fast)
        duration = time.time() - start_time
        
        self.execution_summary["integration_tests"] = {
            "executed": True,
            "results": integration_results
        }
        self.execution_summary["total_duration"] = duration
        self.execution_summary["overall_success"] = all(r["success"] for r in integration_results)
        
        self._print_combined_summary()
        return self.execution_summary
    
    def run_all_tests(self, verbose: bool = False, fail_fast: bool = False) -> Dict:
        """Run all tests: unit tests first, then integration tests."""
        print("🚀 Running Complete Agent System Test Suite")
        print("📋 Strategy: Unit tests first (rapid feedback), then integration tests (comprehensive validation)")
        print("=" * 80)
        
        overall_start_time = time.time()
        
        # Phase 1: Unit Tests (Rapid Feedback)
        print("\n📍 PHASE 1: Unit Tests (Rapid Feedback)")
        print("-" * 50)
        
        unit_start_time = time.time()
        unit_results = self.unit_runner.run_all_unit_tests(verbose, fail_fast)
        unit_duration = time.time() - unit_start_time
        
        self.execution_summary["unit_tests"] = {
            "executed": True,
            "results": unit_results,
            "duration": unit_duration
        }
        
        unit_success = all(r["success"] for r in unit_results)
        
        if not unit_success:
            failed_unit_tests = [r for r in unit_results if not r["success"]]
            print(f"\n❌ Unit tests failed ({len(failed_unit_tests)} failures)")
            
            if fail_fast:
                print("💥 Stopping execution due to unit test failures (fail-fast mode)")
                self.execution_summary["total_duration"] = time.time() - overall_start_time
                self.execution_summary["overall_success"] = False
                self._print_combined_summary()
                return self.execution_summary
            else:
                print("⚠️  Continuing with integration tests despite unit test failures")
        else:
            print(f"✅ Unit tests passed ({unit_duration:.1f}s)")
        
        # Phase 2: Integration Tests (Comprehensive Validation)
        print(f"\n📍 PHASE 2: Integration Tests (Comprehensive Validation)")
        print("-" * 50)
        
        # Check prerequisites
        if not self.integration_runner.check_integration_prerequisites():
            print("❌ Integration test prerequisites not met")
            self.execution_summary["integration_tests"] = {
                "executed": False,
                "results": [],
                "error": "Prerequisites not met"
            }
        else:
            integration_start_time = time.time()
            integration_results = self.integration_runner.run_all_integration_tests(verbose, fail_fast)
            integration_duration = time.time() - integration_start_time
            
            self.execution_summary["integration_tests"] = {
                "executed": True,
                "results": integration_results,
                "duration": integration_duration
            }
        
        # Calculate overall results
        self.execution_summary["total_duration"] = time.time() - overall_start_time
        
        integration_success = True
        if self.execution_summary["integration_tests"]["executed"]:
            integration_success = all(r["success"] for r in self.execution_summary["integration_tests"]["results"])
        
        self.execution_summary["overall_success"] = unit_success and integration_success
        
        self._print_combined_summary()
        return self.execution_summary
    
    def _print_combined_summary(self):
        """Print comprehensive test execution summary."""
        print("\n" + "=" * 80)
        print("📊 COMBINED TEST EXECUTION SUMMARY")
        print("=" * 80)
        
        # Unit test summary
        if self.execution_summary["unit_tests"]["executed"]:
            unit_results = self.execution_summary["unit_tests"]["results"]
            unit_passed = sum(1 for r in unit_results if r["success"])
            unit_total = len(unit_results)
            unit_duration = self.execution_summary["unit_tests"].get("duration", 0)
            
            print(f"🏃‍♂️ Unit Tests: {unit_passed}/{unit_total} passed ({unit_duration:.1f}s)")
            
            if unit_passed == unit_total:
                print("   ✅ All unit tests passed - code changes unlikely to break basic functionality")
            else:
                failed_units = [r["suite"] for r in unit_results if not r["success"]]
                print(f"   ❌ Failed unit tests: {', '.join(failed_units)}")
        else:
            print("🏃‍♂️ Unit Tests: Not executed")
        
        # Integration test summary
        if self.execution_summary["integration_tests"]["executed"]:
            integration_results = self.execution_summary["integration_tests"]["results"]
            integration_passed = sum(1 for r in integration_results if r["success"])
            integration_total = len(integration_results)
            integration_duration = self.execution_summary["integration_tests"].get("duration", 0)
            
            print(f"🧪 Integration Tests: {integration_passed}/{integration_total} passed ({integration_duration:.1f}s)")
            
            if integration_passed == integration_total:
                print("   ✅ All integration tests passed - system performance and end-to-end scenarios validated")
            else:
                failed_integrations = [r["suite"] for r in integration_results if not r["success"]]
                print(f"   ❌ Failed integration tests: {', '.join(failed_integrations)}")
        elif "error" in self.execution_summary["integration_tests"]:
            error_msg = self.execution_summary["integration_tests"]["error"]
            print(f"🧪 Integration Tests: Not executed ({error_msg})")
        else:
            print("🧪 Integration Tests: Not executed")
        
        # Overall summary
        total_duration = self.execution_summary["total_duration"]
        print(f"\n⏱️  Total Execution Time: {total_duration:.1f}s")
        
        if self.execution_summary["overall_success"]:
            print("🎉 ALL TESTS PASSED")
            print("✅ Code changes validated - ready for manual end-to-end testing")
        else:
            print("💥 SOME TESTS FAILED") 
            print("❌ Review failures before proceeding to manual testing")
        
        # Performance insights
        self._print_performance_insights(total_duration)
    
    def _print_performance_insights(self, total_duration: float):
        """Print performance insights and recommendations."""
        print(f"\n📈 Performance Insights:")
        
        # Performance categorisation based on total duration
        if total_duration < 60:
            print(f"   🚀 Excellent performance ({total_duration:.1f}s) - ideal for rapid development feedback")
        elif total_duration < 120:
            print(f"   ✅ Good performance ({total_duration:.1f}s) - suitable for regular testing")
        elif total_duration < 300:
            print(f"   ⚠️  Moderate performance ({total_duration:.1f}s) - consider optimising slow tests")
        else:
            print(f"   🐌 Slow performance ({total_duration:.1f}s) - investigate performance bottlenecks")
        
        # Test strategy recommendations
        unit_executed = self.execution_summary["unit_tests"]["executed"]
        integration_executed = self.execution_summary["integration_tests"]["executed"]
        
        if unit_executed and integration_executed:
            unit_duration = self.execution_summary["unit_tests"].get("duration", 0)
            integration_duration = self.execution_summary["integration_tests"].get("duration", 0)
            
            if unit_duration > 30:
                print(f"   💡 Unit tests took {unit_duration:.1f}s - consider optimising for sub-30s target")
            
            if integration_duration > 180:
                print(f"   💡 Integration tests took {integration_duration:.1f}s - normal for comprehensive validation")
        
        print(f"   📋 Recommendation: Run unit tests frequently, integration tests before major releases")


def main():
    """Main entry point for combined test runner."""
    parser = argparse.ArgumentParser(
        description="Agent System Combined Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_all_tests.py                    # Run all tests (unit then integration)
  python run_all_tests.py --unit-only       # Run only unit tests  
  python run_all_tests.py --integration-only # Run only integration tests
  python run_all_tests.py --verbose         # Verbose output
  python run_all_tests.py --fail-fast       # Stop on first failure
        """
    )
    
    parser.add_argument(
        "--unit-only",
        action="store_true",
        help="Run only unit tests"
    )
    parser.add_argument(
        "--integration-only", 
        action="store_true",
        help="Run only integration tests"
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
    
    args = parser.parse_args()
    
    # Validate mutually exclusive options
    if args.unit_only and args.integration_only:
        print("❌ Error: --unit-only and --integration-only are mutually exclusive")
        return 1
    
    runner = CombinedTestRunner()
    
    try:
        if args.unit_only:
            results = runner.run_unit_tests_only(args.verbose, args.fail_fast)
        elif args.integration_only:
            results = runner.run_integration_tests_only(args.verbose, args.fail_fast)
        else:
            results = runner.run_all_tests(args.verbose, args.fail_fast)
        
        # Return appropriate exit code
        return 0 if results["overall_success"] else 1
        
    except KeyboardInterrupt:
        print("\n🛑 Test execution interrupted by user")
        return 130
    except Exception as e:
        print(f"💥 Test runner error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())