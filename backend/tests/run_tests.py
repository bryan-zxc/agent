#!/usr/bin/env python
"""
Agent System Test Runner - Main Entry Point

Simplified interface to the Agent System test suite with commonly used configurations.

Usage:
    # Quick unit tests for development (default)
    python run_tests.py
    
    # All tests (unit + integration)
    python run_tests.py --all
    
    # Only integration tests
    python run_tests.py --integration
    
    # With verbose output
    python run_tests.py --verbose
    
    # Stop on first failure
    python run_tests.py --fail-fast
    
    # Docker environment (recommended)
    docker-compose exec backend uv run python tests/run_tests.py
"""

import argparse
import sys
import os
from pathlib import Path

# Add current directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent))

from run_all_tests import CombinedTestRunner


def main():
    """Main entry point with simplified interface."""
    parser = argparse.ArgumentParser(
        description="Agent System Test Runner - Simplified Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Common Usage Patterns:
  python run_tests.py                  # Quick unit tests (default)
  python run_tests.py --all           # Full test suite (unit + integration)  
  python run_tests.py --integration   # Integration tests only
  python run_tests.py --verbose       # Verbose output
  python run_tests.py --fail-fast     # Stop on first failure

Development Workflow:
  1. Make code changes
  2. Run: python run_tests.py (unit tests for quick feedback)
  3. If unit tests pass, optionally run: python run_tests.py --all
  4. Proceed with manual end-to-end testing
        """
    )
    
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all tests (unit + integration) - comprehensive validation"
    )
    parser.add_argument(
        "--integration",
        action="store_true", 
        help="Run integration tests only - performance and end-to-end validation"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose test output with detailed information"
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop execution on first test failure"
    )
    
    args = parser.parse_args()
    
    # Print usage context
    if args.all:
        print("🎯 Running FULL test suite (unit + integration)")
        print("📝 Use case: Before major releases, comprehensive validation")
    elif args.integration:
        print("🎯 Running INTEGRATION tests only")  
        print("📝 Use case: Performance validation, end-to-end scenarios")
    else:
        print("🎯 Running UNIT tests only (default)")
        print("📝 Use case: Development workflow, quick error detection")
    
    runner = CombinedTestRunner()
    
    try:
        if args.all:
            results = runner.run_all_tests(args.verbose, args.fail_fast)
        elif args.integration:
            results = runner.run_integration_tests_only(args.verbose, args.fail_fast)
        else:
            # Default: unit tests only for rapid development feedback
            results = runner.run_unit_tests_only(args.verbose, args.fail_fast)
        
        return 0 if results["overall_success"] else 1
        
    except KeyboardInterrupt:
        print("\n🛑 Test execution interrupted by user")
        return 130
    except Exception as e:
        print(f"💥 Test runner error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())