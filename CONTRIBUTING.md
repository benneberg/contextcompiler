# Contributing to CCC (Code Context Compiler)

Thank you for your interest in contributing!

## Development setup

```bash
git clone https://github.com/benneberg/contextcompiler.git
cd contextcompiler
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[all]"
```
## Running tests
```
pytest
# or with coverage
pytest --cov=ccc --cov-report=term-missing
```
## Code style
•  We use ruff for linting and formatting.
•  Target Python 3.10+.
•  Keep the core dependency-free (optional extras only).

```
ruff check .
ruff format .
```
## Pull requests
1.  Fork the repository and create a feature branch.
2.  Make your changes with clear, focused commits.
3.  Add or update tests when relevant.
4.  Ensure tests and ruff pass.
5.  Open a PR against main with a clear description of the change.
## Questions?
Open an issue or start a discussion. All skill levels are welcome.
