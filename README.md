# CCC — Code Context Compiler

**A deterministic intermediate representation of your codebase, optimized for AI.**

CCC sits between raw code and LLMs. It scans your repositories and produces structured,
queryable artifacts that give AI tools precise, grounded context — without flooding
the context window with raw source files.

```bash
pip install ccc-contextcompiler
ccc                        # generate context for current directory
ccc query "UserService"    # query artifacts at runtime
ccc align                  # check code matches product documentation
ccc workspace serve        # open browser UI for the whole team
```

---

## The Core Idea

Most AI coding tools try to make LLMs smarter about code. CCC takes the opposite approach:

> **Make code understandable first. Then give it to LLMs.**

Like a compiler, CCC transforms source code into a well-defined intermediate representation
(IR). The `.llm-context/` directory is that IR — deterministic, precise, cacheable,
and consumable by any tool.

```
Code → CCC (IR) → .llm-context/ artifacts
                        ↓
               Query Engine    ← runtime interrogation
               Graph Analysis  ← impact reasoning
               Alignment       ← intent vs reality
                        ↓
               LLMs / Copilot / CI / Tools
```

**CCC = Reality** (what exists, extracted deterministically from code)  
**PKML = Intent** (what should exist, declared by humans)  
The Alignment Engine combines them — never merge the two sources.

---

## Why It Exists

Modern codebases are too large, too distributed, and too implicit for LLMs to work with
directly. The most valuable engineering knowledge is rarely in the code itself:

- Which modules are dangerous and why
- What conventions the team actually follows
- Which services depend on which, and in what order changes must land
- What the code is *supposed* to do versus what it actually does
- Which cross-repo dependencies nobody documented

CCC makes that knowledge **extractable, structured, portable, and reusable**.

---

## What Makes This Different

| | CCC | Repomix | Cursor indexing | Manual copying |
|---|---|---|---|---|
| **Extracts semantic context** | ✓ | ✗ | Partial | ✗ |
| **Symbol → file:line index** | ✓ | ✗ | ✓ | ✗ |
| **Convention detection** | ✓ | ✗ | ✗ | ✗ |
| **Cross-repo analysis** | ✓ | ✗ | ✗ | ✗ |
| **Undeclared dep discovery** | ✓ | ✗ | ✗ | ✗ |
| **Intent vs reality check** | ✓ | ✗ | ✗ | ✗ |
| **Offline / corporate safe** | ✓ | ✓ | ✗ | ✓ |
| **CI-ready, incremental** | ✓ | ✗ | ✗ | ✗ |
| **Zero required deps** | ✓ | ✗ | ✗ | ✓ |

**vs Repomix:** Repomix concatenates files. CCC extracts *semantic* context (types,
routes, dependencies, conventions) and keeps it queryable and incrementally updated.

---

## Installation

### Recommended

```bash
pip install ccc-contextcompiler
```

With optional features:

```bash
pip install "ccc-contextcompiler[yaml]"    # YAML workspace manifests (recommended)
pip install "ccc-contextcompiler[watch]"   # watch mode
pip install "ccc-contextcompiler[ai]"      # LLM module summaries
pip install "ccc-contextcompiler[all]"     # everything
```

### Development (editable install)

```bash
git clone https://github.com/benneberg/contextcompiler
cd contextcompiler
pip install -e .                           # Linux / Mac
pip install -e . --break-system-packages   # if pip complains on Linux
```

On Windows, if you get a setuptools error:
```bash
python -m pip install --upgrade pip setuptools wheel
pip install -e .
```

### Standalone (zero dependencies)

```bash
curl -O https://raw.githubusercontent.com/benneberg/contextcompiler/main/llm-context-setup.py
python3 llm-context-setup.py
```

**Requirements:** Python 3.10+. Core generation has zero mandatory dependencies.

---

## Quick Start

