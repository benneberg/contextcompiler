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
               Query Engine    ← runtime access
               Graph Analysis  ← impact reasoning
               Alignment       ← intent vs reality
                        ↓
               LLMs / Copilot / CI / Tools
```

**CCC = Reality** (what exists, extracted from code)
**PKML = Intent** (what should exist, declared by humans)
The Alignment Engine combines them.

---

## Why It Exists

Modern codebases are too large, too distributed, and too implicit for LLMs to work with directly.
The most valuable engineering knowledge is rarely documented:

- Which modules are critical and why
- What conventions the team actually follows
- Where dangerous code lives
- Which services depend on which, and in what order changes must land
- What the code is *supposed* to do versus what it actually does

CCC makes that knowledge **extractable, structured, portable, and reusable**.

---

## Installation

### Package install (recommended)

```bash
pip install ccc-contextcompiler
```

With optional features:

```bash
pip install "ccc-contextcompiler[yaml]"    # YAML workspace manifests
pip install "ccc-contextcompiler[watch]"   # watch mode (requires watchdog)
pip install "ccc-contextcompiler[ai]"      # LLM module summaries
pip install "ccc-contextcompiler[all]"     # everything
```

### Editable install from source (for development)

```bash
git clone https://github.com/benneberg/contextcompiler
cd contextcompiler
pip install -e .                          # Linux / Mac
pip install -e . --break-system-packages  # if pip complains
```

On Windows, if you get a setuptools error:
```bash
python -m pip install --upgrade pip setuptools wheel
pip install -e .
```

### Standalone script (zero dependencies)

```bash
curl -O https://raw.githubusercontent.com/benneberg/contextcompiler/main/llm-context-setup.py
python3 llm-context-setup.py
```

**Requirements:** Python 3.10+. Core generation has zero mandatory dependencies.

---

## Quick Start

```bash
ccc --doctor           # check your environment
ccc                    # generate context for current directory
ccc --quick-update     # fast incremental update (skips unchanged files)
ccc --force            # full regeneration, ignore cache
ccc --watch            # auto-update on file changes
```

After running, you get:

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
│   └── manifest.json                generation metadata
├── LLM.md                           auto-detected conventions scaffold
└── ARCHITECTURE.md                  architecture description scaffold
```

---

## All Commands

### Single-repository commands

```bash
ccc [path]                    Generate context for a project
                              Default: current directory

ccc --quick-update / -q       Incremental update — only regenerates changed files
ccc --force / -f              Ignore cache, regenerate everything
ccc --watch                   Watch mode — auto-update on file save
ccc --with-summaries          Add LLM-powered module summaries (requires [ai])
ccc --doctor                  Diagnostics — Python version, project structure,
                              context status, security config
ccc --security-status         Show current security mode and redaction settings
ccc --output DIR / -o DIR     Write context to a custom directory
ccc --config FILE / -c FILE   Use a custom llm-context.yml or .json config
ccc --version / -v            Print version
```

### Query — interrogate artifacts at runtime

```bash
ccc query TERM                      Search across all artifact types
ccc query --type symbol TERM        Symbol lookup (classes, functions, types)
ccc query --type route TERM         Route/endpoint search
ccc query --type impact TERM        What breaks if this changes?
ccc query --type context TERM       Build an LLM-ready focused context block
ccc query --type api TERM           Search function signatures
ccc query --format json TERM        Machine-readable output
ccc query --format compact TERM     Minimal token output for prompts
ccc query --limit 20 TERM           Control result count (default: 10)
ccc query --context-dir DIR TERM    Point at a non-default .llm-context/
```

Examples:
```bash
ccc query "UserService"                     # find everything named UserService
ccc query --type symbol CreateUserRequest   # exact symbol location
ccc query --type route /users               # find routes matching /users
ccc query --type impact UserModel           # what depends on UserModel?
ccc query --type context "authentication"   # LLM-ready context block
ccc query --format json "platform"          # pipe to other tools
```

### Align — detect drift between code and product documentation

```bash
ccc align                             Compare code against auto-detected pkml.json
ccc align --pkml path/to/pkml.json    Use a specific PKML file
ccc align --format json               Machine-readable output (for CI)
ccc align --context-dir DIR           Point at a non-default .llm-context/
```

Exit codes: `0` = clean, `1` = errors found. Use in CI to gate on drift.

### PKML — bootstrap product knowledge from code

```bash
ccc pkml                          Generate pkml.json from .llm-context/ files
ccc pkml --output DIR             Custom output directory
ccc pkml --open                   Open PKML editor in browser after generating
```

Requires `.llm-context/` to exist first (run `ccc` before `ccc pkml`).

### Workspace — multi-repository mode

