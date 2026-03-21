# Testing Guide

***In short***
1. Install test dependencies
pip install -r tests/requirements.txt

2. Run the tests
python tests/run_tests.py --verbose

3. Check that all tests pass
You should see output like:
- tests/integration/test_current_functionality.py::TestPythonFastAPI::test_generates_context_directory PASSED
- tests/integration/test_current_functionality.py::TestPythonFastAPI::test_generates_tree_file PASSED
- ...

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


### Test commands:  
```
The ccc query command lets you interrogate the artifacts programmatically it is a meaningful feature. It's the difference between a generated report and a queryable database.
Note: Differences between single repo vs multi repo workspace. If you pip install networkx, the traversal becomes fully graph-aware for transitive deps.
# Query — interrogate artifacts at runtime
ccc query "UserService"                    # search everything
ccc query --type symbol CreateUser         # exact symbol search  
ccc query --type route /users              # route search
ccc query --type impact UserService        # what breaks if this changes?
ccc query --type context "auth flow"       # build LLM-ready context block
ccc query --format json "platform"         # machine-readable output

# Align — detect drift between code and PKML
ccc align                                  # auto-detect pkml.json
ccc align --pkml product-knowledge/pkml.json
ccc align --format json                    # for CI integration

```