```bash
ccc --doctor           # verify your environment
ccc                    # generate context for current directory
ccc --quick-update     # fast incremental update after code changes
ccc query "User"       # interrogate the generated artifacts
ccc align              # check code matches product documentation
```

After the first run:

```
your-project/
├── .llm-context/
│   ├── tree.txt                     directory structure
│   ├── routes.txt                   API route map
│   ├── public-api.txt               exported function signatures
│   ├── schemas-extracted.py         Python dataclasses, Pydantic, enums
│   ├── types-extracted.ts           TypeScript interfaces, types, enums
│   ├── dependency-graph.txt         internal import relationships
│   ├── dependency-graph.md          Mermaid dependency diagram
│   ├── symbol-index.json            symbol → file:line navigation map
│   ├── external-dependencies.json   what this service exposes and consumes
│   ├── env-shape.txt                environment variable template
│   ├── db-schema.txt                database models (SQLAlchemy, Prisma, etc.)
│   ├── entry-points.json            main files, servers, CLI entry points
│   ├── recent-commits.txt           last 20 git commits
│   └── manifest.json                generation metadata and cache
├── LLM.md                           auto-detected conventions, patterns, dangerous files
└── ARCHITECTURE.md                  architecture description scaffold
```

---

## All Commands

### Single-Repository

```bash
ccc [path]                    Generate context for a project (default: current dir)
ccc --quick-update  / -q      Incremental update — only regenerates changed files
ccc --force         / -f      Ignore cache, regenerate everything from scratch
ccc --watch                   Watch mode — auto-update on file save
ccc --with-summaries          Add LLM-powered module summaries (requires [ai])
ccc --doctor                  Diagnostics — Python version, project structure, status
ccc --security-status         Show current security mode and redaction settings
ccc --output DIR    / -o DIR  Write context to a custom directory
ccc --config FILE   / -c FILE Use a custom llm-context.yml or .json config
ccc --version       / -v      Print version
```

---

### `ccc query` — Interrogate Artifacts at Runtime

Query `.llm-context/` artifacts without reading files manually.

```bash
ccc query TERM                         Search across all artifact types
ccc query --type symbol  TERM          Symbol lookup (classes, functions, types)
ccc query --type route   TERM          Route/endpoint search
ccc query --type impact  TERM          What breaks if this symbol changes?
ccc query --type context TERM          Build an LLM-ready focused context block
ccc query --type api     TERM          Search public function signatures
ccc query --type all     TERM          Explicit all-types search (default)

ccc query --format human   TERM        Human-readable terminal output (default)
ccc query --format json    TERM        Machine-readable JSON (pipe to other tools)
ccc query --format compact TERM        Minimal token output (for prompt injection)
ccc query --format markdown TERM       Markdown block (for Copilot Chat)

ccc query --limit 20       TERM        Max results per section (default: 10)
ccc query --context-dir DIR TERM       Point at a non-default .llm-context/
```

**Examples:**

```bash
ccc query "UserService"                      # find everything named UserService
ccc query --type symbol  CreateUserRequest   # exact file:line location
ccc query --type route   /api/users          # route search
ccc query --type impact  UserModel           # what depends on UserModel?
ccc query --type context "authentication"    # LLM-ready focused context block
ccc query --format json  "platform"          # pipe to jq or other tools
ccc query --format compact "user" --limit 5  # minimal prompt injection
```

**Python API:**

```python
from ccc.query import CCCQueryEngine

engine = CCCQueryEngine(".llm-context")

# Unified search across all artifacts
result = engine.query("user")
# result.symbols, result.routes, result.public_api, result.schemas, result.dependencies

# Exact symbol lookup
sym = engine.find_symbol("CreateUserRequest")
# sym.file → "services/users.py", sym.line → 42, sym.kind → "class"

# Impact analysis: what depends on this?
impact = engine.find_impact("UserModel")
# impact["direct_dependents"], impact["transitive_dependents"], impact["total_affected"]

# LLM context builder — precise, focused, minimal tokens
context = engine.build_llm_context("authentication flow", format="markdown")
# Returns a focused markdown block — paste directly into Copilot Chat or any LLM

# Output formats
json_ctx    = engine.build_llm_context("user", format="json")
compact_ctx = engine.build_llm_context("user", format="compact")

# Engine stats
print(engine.stats())
# {"symbols": 142, "routes": 28, "dependency_edges": 67, ...}
```