```bash
ccc workspace init [path]               Scan directories, generate ccc-workspace.yml
ccc workspace init --name my-platform   Set workspace name
ccc workspace init --force              Overwrite existing manifest

ccc workspace list                      List all services in workspace
ccc workspace validate                  Check paths, detect circular deps

ccc workspace query --tags core         Find services by tag, show change sequence
ccc workspace query --tags auth users   Multiple tags (OR logic)
ccc workspace query --service NAME      Inspect a specific service
ccc workspace query --service NAME --what depends-on
ccc workspace query --service NAME --what dependents
ccc workspace query --service NAME --what external
ccc workspace query --service NAME --what all
ccc workspace query --tags TAG --generate  Also generate workspace context

ccc workspace generate                  Build cross-repo context
ccc workspace generate --tags TAG       Filter to specific services

ccc workspace discover                  Find undeclared cross-repo dependencies
ccc workspace discover --tags TAG       Filter to specific services
ccc workspace discover --min-confidence 0.7  Stricter confidence threshold

ccc workspace conflicts                 Detect type conflicts, API mismatches
ccc workspace conflicts --tags TAG
ccc workspace conflicts --output DIR

ccc workspace doctor                    Alias for conflicts

ccc workspace serve                     Launch browser UI (localhost:7842)
ccc workspace serve --port 8080         Custom port
ccc workspace serve --no-open           Don't auto-open browser
ccc workspace serve --no-rebuild        Skip rebuilding service-index.json
```

---

## Output Files Reference

| File | Contents |
|------|----------|
| `tree.txt` | Annotated directory structure |
| `routes.txt` | API route map (FastAPI, Flask, Express, NestJS) |
| `public-api.txt` | Exported function signatures |
| `schemas-extracted.py` | Python dataclasses, Pydantic models, enums |
| `types-extracted.ts` | TypeScript interfaces, types, enums |
| `dependency-graph.txt` | Internal import relationships |
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

## Multi-Repository Workspace Mode

### Step 1 — Initialize

```bash
cd ~/company          # directory containing your service repos
ccc workspace init .  # auto-scans, generates ccc-workspace.yml draft
```

Edit the generated manifest to fill in descriptions and correct `depends_on`:

```yaml
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

  client:
    path: ./client
    type: frontend
    tags: [ui, platforms]
    depends_on: [user-service]
```

### Step 2 — Generate per-service context

```bash
cd auth-service && ccc && cd ..
cd user-service && ccc && cd ..
cd client       && ccc && cd ..
```

### Step 3 — Build workspace context

```bash
ccc workspace generate
```

### Step 4 — Discover undeclared dependencies

```bash
ccc workspace discover
```

Analyzes `.llm-context/` artifacts and surfaces hidden coupling. Four detection methods:

| Method | What It Finds | Confidence |
|--------|--------------|------------|
| API route matching | Service A calls routes that Service B exposes | 75–95% |
| Schema cross-reference | Same type defined differently in two services | 50–85% |
| Shared infrastructure | Services sharing the same database, cache, or queue | 45–70% |
| Event coupling | Event emitted by one service consumed by another | 88% |

### Step 5 — Open the browser UI

```bash
ccc workspace serve    # opens http://localhost:7842
```

Share with the whole team. No coding required. Features tag filtering, service
detail view, dependency graph, change sequence, copy-as-Markdown, download-as-JSON.

---

## Query Engine

Interrogate `.llm-context/` at runtime instead of reading files manually.

```bash
ccc query "user"                           # search all artifact types
ccc query --type symbol CreateUserRequest  # exact file:line location
ccc query --type route /api/users          # route search
ccc query --type impact UserModel          # what breaks if this changes?
ccc query --type context "auth flow"       # LLM-ready context block
```

### Python API

```python
from ccc.query import CCCQueryEngine

engine = CCCQueryEngine(".llm-context")

# Unified search
result = engine.query("user")
# result.symbols, result.routes, result.public_api, result.schemas

# Exact lookup
sym = engine.find_symbol("CreateUserRequest")
# sym.file, sym.line, sym.kind

# Impact analysis
impact = engine.find_impact("UserModel")
# impact["direct_dependents"], impact["transitive_dependents"]

# LLM context builder — paste directly into prompts
context = engine.build_llm_context("authentication", format="markdown")
```

Install `networkx` for graph-aware transitive impact analysis:
```bash
pip install networkx
```

---

## Alignment Engine

Compares what the code does (CCC) against what the product docs say it should do (PKML).

```bash
ccc align              # auto-detect pkml.json, show drift report
ccc align --format json  # for CI integration
```

```
  ✓  Confirmed: GET /api/users, POST /api/users, DELETE /api/users/{id}

  ✗  Missing implementation:
     POST /api/auth/reset-password — in PKML but not in code

  ⚠  Undocumented:
     DELETE /internal/purge-cache — in code but not in PKML
```

Use in CI:
```yaml
- run: ccc --force && ccc align   # exits 1 if errors, fails the build
```

---

## LLM.md — Auto-Detected Conventions

Generated with real detected conventions, not a static template:

