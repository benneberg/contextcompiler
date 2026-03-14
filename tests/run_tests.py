#!/usr/bin/env python3
# Make this file executable: chmod +x tests/run_tests.py
"""
Test runner for LLM Context Generator.

Usage:
    python tests/run_tests.py
    python tests/run_tests.py --verbose
    python tests/run_tests.py --coverage
"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def run_tests(verbose=False, coverage=False):
    """Run all tests."""
    args = [sys.executable, "-m", "pytest"]
    
    if verbose:
        args.append("-v")
    
    if coverage:
        args.extend(["--cov=.", "--cov-report=html", "--cov-report=term"])
    
    # Add test directory
    args.append(str(PROJECT_ROOT / "tests"))
    
    print(f"Running: {' '.join(args)}")
    print("-" * 60)
    
    result = subprocess.run(args, cwd=PROJECT_ROOT)
    return result.returncode


def check_pytest_installed():
    """Check if pytest is installed."""
    try:
        import pytest
        return True
    except ImportError:
        print("Error: pytest not installed")
        print("Install with: pip install pytest")
        if "--coverage" in sys.argv:
            print("For coverage: pip install pytest-cov")
        return False


if __name__ == "__main__":
    if not check_pytest_installed():
        sys.exit(1)
    
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    coverage = "--coverage" in sys.argv
    
    exit_code = run_tests(verbose=verbose, coverage=coverage)
    sys.exit(exit_code)