Install `networkx` for graph-aware transitive impact analysis:
```bash
pip install networkx
```

---

### `ccc align` — Detect Drift Between Code and Documentation

Compares what the code actually does (CCC artifacts) against what product
documentation says it should do (PKML). Degrades gracefully — partial PKML
gives partial checking, no PKML gives a helpful message rather than an error.

```bash
ccc align                              Auto-detect pkml.json, show drift report
ccc align --pkml path/to/pkml.json     Use a specific PKML file
ccc align --format json                Machine-readable output for CI
ccc align --context-dir DIR            Point at a non-default .llm-context/
```

**Example output:**

```
  PKML completeness: 80%

  ✓  Confirmed (5 match):
     ✓  GET /api/users
     ✓  POST /api/users
     ✓  DELETE /api/users/{id}
     ✓  GET /api/users/{id}
     ✓  POST /api/events/track

  ✗  Errors (1):
     ✗  POST /api/auth/reset-password
        In PKML but not found in routes.txt
        → Implement this endpoint or remove it from PKML

  ⚠  Warnings (1):
     ⚠  DELETE /internal/purge-cache
        In code but not declared in PKML
        → Add to PKML exposes.api or prefix with /internal/

  Summary: 1 error(s), 1 warning(s), 5 confirmed
```

**In CI (exit code 1 on errors):**
```yaml
- name: Verify code matches documentation
  run: ccc --force && ccc align
```

---

### `ccc pkml` — Bootstrap Product Knowledge

Generate a `pkml.json` draft from generated `.llm-context/` files.
Requires `.llm-context/` to exist first — run `ccc` before `ccc pkml`.

```bash
ccc pkml                       Generate pkml.json in product-knowledge/
ccc pkml --output DIR          Custom output directory
ccc pkml --open                Open PKML editor in browser after generating
```

---

### `ccc workspace` — Multi-Repository Mode

All workspace commands work from a directory containing a `ccc-workspace.yml` file,
or with `--workspace path/to/ccc-workspace.yml`.

```bash
# Setup
ccc workspace init [path]               Scan directories, generate ccc-workspace.yml
ccc workspace init --name my-platform   Set workspace name
ccc workspace init --output DIR         Write manifest to a specific directory
ccc workspace init --force              Overwrite existing manifest

# Inspection
ccc workspace list                      List all services with tags and status
ccc workspace validate                  Check paths exist, detect circular deps

# Service discovery
ccc workspace query --tags core                    Find services by tag
ccc workspace query --tags auth users              Multiple tags (matches either)
ccc workspace query --service NAME                 Inspect one service (all info)
ccc workspace query --service NAME --what info     Basic info only
ccc workspace query --service NAME --what depends-on
ccc workspace query --service NAME --what dependents
ccc workspace query --service NAME --what external
ccc workspace query --tags TAG --generate           Also generate workspace context

# Context generation
ccc workspace generate                  Build cross-repo WORKSPACE.md, API map,
                                        change sequence, dependency graph
ccc workspace generate --tags TAG       Filter to specific services

# Dependency discovery
ccc workspace discover                  Find undeclared cross-repo dependencies
ccc workspace discover --tags TAG       Filter to specific services
ccc workspace discover --min-confidence 0.7  Stricter threshold (default: 0.5)
ccc workspace discover --output DIR     Custom output directory

# Conflict detection
ccc workspace conflicts                 Detect type conflicts, API mismatches,
                                        naming inconsistencies across repos
ccc workspace conflicts --tags TAG      Filter services
ccc workspace conflicts --output DIR    Custom report location
ccc workspace doctor                    Alias for conflicts

# Browser UI
ccc workspace serve                     Open browser UI at http://localhost:7842
ccc workspace serve --port 8080         Custom port
ccc workspace serve --no-open           Don't auto-open browser
ccc workspace serve --no-rebuild        Skip rebuilding service-index.json
```

