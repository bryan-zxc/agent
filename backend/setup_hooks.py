#!/usr/bin/env python3
"""
Pre-commit Hook Setup Script

Sets up git pre-commit hooks for async/await correctness checking.
Run this once after cloning the repository or when pre-commit config changes.

Usage:
    python setup_hooks.py
    docker-compose exec backend uv run python setup_hooks.py
"""

import subprocess
import sys
from pathlib import Path

def run_command(cmd, description):
    """Run a command and return success status"""
    print(f"🔧 {description}...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, text=True, timeout=60)
        print("✅ SUCCESS")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ FAILED: {e}")
        return False
    except subprocess.TimeoutExpired:
        print("❌ TIMEOUT")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    """Setup pre-commit hooks"""
    print("🪝 Pre-commit Hook Setup")
    print("=" * 40)
    
    # Check if we're in a git repository
    backend_dir = Path(__file__).parent
    if not (backend_dir / ".git").exists() and not (backend_dir.parent / ".git").exists():
        print("❌ Error: Not in a git repository")
        print("Make sure you're running this from the backend directory of a git repo")
        sys.exit(1)
    
    # Check if pre-commit config exists
    if not (backend_dir / ".pre-commit-config.yaml").exists():
        print("❌ Error: .pre-commit-config.yaml not found")
        sys.exit(1)
    
    print(f"Working directory: {backend_dir}")
    
    # Install pre-commit hooks
    success = run_command([
        "uv", "run", "pre-commit", "install"
    ], "Installing pre-commit hooks")
    
    if not success:
        print("\n❌ Failed to install pre-commit hooks")
        sys.exit(1)
    
    # Run a test to make sure everything works
    print("\n🧪 Testing pre-commit setup...")
    success = run_command([
        "uv", "run", "pre-commit", "run", "--all-files", "--show-diff-on-failure"
    ], "Running pre-commit on all files (test run)")
    
    if success:
        print("\n✅ Pre-commit hooks installed successfully!")
        print("\n📋 What happens now:")
        print("  • Every git commit will run async/await checks automatically")
        print("  • Commits will be blocked if async issues are found")
        print("  • Run 'python check_async.py' for quick manual checks")
        print("  • Run 'pre-commit run --all-files' to check all files manually")
        
    else:
        print("\n⚠️  Pre-commit hooks installed but found issues in existing code")
        print("This is expected if there are existing async/await problems.")
        print("\nNext steps:")
        print("  1. Fix the issues shown above")
        print("  2. Run 'python check_async.py' to verify fixes")
        print("  3. Commit your changes - hooks will prevent future async issues")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()