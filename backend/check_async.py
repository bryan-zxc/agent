#!/usr/bin/env python3
"""
Async/Await Correctness Checker

Quick script to run targeted async/await validation during development.
This complements pre-commit hooks by providing fast feedback while coding.

Key differences from pre-commit hooks:
- Runs manually when YOU want feedback
- Faster execution (only async checks)
- Can run on dirty/uncommitted files
- Great for iterative development

Usage:
    python check_async.py                    # Check all critical modules
    python check_async.py --module tasks    # Check specific module
    python check_async.py --file worker_tasks.py  # Check specific file
    docker-compose exec backend uv run python check_async.py
"""

import subprocess
import sys
import argparse
from pathlib import Path


def run_command(cmd, description, show_output=True):
    """Run a command and return success status"""
    print(f"\n🔍 {description}...")
    if show_output:
        print(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            print("✅ PASSED")
            if result.stdout.strip() and "All checks passed" not in result.stdout:
                print(f"Output: {result.stdout.strip()}")
            return True
        else:
            print("❌ FAILED")
            if result.stdout.strip():
                print(f"STDOUT:\n{result.stdout}")
            if result.stderr.strip():
                print(f"STDERR:\n{result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ TIMEOUT")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def get_module_path(module_name):
    """Get the path for a specific module"""
    module_paths = {
        "tasks": "src/agent/tasks/",
        "core": "src/agent/core/",
        "models": "src/agent/models/",
        "services": "src/agent/services/",
        "utils": "src/agent/utils/",
    }
    return module_paths.get(module_name, f"src/agent/{module_name}/")


def main():
    """Run async correctness checks"""
    parser = argparse.ArgumentParser(description="Check async/await correctness")
    parser.add_argument(
        "--module", help="Check specific module (tasks, core, models, services, utils)"
    )
    parser.add_argument("--file", help="Check specific file path")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--mypy-only", action="store_true", help="Run only MyPy checks")
    parser.add_argument("--ruff-only", action="store_true", help="Run only Ruff checks")

    args = parser.parse_args()

    if not args.quiet:
        print("🧪 Async/Await Correctness Checker")
        print("=" * 50)

    # Determine what to check
    if args.file:
        target_path = args.file
        if not Path(target_path).exists():
            print(f"❌ Error: File not found: {target_path}")
            sys.exit(1)
    elif args.module:
        target_path = get_module_path(args.module)
        if not Path(target_path).exists():
            print(f"❌ Error: Module path not found: {target_path}")
            sys.exit(1)
    else:
        # Default: check critical modules where async issues are most likely
        target_path = ["src/agent/tasks/", "src/agent/core/"]

    # Change to backend directory
    backend_dir = Path(__file__).parent
    if not args.quiet:
        print(f"Working directory: {backend_dir}")

    # Check if we're in the right directory
    if not (backend_dir / "src" / "agent").exists():
        print("❌ Error: Not in backend directory or missing src/agent")
        sys.exit(1)

    checks = []

    # Run checks based on arguments
    if not args.mypy_only:
        if isinstance(target_path, list):
            for path in target_path:
                checks.append(
                    run_command(
                        ["uv", "run", "ruff", "check", path, "--select", "ASYNC"],
                        f"Ruff async checks on {path}",
                        show_output=not args.quiet,
                    )
                )
        else:
            checks.append(
                run_command(
                    ["uv", "run", "ruff", "check", target_path, "--select", "ASYNC"],
                    f"Ruff async checks on {target_path}",
                    show_output=not args.quiet,
                )
            )

    if not args.ruff_only:
        if isinstance(target_path, list):
            # For multiple paths, focus on the most critical files
            critical_files = [
                "src/agent/tasks/task_utils.py",
                "src/agent/tasks/planner_tasks.py",
                "src/agent/tasks/worker_tasks.py",
                "src/agent/core/router.py",
            ]
            for file_path in critical_files:
                if Path(file_path).exists():
                    checks.append(
                        run_command(
                            [
                                "uv",
                                "run",
                                "mypy",
                                file_path,
                                "--config-file",
                                "mypy.ini",
                                "--show-error-codes",
                            ],
                            f"MyPy coroutine checks on {file_path}",
                            show_output=not args.quiet,
                        )
                    )
        else:
            checks.append(
                run_command(
                    [
                        "uv",
                        "run",
                        "mypy",
                        target_path,
                        "--config-file",
                        "mypy.ini",
                        "--show-error-codes",
                    ],
                    f"MyPy coroutine checks on {target_path}",
                    show_output=not args.quiet,
                )
            )

    # Summary
    if not args.quiet:
        print("\n" + "=" * 50)
        print("📊 SUMMARY")

    passed = sum(checks)
    total = len(checks)

    if passed == total:
        if args.quiet:
            print("✅ All async checks passed")
        else:
            print(f"✅ All checks passed ({passed}/{total})")
            print("\n🎉 No async/await issues detected!")
        sys.exit(0)
    else:
        if args.quiet:
            print(f"❌ {total - passed} async issues found")
        else:
            print(f"❌ Some checks failed ({passed}/{total})")
            print("\n⚠️  Async/await issues detected - please review and fix")
        sys.exit(1)


if __name__ == "__main__":
    main()