---

## Output Files Reference

| File | Contents |
|------|----------|
| `tree.txt` | Annotated directory structure |
| `routes.txt` | API route map (FastAPI, Flask, Express, NestJS, etc.) |
| `public-api.txt` | Exported function signatures with types |
| `schemas-extracted.py` | Python dataclasses, Pydantic models, enums |
| `types-extracted.ts` | TypeScript interfaces, types, enums |
| `dependency-graph.txt` | Internal import relationships (text) |
| `dependency-graph.md` | Mermaid dependency diagram |
| `symbol-index.json` | Symbol → file:line navigation index |
| `external-dependencies.json` | Service boundary contracts (exposes + consumes) |
| `env-shape.txt` | Environment variable shape |
| `db-schema.txt` | Database models (SQLAlchemy, Django, Prisma, TypeORM) |
| `entry-points.json` | Main files, servers, CLI entry points |
| `recent-commits.txt` | Last 20 git commits |
| `LLM.md` | Auto-detected conventions, dangerous files, patterns |
| `ARCHITECTURE.md` | Architecture description scaffold |

---

## Language Support

| Language | Schemas | Routes | Signatures | Deps |
|----------|---------|--------|------------|------|
| Python | ✓ | ✓ | ✓ | ✓ |
| TypeScript | ✓ | ✓ | ✓ | ✓ |
| JavaScript | — | ✓ | — | ✓ |
| Rust | ✓ | — | — | — |
| Go | ✓ | — | — | — |
| C# | ✓ | — | — | — |

---

## Multi-Repository Workspace — Full Workflow

### Step 1 — Initialize

```bash
cd ~/company          # directory containing your service repos
ccc workspace init .  # auto-scans, generates ccc-workspace.yml draft
```

Edit the generated manifest to fill in descriptions and correct `depends_on` relationships:

```yaml
# ccc-workspace.yml
name: my-platform
version: 1

services:
  auth-service:
    path: ./auth-service
    type: backend-api
    tags: [auth, security, core]
    description: "Authentication and authorization"

  user-service:
    path: ./user-service
    type: backend-api
    tags: [users, core]
    depends_on: [auth-service]
    description: "User profiles and management"

  client:
    path: ./client
    type: frontend
    tags: [ui, platforms, core]
    depends_on: [user-service]
    description: "Web and device client"
```

### Step 2 — Generate context per service

```bash
cd auth-service && ccc && cd ..
cd user-service && ccc && cd ..
cd client       && ccc && cd ..
```

### Step 3 — Build workspace context

```bash
ccc workspace generate
```

Produces `workspace-context/` with:
- `WORKSPACE.md` — what these services do together, how they connect
- `cross-repo-api.txt` — all API calls between services
- `change-sequence.md` — correct order to implement changes (from dependency graph)
- `dependency-graph.md` — Mermaid cross-repo diagram
- `service-index.json` — cached index for offline queries and the UI

### Step 4 — Discover undeclared dependencies

```bash
ccc workspace discover
```

Reads `.llm-context/` artifacts and surfaces hidden coupling nobody put in the manifest.
Four detection methods:

| Method | What It Finds | Confidence |
|--------|--------------|------------|
| API route matching | Service A calls routes that Service B exposes | 75–95% |
| Schema cross-reference | Same type defined differently in two services | 50–85% |
| Shared infrastructure | Services sharing the same database, cache, or queue | 45–70% |
| Event coupling | Event emitted by one service, consumed by another | 88% |

Output: `workspace-context/discovered-relationships.md` and `.json`

### Step 5 — Open the browser UI

