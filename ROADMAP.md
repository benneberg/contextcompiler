# CCC Release & Distribution Roadmap

Phase 1 — Make CCC installable everywhere ⭐⭐⭐⭐⭐

Goal: pip install ccc-contextcompiler works from any computer or GitHub Action.

Step 1. Verify packaging

already have:

* ✅ pyproject.toml
* ✅ [project.scripts]
* ✅ ccc = "ccc.cli:main"
* ✅ package discovery
* ✅ metadata

No major changes needed.

⸻

Step 2. Build the package locally

Install the build tools:

python -m pip install --upgrade build twine

Build the package:

python -m build

we should get:

dist/
ccc_contextcompiler-0.1.0.tar.gz
ccc_contextcompiler-0.1.0-py3-none-any.whl

⸻

Step 3. Test the built package

Install the wheel into a clean environment:

pip install dist/ccc_contextcompiler-0.1.0-py3-none-any.whl

Verify:

ccc --version
ccc --doctor
ccc .

If these work, the package is ready for PyPI.

⸻

Phase 2 — Publish to PyPI ⭐⭐⭐⭐⭐

Create accounts on:

* PyPI
* TestPyPI (recommended)

Upload first to TestPyPI:

twine upload --repository testpypi dist/*

Install from TestPyPI:

pip install --index-url https://test.pypi.org/simple ccc-contextcompiler

If everything works:

twine upload dist/*

Now everyone can simply do:

pip install ccc-contextcompiler

⸻

Phase 3 — Automatic GitHub Releases ⭐⭐⭐⭐⭐

Instead of manually uploading.

Create a workflow:

.github/workflows/release.yml

Workflow:

Tag pushed
↓
Run tests
↓
Build package
↓
Publish to PyPI
↓
Create GitHub Release

Then releasing becomes:

git tag v0.1.0
git push origin v0.1.0

Done.

⸻

Phase 4 — Improve GitHub Actions ⭐⭐⭐⭐☆

Replace the current CCC workflow with:

Checkout
↓
Install Python
↓
Install CCC
↓
Verify installation
↓
Run CCC
↓
Commit changes

Verification step:

ccc --version
ccc --doctor

This makes failures much easier to diagnose.

⸻

Phase 5 — Versioning ⭐⭐⭐⭐☆

Use Semantic Versioning.

Example:

0.1.0
0.1.1
0.2.0
0.3.0
1.0.0

Meaning:

Patch
Bug fixes
Minor
New features
Major
Breaking changes

⸻

Phase 6 — Keep Tests Running ⭐⭐⭐⭐⭐

Continue running tests on

* Python 3.10
* Python 3.11
* Python 3.12

before every release.

Never publish if tests fail.

⸻

Phase 7 — Public Python API ⭐⭐⭐⭐☆

This is the only place I’d make a small architectural improvement.

Right now people use:

ccc

Internally, the CLI probably already calls functions.

Simply expose those functions.

Example:

from ccc import generate_context
generate_context(".")

or

from ccc import Workspace
workspace.generate()

Nothing changes internally.

we simply making existing functionality importable.

Benefits:

* IDE plugins
* web applications
* MCP server
* automation
* AI agents
* unit tests

all become much easier.

⸻

Phase 8 — Keep CLI as the Main Interface ⭐⭐⭐⭐⭐

Don’t remove anything.

Keep:

ccc
ccc workspace
ccc query
ccc inspect
ccc feedback

The CLI should simply call the library.

This is how tools like:

* pytest
* black
* uv
* pip

are designed.

⸻

Phase 9 — Documentation ⭐⭐⭐⭐☆

Update the README.

Current installation:

pip install ccc-contextcompiler

Once PyPI is live, that’s perfect.

Add a section:

Development
pip install -e .

for contributors.

⸻

Phase 10 — Better CI ⭐⭐⭐⭐☆

I’d have three workflows.

tests.yml

Runs every push.

Checkout
↓
Install
↓
Run tests
↓
Coverage

⸻

release.yml

Runs on tags.

Tests
↓
Build
↓
Publish
↓
GitHub Release

⸻

ccc-update.yml

Runs in repositories using CCC.

Checkout
↓
Install CCC
↓
Generate context
↓
Commit .llm-context

⸻

Phase 11 — Long-Term Integrations ⭐⭐⭐☆

These don’t change CCC.

They simply reuse it.

Possible future integrations:

✅ VS Code Extension

✅ Cursor Extension

✅ MCP Server

✅ REST API

✅ Docker image

✅ GitHub App

✅ Pre-commit hook

All using the same engine.

⸻

Phase 12 — Release Checklist ⭐⭐⭐⭐⭐

Before each release:

* Update version
* Run tests
* Build package
* Install built wheel
* Verify CLI works
* Update CHANGELOG
* Tag release
* Push tag

GitHub does the rest.

⸻

Phase 13 — Future Growth ⭐⭐☆

As adoption grows, consider adding:

* Homebrew formula (macOS)
* Winget package (Windows)
* APT package (Linux)
* Docker image
* Dev Container

These make installation even easier but are optional.

⸻

Final Architecture

                 CCC Core
                      │
      ┌───────────────┼───────────────┐
      │               │               │
      │               │               │
    CLI         Python API        Future API
      │               │               │
      └───────────────┼───────────────┘
                      │
               Context Engine
                      │
     ┌────────────────┼────────────────┐
     │                │                │
 Extractors     Query Engine     Alignment
     │                │                │
     └────────────────┼────────────────┘
                      │
              .llm-context IR
                      │
     ┌────────────┬──────────────┬─────────────┐
     │            │              │             │
 GitHub CI   VS Code/Cursor   MCP Server   Your Apps


prioritizing the remaining work in this order:

1. Publish to TestPyPI, then PyPI so installation works everywhere.
2. Automate releases with GitHub Actions and Trusted Publishing.
3. Expose a small, stable Python API that wraps the existing engine without changing its behavior.
4. Add integrations (VS Code, MCP, GitHub App, etc.) only after the packaging and release pipeline are solid.

That sequence gives the biggest improvement in usability while keeping CCC’s existing functionality and architecture intact.