```markdown
## Stack
- Languages: python, typescript
- Framework: fastapi, sqlalchemy
- API Style: REST
- Database: SQLAlchemy
- Logging: structlog

## Critical Conventions

### Error Handling
Exception-based (try/except)

### Testing
- Python: pytest
- JavaScript: jest

### Async/Await
Heavy async (~73% of functions)

### Code Quality
- Linters: ruff, eslint
- Type checking: mypy, tsc

## Dangerous Areas
- `services/payment.py` — Payment processing | Cryptography
- `middleware/auth.py`  — Authentication | Password handling
```

---

## GitHub Copilot Integration

### `.github/copilot-instructions.md`

```markdown
# Copilot Instructions

Before suggesting changes, review:
- `LLM.md` — conventions and dangerous areas
- `ARCHITECTURE.md` — system design
- `.llm-context/routes.txt` — all API endpoints
- `.llm-context/schemas-extracted.py` — data models
- `.llm-context/symbol-index.json` — where to find things

Never create a symbol without checking symbol-index.json first.
```

### `.vscode/settings.json`

```json
{
  "github.copilot.chat.codeGeneration.instructions": [
    { "file": "LLM.md" },
    { "file": "ARCHITECTURE.md" },
    { "file": ".llm-context/routes.txt" },
    { "file": ".llm-context/schemas-extracted.py" },
    { "file": ".llm-context/external-dependencies.json" }
  ]
}
```

### Git hook

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

## Incremental Updates

| Strategy | Behaviour |
|----------|-----------|
| `always` | Regenerate every run (tree, recent-commits) |
| `if-changed` | Regenerate only when source files change |
| `if-missing` | Generate once, never overwrite (LLM.md, ARCHITECTURE.md) |

```bash
ccc --quick-update   # fast, respects if-changed
ccc                  # normal run
ccc --force          # regenerate everything
```

---

## Security Modes

| Mode | Description |
|------|-------------|
| `offline` | No external AI calls. Safe for proprietary code. Default. |
| `private-ai` | Use internal infrastructure (Azure OpenAI, self-hosted). |
| `public-ai` | Use external providers (Anthropic, OpenAI). |

```yaml
# llm-context.yml
security:
  mode: offline
  redact_secrets: true
  audit_log: true
```

Secret redaction is automatic. Sensitive files are excluded automatically.

---

## Configuration

```yaml
# llm-context.yml
output_dir: .llm-context

security:
  mode: offline
  redact_secrets: true

generate:
  tree: true
  schemas: true
  routes: true
  public_api: true
  dependencies: true
  symbol_index: true
  env_shape: true
  external_dependencies: true
  claude_md_scaffold: true
  architecture_md_scaffold: true
  module_summaries: false      # requires [ai]

llm_summaries:
  provider: anthropic
  model: claude-haiku-4-5-20251001
  max_modules: 30
```

---

## CCC and PKML

| | CCC | PKML |
|--|-----|------|
| **Input** | Source code | Human-written descriptions |
| **Output** | `.llm-context/` | `pkml.json` |
| **Answers** | *How does this code work?* | *What does this product do?* |
| **Updates** | Automated | Manual |

```bash
ccc          # generate .llm-context/
ccc pkml     # bootstrap pkml.json draft from artifacts
ccc align    # continuously verify code matches declared intent
```

---

## Package Structure

```
contextcompiler/
├── llm-context-setup.py      standalone zero-dependency entrypoint
├── ccc/
│   ├── cli.py                command dispatch
│   ├── generator.py          orchestrator (parallel generation)
│   ├── query.py              runtime query engine
│   ├── alignment.py          CCC vs PKML drift detection
│   ├── file_index.py         FileIndex + HashCache
│   ├── extractors/           Python, TypeScript AST extractors
│   ├── generators/           tree, schemas, api, deps, symbols,
│   │                         database, contracts, external, summaries,
│   │                         claude_md, pkml
│   ├── security/             modes + secret redaction
│   ├── utils/                files, formatting, hashing
│   └── workspace/            manifest, query, conflicts, discover,
│                             init, index, serve
└── tests/                    unit, integration, fixtures
```

---

## Testing

```bash
pip install -r tests/requirements.txt
python tests/run_tests.py --verbose
```

CI runs on Python 3.10, 3.11, 3.12 via GitHub Actions.

---

## Contributing

Contributions welcome. Especially valuable:

- Language extractors (Java, Kotlin, Ruby, PHP)
- TypeScript framework patterns (NestJS, tRPC, Next.js App Router, Prisma)
- Confidence score calibration data for `workspace discover`
- Real-world output examples from production codebases

---

## License

MIT — see LICENSE.

---

## Status

**Functional and actively developed.**

Single-repo generation, workspace mode (init/query/generate/discover/serve),
query engine, and alignment engine all work today. The `ccc` package is modular
and installable. The standalone `llm-context-setup.py` remains available as a
zero-dependency fallback.