```bash
ccc workspace serve    # opens http://localhost:7842
```

Works for the whole team — no coding required. Features:
- Tag-based service filtering
- Service detail view with API endpoints, dependencies, types
- Dependency graph with declared vs discovered relationships
- Suggested change sequence for any task
- Copy-as-Markdown (for LLM prompts) and Download-as-JSON

---

## Daily Developer Workflow

### Single repo, solo work

```bash
# Morning: refresh context after overnight changes
ccc --quick-update

# Working on a task: query for relevant context
ccc query --type context "user authentication"  # paste into Copilot Chat
ccc query --type impact  "UserModel"             # check blast radius before changing
ccc query --type route   "/api/auth"             # find all auth-related endpoints

# After significant changes: update context
ccc --quick-update       # <2 seconds, only regenerates what changed

# Before a PR: verify alignment
ccc align                # check nothing documented is missing from code
```

### Multi-repo task (e.g. "implement tizen-tep platform support")

```bash
# Discover which repos are involved
ccc workspace query --tags platforms

# Check for undeclared dependencies first
ccc workspace discover --tags platforms

# Open the UI for a visual overview
ccc workspace serve

# Get LLM-ready context for the task
ccc workspace query --tags platforms --generate
# Then paste workspace-context/WORKSPACE.md into your LLM session
```

### Automated: git hook

```bash
# .git/hooks/post-commit
#!/bin/bash
if git diff HEAD~1 --name-only 2>/dev/null | grep -qE "\.(py|ts|js|go|rs)$"; then
  ccc --quick-update
fi
```

```bash
chmod +x .git/hooks/post-commit
```

---

## GitHub Copilot Integration

### `.github/copilot-instructions.md`

```markdown
# Copilot Instructions

Before suggesting any change, review:
- `LLM.md` — conventions, patterns, dangerous areas
- `ARCHITECTURE.md` — system design
- `.llm-context/routes.txt` — all API endpoints
- `.llm-context/schemas-extracted.py` — data models
- `.llm-context/symbol-index.json` — where things live (file:line)
- `.llm-context/external-dependencies.json` — service contracts

Never create a symbol without checking symbol-index.json first.
Never add a route without checking routes.txt first.
```

### `.vscode/settings.json`

```json
{
  "github.copilot.chat.codeGeneration.instructions": [
    { "file": "LLM.md" },
    { "file": "ARCHITECTURE.md" },
    { "file": ".llm-context/routes.txt" },
    { "file": ".llm-context/schemas-extracted.py" },
    { "file": ".llm-context/public-api.txt" },
    { "file": ".llm-context/external-dependencies.json" }
  ],
  "github.copilot.chat.testGeneration.instructions": [
    { "file": "LLM.md" },
    { "file": ".llm-context/schemas-extracted.py" },
    { "file": ".llm-context/public-api.txt" }
  ]
}
```

### Using `ccc query` with Copilot Chat

Instead of uploading entire context files, query for what's relevant:

```bash
ccc query --type context "authentication flow" --format markdown
# Copy the output, paste into Copilot Chat before your question
```

---

## LLM.md — Auto-Detected Conventions

Generated from real code analysis, not a static template:

```markdown
## Stack
- Languages: python
- Framework: fastapi, sqlalchemy
- API Style: REST
- Database: SQLAlchemy
- Logging: structlog, stdlib logging

## Critical Conventions

### Error Handling
Exception-based (try/except)

### Testing
- Python: pytest

### Async/Await
Heavy async (~73% of functions)

### Code Quality
- Linters: ruff
- Type checking: mypy

## Dangerous Areas
- `services/payment.py` — Payment processing | Cryptography
- `middleware/auth.py`  — Authentication | Password handling
- `db/migrations/`     — Database migration

## Generated Context
See .llm-context/ for auto-extracted context:
- routes.txt — API routes
- schemas-extracted.py — type definitions
- symbol-index.json — symbol → file:line map
- external-dependencies.json — service boundary contracts
```

