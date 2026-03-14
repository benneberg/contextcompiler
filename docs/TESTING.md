# Testing Guide

## Running Tests

### Install test dependencies
```bash
pip install -r tests/requirements.txt
```
### Run all tests
```bash
python tests/run_tests.py
```
### Run with verbose output
```bash
python tests/run_tests.py --verbose
```
###Run with coverage report
```bash
python tests/run_tests.py --coverage
```

## This generates an HTML coverage report in htmlcov/index.html.

### Test Structure
tests/
├── fixtures/              # Test projects
│   ├── python-fastapi/    # Minimal FastAPI app
│   └── typescript-express/# Minimal Express app
├── integration/           # Integration tests
│   └── test_current_functionality.py
├── unit/                  # Unit tests (coming in Phase 2)
└── run_tests.py          # Test runner

## Writing Tests
### Integration Tests
Integration tests use real fixture projects and run the full generator:
```Python
def test_generates_tree_file(fastapi_project, tmp_path):
    """Test that tree.txt is generated."""
    import shutil
    test_project = tmp_path / "test-project"
    shutil.copytree(fastapi_project, test_project)
    
    subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=test_project,
        capture_output=True,
    )
    
    tree_file = test_project / ".llm-context" / "tree.txt"
    assert tree_file.exists()
```
### Fixtures
Fixtures are minimal but realistic projects:

- Include common patterns (models, routes, types)
- Small enough to test quickly
- Comprehensive enough to test all features  

### Baseline Testing
Before modularization (Phase 2), we establish a baseline:

1. Run all tests: python tests/run_tests.py
2. All tests should pass
3. Tag this state: git tag v0.4.0-baseline  
During refactoring, continuously run tests to ensure nothing breaks.

### CI Integration
Tests run automatically on every commit via GitHub Actions (see .github/workflows/test.yml).