---

## CCC and PKML

CCC and PKML serve different purposes and should never be merged:

| | CCC | PKML |
|--|-----|------|
| **Input** | Source code | Human-written descriptions |
| **Output** | `.llm-context/` | `pkml.json` |
| **Answers** | *How does this code work?* | *What is this product supposed to do?* |
| **Updates** | Automated (CI / git hook) | Manual (product team) |
| **Owner** | Engineering | Product / Engineering |

```bash
ccc          # generate .llm-context/ from code
ccc pkml     # bootstrap pkml.json draft from generated artifacts
ccc align    # continuously verify code matches declared product intent
```

The Alignment Engine (`ccc align`) is the only place these two sources combine.
It exits with code 1 when the code diverges from the PKML declaration —
making it suitable as a CI gate.

---

## Incremental Updates

| Strategy | Behaviour | Used for |
|----------|-----------|---------|
| `always` | Regenerate every run | `tree.txt`, `recent-commits.txt` |
| `if-changed` | Only regenerate when source files change | `routes.txt`, `schemas-extracted.*`, etc. |
| `if-missing` | Generate once, never overwrite | `LLM.md`, `ARCHITECTURE.md` |

```bash
ccc --quick-update   # respects if-changed (fast, <2s on most repos)
ccc                  # normal run
ccc --force          # regenerate everything, ignore cache
```

---

## Security Modes

| Mode | Description |
|------|-------------|
| `offline` | No external AI calls. All analysis local. **Default.** Safe for corporate/proprietary code. |
| `private-ai` | Use internal infrastructure (Azure OpenAI, self-hosted models). |
| `public-ai` | Use external providers (Anthropic, OpenAI). Warning shown before sending code. |

Secret redaction is automatic in all modes. API keys, passwords, and tokens are masked.

```yaml
# llm-context.yml
security:
  mode: offline
  redact_secrets: true
  audit_log: true
```

```bash
ccc --security-status    # show current mode and redaction settings
```

---

## Configuration

```yaml
# llm-context.yml — place in project root
output_dir: .llm-context

security:
  mode: offline
  redact_secrets: true
  audit_log: true

exclude_patterns:
  - .git
  - node_modules
  - __pycache__
  - dist

generate:
  tree: true
  schemas: true
  routes: true
  public_api: true
  dependencies: true
  dependency_graph_mermaid: true
  symbol_index: true
  entry_points: true
  db_schema: true
  env_shape: true
  external_dependencies: true
  claude_md_scaffold: true       # generates LLM.md
  architecture_md_scaffold: true # generates ARCHITECTURE.md
  module_summaries: false        # requires [ai] extra

update_strategies:
  tree.txt: always
  schemas-extracted.py: if-changed
  ../LLM.md: if-missing          # never overwrite after manual edits

llm_summaries:
  provider: anthropic            # or: openai
  model: claude-haiku-4-5-20251001
  max_modules: 30
```

---

## Package Structure

```
contextcompiler/
├── llm-context-setup.py       standalone zero-dependency entrypoint
├── ccc/
│   ├── cli.py                 command dispatch (all subcommands)
│   ├── generator.py           orchestrator — parallel artifact generation
│   ├── query.py               runtime query engine (CCCQueryEngine)
│   ├── alignment.py           CCC vs PKML drift detection (AlignmentEngine)
│   ├── file_index.py          FileIndex + HashCache (single scan, shared)
│   ├── manifest.py            SmartUpdater, GenerationManifest
│   ├── config.py              config loading, defaults, merging
│   ├── models.py              shared dataclasses (ProjectInfo, ServiceConfig, etc.)
│   ├── doctor.py              diagnostics
│   ├── watch.py               watch mode
│   ├── extractors/
│   │   ├── python.py          Python AST extraction
│   │   └── typescript.py      TypeScript/JS extraction
│   ├── generators/
│   │   ├── tree.py            directory structure
│   │   ├── api.py             API route extraction
│   │   ├── schemas.py         type/schema extraction
│   │   ├── dependencies.py    dependency graph
│   │   ├── symbols.py         symbol index
│   │   ├── entrypoints.py     entry point detection
│   │   ├── database.py        database schema extraction
│   │   ├── contracts.py       OpenAPI/GraphQL contracts
│   │   ├── external.py        service boundary contracts
│   │   ├── summaries.py       LLM-powered module summaries
│   │   ├── claude_md.py       convention detection → LLM.md
│   │   └── pkml.py            PKML bootstrapper
│   ├── security/
│   │   ├── manager.py         security mode enforcement, secret redaction
│   │   └── modes.py           SecurityMode type
│   ├── utils/
│   │   ├── files.py           safe I/O, path utilities
│   │   ├── formatting.py      timestamps, human-readable sizes
│   │   └── hashing.py         file hashing for incremental updates
│   └── workspace/
│       ├── manifest.py        WorkspaceManifest, dependency ordering
│       ├── query.py           workspace query + context generation
│       ├── conflicts.py       cross-repo conflict detection
│       ├── discover.py        CrossRepoDiscovery — undeclared dep detection
│       ├── init.py            workspace init — directory scanner
│       ├── index.py           service-index.json builder
│       ├── serve.py           browser UI server
│       └── aggregator.py      workspace aggregation utilities
└── tests/
    ├── unit/                  unit tests per module
    ├── integration/           end-to-end tests with fixtures
    └── fixtures/              python-fastapi, typescript-express, multi-repo
```

---

## CI Integration

### Per-repo: keep context always fresh

```yaml
# .github/workflows/ccc-update.yml
name: Update CCC Context
on:
  push:
    branches: [main]
    paths-ignore: ['.llm-context/**']

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.12'}
      - run: pip install ccc-contextcompiler
      - run: ccc
      - name: Commit context
        run: |
          git config user.name "ccc-bot"
          git config user.email "ccc-bot@company.com"
          git add .llm-context/ LLM.md ARCHITECTURE.md
          git diff --staged --quiet || \
            git commit -m "chore: update CCC context [skip ci]" && git push
```

### Alignment gate on PRs

```yaml
- name: Verify code matches PKML documentation
  run: ccc --force && ccc align   # exits 1 on errors, fails the build
```

---

## Testing

```bash
pip install -r tests/requirements.txt
python tests/run_tests.py --verbose
```

CI runs on Python 3.10, 3.11, 3.12 via GitHub Actions on every push.

---

## Contributing

Contributions welcome. Especially valuable:

- Language extractors (Java, Kotlin, Ruby, PHP)
- Framework-specific patterns (NestJS, tRPC, Next.js App Router, Prisma, Django REST)
- Confidence score calibration data for `workspace discover`
- Real-world output examples from production codebases

---

## License

MIT — see LICENSE.

---

## Status

**Functional and actively developed.**

| Feature | Status |
|---------|--------|
| Single-repo generation | ✅ Stable |
| Workspace mode (init/query/generate/conflicts) | ✅ Stable |
| Cross-repo discovery (`workspace discover`) | ✅ Working, confidence scores being calibrated |
| Query engine (`ccc query`) | ✅ Working, lexical today |
| Alignment engine (`ccc align`) | ✅ Working |
| Browser UI (`workspace serve`) | ✅ Working |
| LLM module summaries (`--with-summaries`) | ✅ Working (requires [ai]) |
| Graph-aware impact analysis | ✅ Working (requires `pip install networkx`) |
| Semantic/embedding search | 🔲 Planned (Phase 2) |
| VSCode extension | 🔲 Planned |

The `ccc` package is modular and installable via pip. The standalone
`llm-context-setup.py` remains available as a zero-dependency fallback for
environments where pip install isn't possible.

---

*Built for developers who like structure and precision when working with LLMs in large codebases.*