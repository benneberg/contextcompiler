# CCC — Code Context Compiler

> **A deterministic intermediate representation of your codebase, optimized for AI.**

[![CI](https://github.com/benneberg/contextcompiler/actions/workflows/ci.yml/badge.svg)](https://github.com/benneberg/contextcompiler/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/benneberg/contextcompiler/branch/main/graph/badge.svg)](https://codecov.io/gh/benneberg/contextcompiler)
[![PyPI](https://img.shields.io/pypi/v/ccc-contextcompiler.svg)](https://pypi.org/project/ccc-contextcompiler/)
[![Python](https://img.shields.io/pypi/pyversions/ccc-contextcompiler.svg)](https://pypi.org/project/ccc-contextcompiler/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](Dockerfile)

**Status:** Alpha (0.1.x) — core generation is solid; multi-repo UI and some extractors are still evolving.

CCC sits between raw code and LLMs. It scans your repositories and produces structured,
queryable artifacts that give AI tools precise, grounded context — without flooding
the context window with raw source files.

```bash
pip install ccc-contextcompiler
ccc                        # generate context for current directory
ccc inspect src/auth.py    # debug what CCC extracted from a file
ccc context-for "add webm support"  # assemble task-specific context
ccc workspace serve        # open browser UI for multi-repo workspaces
```
---

## The Core Idea

Most AI coding tools try to make LLMs smarter about code. CCC takes the opposite approach:

> **Make code understandable first. Then give it to LLMs.**

Like a compiler, CCC transforms source code into a well-defined intermediate representation (IR).
The `.llm-context/` directory is that IR — deterministic, precise, cacheable, and consumable
by any tool.

```
Code → CCC (IR) → .llm-context/ artifacts
                        ↓
               Query Engine    ← runtime interrogation
               Intent Resolver ← natural language → relevant services
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

Modern codebases are too large, too distributed, and too implicit for LLMs to work with directly.
The most valuable engineering knowledge is rarely in the code itself:

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
| **Call graph tracing** | ✓ | ✗ | Partial | ✗ |
| **Change surface ranking** | ✓ | ✗ | ✗ | ✗ |
| **Cross-repo analysis** | ✓ | ✗ | ✗ | ✗ |
| **Intent → services resolver** | ✓ | ✗ | ✗ | ✗ |
| **Token budget hints** | ✓ | ✗ | ✗ | ✗ |
| **AI feedback loop** | ✓ | ✗ | ✗ | ✗ |
| **Offline / corporate safe** | ✓ | ✓ | ✗ | ✓ |
| **CI-ready, incremental** | ✓ | ✗ | ✗ | ✗ |
| **Zero required deps** | ✓ | ✗ | ✗ | ✓ |

---

## Installation

### Recommended

```bash
pip install ccc-contextcompiler
```

With optional features:

```bash
pip install "ccc-contextcompiler[yaml]"    # YAML workspace manifests (recommended)
pip install "ccc-contextcompiler[watch]"   # watch mode (requires watchdog)
pip install "ccc-contextcompiler[ai]"      # LLM module summaries
pip install "ccc-contextcompiler[live]"    # WebSocket live reload (requires websockets)
pip install "ccc-contextcompiler[all]"     # everything
```

### Development (editable install)

```bash
git clone https://github.com/benneberg/contextcompiler
cd contextcompiler
pip install -e .                           # Linux / Mac
pip install -e . --break-system-packages   # if pip complains on Linux
```

**Requirements:** Python 3.10+. Core generation has zero mandatory dependencies.

---

## Quick Start

### First time — interactive setup

```bash
ccc setup          # auto-detects single repo vs multi-repo, runs full pipeline
```

This replaces the manual init → generate → serve sequence. It detects git repos,
asks a few questions, and produces a working setup.

### Single repository

```bash
ccc                    # generate context for current directory
ccc --quick-update     # fast incremental update after code changes
ccc --force            # ignore cache, regenerate everything
ccc inspect src/auth.py # debug what CCC extracted from a specific file
ccc feedback           # record post-AI-session notes to improve context over time
```

### Multi-repo workspace

```bash
ccc workspace serve                              # browse all services in the UI
ccc workspace query --intent "add webm support"  # find relevant services by task
ccc context-for "add webm support" --budget 8000 # ready-to-paste #file: block
```

After the first run, your project has:

```
your-project/
├── .llm-context/
│   ├── LLM.md                    ← conventions, entry points, known gaps, AI instructions
│   ├── context-manifest.json     ← artifact index with token estimates (read this first)
│   ├── ai-observations.md        ← AI session notes (append after each session)
│   ├── tree.txt                  ← directory structure
│   ├── routes.txt                ← API route map
│   ├── public-api.txt            ← exported function signatures
│   ├── call-graph.json           ← 2-level function call graph
│   ├── change-surface.json       ← files ranked by likelihood of needing edits
│   ├── symbol-index.json         ← symbol → file:line navigation map
│   ├── schemas-extracted.py      ← Python dataclasses, Pydantic models, enums
│   ├── types-extracted.ts        ← TypeScript interfaces, types, enums (with cross-file annotations)
│   ├── type-graph.json           ← TypeScript type cross-reference (defined_in, used_in)
│   ├── external-dependencies.json ← service boundary contracts
│   ├── dependency-graph.txt      ← internal import relationships
│   ├── dependency-graph.md       ← Mermaid dependency diagram
│   ├── capabilities.json         ← semantic capability groups
│   ├── db-schema.txt             ← database models
│   ├── env-shape.txt             ← environment variable template
│   ├── entry-points.json         ← main files, servers, CLI entry points
│   └── manifest.json             ← generation metadata and hash cache
├── LLM.md                        ← architecture overview (if-missing, edit freely)
└── ARCHITECTURE.md               ← architecture scaffold (if-missing, edit freely)
```

---

## All Commands

### Single-Repository

```bash
ccc [path]                    Generate context for a project (default: current dir)
ccc --quick-update  / -q      Incremental — only regenerates changed files
ccc --force         / -f      Ignore cache, regenerate everything
ccc --watch                   Watch mode — auto-update on file save
ccc --with-summaries          Add LLM-powered module summaries (requires [ai])
ccc --quiet                   Suppress all output except warnings and errors
ccc --verbose                 Show debug-level output
ccc --log-file PATH           Write log output to a file
ccc --doctor                  Diagnostics — Python version, project structure, status
ccc --security-status         Show security mode and redaction settings
ccc --version                 Print version
```

### `ccc setup` — Interactive Onboarding

The recommended starting point. Auto-detects whether you're in a single repo or
a multi-repo workspace and runs the correct pipeline.

```bash
ccc setup              # from workspace root or inside any git repo
ccc setup /path/to/ws  # explicit path
```

What it does:
- Detects git repositories in the current directory
- For single repos: runs `ccc` and shows next steps
- For multi-repo: prompts for workspace name, lets you select repos,
  runs `ccc` in each, then `workspace generate`

### `ccc inspect <file>` — Per-File Context Debugger

Shows exactly what CCC extracted from a specific file. Essential for diagnosing
incomplete or incorrect context.

```bash
ccc inspect src/thumbnail/encoder.py
ccc inspect --root /path/to/repo src/auth.py
```

Output sections:
- **File info** — language, size, modified date, binary/excluded status
- **Symbols** — functions and classes extracted (with line numbers)
- **Routes** — HTTP routes registered in this file
- **Imports** — external imports detected
- **Artifact index** — which `.llm-context/` artifacts reference this file and with what symbols

### `ccc context-for <task>` — Task-Scoped Context Assembly

Assembles a token-budget-aware context package for a specific task across a
workspace. Outputs `#file:` blocks ready to paste into Copilot or Claude.

```bash
ccc context-for "add webm support to thumbnail pipeline"
ccc context-for "add webm support" --budget 12000
ccc context-for "add oauth login" --depth 2          # include transitive deps
ccc context-for "refactor auth" --generate            # also write task files
ccc context-for "add webm support" --workspace /path/to/ws
```

Output: a ranked table of matched services with scores and token estimates,
followed by a copyable `#file:` block that stays within the token budget.

`--generate` additionally writes `workspace-context/task-{slug}/`:
- `TASK-CONTEXT.md` — which services, why, implementation order
- `relevant-symbols.txt` — symbols matching the task keywords
- `relevant-routes.txt` — routes matching the task keywords
- `change-sequence.md` — topologically ordered implementation plan

### `ccc feedback` — AI Session Feedback Recorder

Records what worked, what was missing, and what the AI had to guess after
an AI-assisted coding session. Builds up signal in `feedback-log.jsonl`
that helps improve context over time.

```bash
ccc feedback                      # interactive prompts (~2 min)
ccc feedback --service auth       # pre-fill service name
ccc feedback --analyze            # summarise patterns across all sessions
```

Saves to:
- `.llm-context/feedback-log.jsonl` — structured entries
- `.llm-context/ai-observations.md` — human-readable session notes

`--analyze` shows sufficiency breakdown, common missing items, most-discussed
services, and files frequently needed but not in LLM.md.

### `ccc query` — Interrogate Artifacts at Runtime

```bash
ccc query TERM                         Search across all artifact types
ccc query --type symbol  TERM          Symbol lookup
ccc query --type route   TERM          Route/endpoint search
ccc query --type impact  TERM          What breaks if this changes?
ccc query --type context TERM          Build an LLM-ready focused context block
ccc query --format json  TERM          Machine-readable output
ccc query --format markdown TERM       Markdown block for Copilot Chat
ccc query --limit 20     TERM          Max results per section
```

### `ccc align` — Detect Drift Between Code and Documentation

```bash
ccc align                              Auto-detect pkml.json, show drift report
ccc align --pkml path/to/pkml.json     Use a specific PKML file
ccc align --format json                Machine-readable output for CI
```

Exit code 1 on errors — suitable as a CI gate.

### `ccc workspace` — Multi-Repository Mode

```bash
# Setup (or use `ccc setup` for the interactive version)
ccc workspace init [path]              Scan directories, generate ccc-workspace.yml

# Daily use
ccc workspace list                     List all services with tags and status
ccc workspace validate                 Check paths exist, detect circular deps
ccc workspace serve                    Open browser UI at http://localhost:7842

# Service query — three modes
ccc workspace query --tags auth core       Find services by tag
ccc workspace query --service auth         Inspect one service
ccc workspace query --intent "add webm"    Natural language → ranked services
ccc workspace query --intent "add webm" --generate   Also write task context files
ccc workspace query --intent "add webm" --depth 2    Include transitive deps

# Context generation
ccc workspace generate                 Build workspace index and context
ccc workspace generate --skip-discover Skip undeclared dependency scan
ccc workspace generate --commit-index  Stage service-index.json for git commit

# Dependency discovery (also runs automatically after workspace generate)
ccc workspace discover                 Find undeclared cross-repo dependencies
ccc workspace discover --min-confidence 0.7

# Conflict detection
ccc workspace conflicts                Detect type conflicts, API mismatches across repos
ccc workspace doctor                   Alias for conflicts

# Browser UI options
ccc workspace serve --port 8080
ccc workspace serve --no-open          Don't auto-open browser
ccc workspace serve --no-rebuild       Skip rebuilding service-index.json
ccc workspace serve --bind 0.0.0.0     Expose on network (use with caution)
ccc workspace serve --token SECRET     Require ?token=SECRET in URL
ccc workspace serve --auto-refresh 30  Poll for changes every 30 seconds
ccc workspace serve --live-reload      WebSocket live reload (instant, requires websockets+watchdog)
```

---

## The Serve UI

`ccc workspace serve` opens a browser UI at `http://localhost:7842` with:

**Sidebar navigation:**
- **Overview** — stats, tag cloud, service list
- **Dependencies** — declared dependency matrix + discover hint
- **Reports** — Coverage Map, Stale Context, Change Impact
- **Task Intent** — natural language task search with "Copy for Copilot" export
- **Find Service** — filter by name
- **Filter by tag** — click tags to filter, `+ save view` to persist
- **Saved Views** — named tag filter sets stored in browser localStorage

**Service detail view:**
- API endpoints, dependencies, types, events
- Context freshness indicator (stale warning if commits are newer than last `ccc` run)
- "Copy for LLM" and "Download JSON" buttons

**Intent query** (the Task Intent input):
- Type a task description — results update as you type
- Scores services by name match, tag match, API endpoint match, description match,
  and tech-hint expansion (e.g. "webm" → media, encoder, codec tags)
- "Copy for Copilot" button emits `#file:` blocks for all matched services

**Report views:**
- **Coverage Map** — tiers services as Full / Partial / Basic / None
- **Stale Context** — shows which services have commits newer than their last `ccc` run
- **Change Impact** — select a service, see direct and transitive dependents + dependencies

---

## Output Files Reference

| File | Contents | Update strategy |
|------|----------|-----------------|
| `context-manifest.json` | Artifact index with token estimates and task guidance | always |
| `call-graph.json` | 2-level function call graph (`calls`, `called_by`) | if-changed |
| `change-surface.json` | Files ranked by edit likelihood (fan-in, recency, pattern density) | if-changed |
| `symbol-index.json` | Symbol → file:line navigation index | if-changed |
| `tree.txt` | Annotated directory structure | always |
| `routes.txt` | API route map | if-changed |
| `public-api.txt` | Exported function signatures | if-changed |
| `schemas-extracted.py` | Python dataclasses, Pydantic models, enums | if-changed |
| `types-extracted.ts` | TypeScript interfaces/types/enums with `// used in:` annotations | if-changed |
| `type-graph.json` | TypeScript cross-file type resolution (`defined_in`, `used_in`) | if-changed |
| `external-dependencies.json` | Service boundary contracts (exposes + consumes) | if-changed |
| `capabilities.json` | Semantic capability groups | if-missing |
| `dependency-graph.txt` | Internal import relationships | if-changed |
| `dependency-graph.md` | Mermaid dependency diagram | if-changed |
| `db-schema.txt` | Database models (SQLAlchemy, Django, Prisma, TypeORM) | if-changed |
| `env-shape.txt` | Environment variable shape | if-changed |
| `entry-points.json` | Main files, servers, CLI entry points | if-changed |
| `ai-observations.md` | AI session notes — **never overwritten**, append freely | if-missing |
| `LLM.md` *(project root)* | Conventions, patterns, known gaps, AI instructions | if-missing |
| `ARCHITECTURE.md` *(project root)* | Architecture description scaffold | if-missing |

`LLM.md.suggested-updates` is written alongside `LLM.md` when drift is detected
(new routes or dependencies not mentioned in the current LLM.md). Delete it once reviewed.

---

## Language Support

| Language | Symbols | Routes | Types | Call Graph | Deps |
|----------|---------|--------|-------|------------|------|
| Python | ✓ AST | ✓ | ✓ | ✓ AST | ✓ |
| TypeScript | ✓ | ✓ | ✓ + cross-file | ✓ regex | ✓ |
| JavaScript | ✓ | ✓ | — | ✓ regex | ✓ |
| Go | ✓ | ✓ gin/fiber/chi/mux | ✓ struct/interface | meta | ✓ go.mod |
| Rust | ✓ pub fn/struct/enum | ✓ actix/axum macros | ✓ | meta | ✓ Cargo.toml |
| C# | ✓ public methods/classes | ✓ ASP.NET + Minimal API | ✓ class/interface/record | meta | ✓ csproj |

"meta" = functions appear in call graph for `called_by` lookups but outgoing calls
are not traced (would require a full language parser).

---

## Multi-Repository Workspace — Full Workflow

### Option A — Interactive (recommended)

```bash
cd ~/company    # directory containing your service repos
ccc setup       # detects multi-repo, walks you through the whole setup
```

### Option B — Manual

**Step 1 — Initialize**

```bash
cd ~/company
ccc workspace init .    # auto-scans, generates ccc-workspace.yml
```

Edit the manifest:

```yaml
# ccc-workspace.yml
name: my-platform
version: 1

services:
  auth-service:
    path: ./auth-service
    type: backend-api
    tags: [auth, security, core]
    description: "JWT authentication and authorization"

  user-service:
    path: ./user-service
    type: backend-api
    tags: [users, core]
    depends_on: [auth-service]
    description: "User profiles and management"

  thumbnail-service:
    path: ./thumbnail-service
    type: backend-api
    tags: [media, thumbnail, encoder]
    depends_on: [user-service]
    description: "Video thumbnail generation and encoding"
```

**Step 2 — Generate context per service**

```bash
cd auth-service      && ccc && cd ..
cd user-service      && ccc && cd ..
cd thumbnail-service && ccc && cd ..
```

**Step 3 — Build workspace index**

```bash
ccc workspace generate
# Also runs workspace discover automatically — prints undeclared dep summary
```

**Step 4 — Browse and query**

```bash
ccc workspace serve                                  # UI at localhost:7842
ccc workspace query --intent "add webm support"      # CLI intent search
ccc context-for "add webm support" --budget 8000     # ready-to-paste context
```

### Sharing the workspace index

Commit `workspace-context/service-index.json` so teammates can browse the UI
without cloning all service repos:

```bash
ccc workspace generate --commit-index   # stages the file for you
git commit -m "chore: update workspace index"
```

Then any teammate with just the workspace repo can run `ccc workspace serve`.

---

## Using with GitHub Copilot

### `.github/copilot-instructions.md`

```markdown
# Copilot Instructions

Before suggesting any change, review:
- `LLM.md` — conventions, patterns, known gaps, dangerous areas
- `.llm-context/context-manifest.json` — what artifacts exist and their token costs
- `.llm-context/routes.txt` — all API endpoints
- `.llm-context/schemas-extracted.py` — data models
- `.llm-context/symbol-index.json` — where things live (file:line)
- `.llm-context/call-graph.json` — how functions call each other
- `.llm-context/change-surface.json` — which files most likely need editing

Never create a symbol without checking symbol-index.json first.
Never add a route without checking routes.txt first.
After completing a task, append a note to .llm-context/ai-observations.md.
```

### `.vscode/settings.json`

```json
{
  "github.copilot.chat.codeGeneration.instructions": [
    { "file": "LLM.md" },
    { "file": ".llm-context/routes.txt" },
    { "file": ".llm-context/schemas-extracted.py" },
    { "file": ".llm-context/public-api.txt" },
    { "file": ".llm-context/external-dependencies.json" }
  ]
}
```

### Task-based workflow with Copilot Agent

```bash
# 1. Find which services are relevant
ccc context-for "add webm thumbnail support" --budget 8000

# 2. Copy the output #file: block into Copilot Chat, then ask your question

# 3. After the session, record what worked
ccc feedback --service thumbnail-service
```

The `context-for` output looks like:
```
#file:thumbnail-service/.llm-context/LLM.md
#file:media-storage/.llm-context/LLM.md
#file:shared-types/.llm-context/LLM.md

Task: add webm thumbnail support
```

---

## LLM.md — What Gets Generated

Auto-detected from source analysis. Contains:

- **Stack** — languages, frameworks, API style, database, logging
- **Entry Points** — main files, server startup
- **Critical Conventions** — error handling, async patterns, testing framework
- **Dangerous Areas** — files with payment processing, auth, crypto, migrations
- **Common Gotchas** — TODOs for you to fill in about race conditions, ordering
- **Known Gaps** — auto-populated from source TODOs/FIXMEs and `ccc align` output
- **Generated Context** — list of `.llm-context/` artifacts with guidance
- **For the AI Assistant** — template for appending session notes to `ai-observations.md`

`LLM.md` uses the `if-missing` strategy — it is never overwritten after first generation.
Edit it freely. Run `ccc` to get a `LLM.md.suggested-updates` file when new routes or
dependencies are detected that aren't mentioned in the current version.

---

## AI Feedback Loop

CCC has a lightweight feedback system for improving context quality over time.

**During a session:** The `LLM.md` scaffold instructs AI assistants to append
notes to `.llm-context/ai-observations.md` after completing a task.

**After a session:** Run `ccc feedback` to record structured notes interactively.

**Over time:** Run `ccc feedback --analyze` to see patterns — which services
generate the most incomplete context, what's most often missing, which files
the AI needed that weren't referenced in LLM.md.

Both `ai-observations.md` and `feedback-log.jsonl` are never overwritten by `ccc`.
They belong to you and accumulate indefinitely.

---

## Incremental Updates

| Strategy | Behaviour | Used for |
|----------|-----------|---------:|
| `always` | Regenerate every run | `tree.txt`, `recent-commits.txt`, `context-manifest.json` |
| `if-changed` | Only when source files change | most artifacts |
| `if-missing` | Generate once, never overwrite | `LLM.md`, `ARCHITECTURE.md`, `ai-observations.md` |

```bash
ccc --quick-update   # respects if-changed, very fast on large repos
ccc                  # normal run
ccc --force          # ignore cache, regenerate everything
```

---

## Security

| Mode | Description |
|------|-------------|
| `offline` | No external calls. All analysis local. **Default.** Safe for corporate code. |
| `private-ai` | Use internal AI infrastructure (Azure OpenAI, self-hosted). |
| `public-ai` | Use external providers. Warning shown before sending code. |

Secret redaction patterns (applied automatically in all modes):
- Environment variable assignments: `API_KEY=`, `PASSWORD=`, `SECRET=`, `TOKEN=`
- HTTP auth headers: `Bearer ...`, `Basic ...`
- PEM private key blocks
- Connection strings: `postgresql://user:pass@host`, `amqp://...`
- AWS-style access keys: `AKIA...`
- JSON-embedded secrets: `"password": "value"`

Audit logging appends to `.llm-context/audit.log` in JSON Lines format.
The file rotates at 5MB, keeping the last 10,000 entries.

```bash
ccc --security-status    # show current mode and settings
```

```yaml
# llm-context.yml
security:
  mode: offline          # offline | private-ai | public-ai
  redact_secrets: true
  audit_log: true
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
  - .llm-context

generate:
  tree: true
  schemas: true
  routes: true
  public_api: true
  dependencies: true
  symbol_index: true
  call_graph: true         # 2-level function call graph
  change_surface: true     # file relevance ranking
  entry_points: true
  db_schema: true
  env_shape: true
  external_dependencies: true
  capabilities: true
  claude_md_scaffold: true       # generates LLM.md
  architecture_md_scaffold: true # generates ARCHITECTURE.md
  module_summaries: false        # requires [ai] extra
```

---

## Package Structure

```
contextcompiler/
├── llm-context-setup.py           standalone zero-dependency entrypoint
├── ccc/
│   ├── cli.py                     command dispatch (all subcommands)
│   ├── generator.py               orchestrator — parallel artifact generation
│   ├── setup_wizard.py            ccc setup — interactive onboarding
│   ├── inspect_cmd.py             ccc inspect — per-file context debugger
│   ├── task_context.py            ccc context-for — task context assembly
│   ├── feedback.py                ccc feedback — AI session recorder
│   ├── query.py                   runtime query engine (CCCQueryEngine)
│   ├── alignment.py               CCC vs PKML drift detection
│   ├── file_index.py              FileIndex + HashCache (single scan, shared)
│   ├── manifest.py                SmartUpdater, GenerationManifest
│   ├── config.py                  config loading, defaults, merging
│   ├── models.py                  shared dataclasses
│   ├── doctor.py                  diagnostics
│   ├── watch.py                   watch mode
│   ├── extractors/
│   │   ├── base.py                BaseExtractor, ExtractionResult, ExtractedSymbol
│   │   ├── python.py              Python AST extraction
│   │   ├── typescript.py          TypeScript/JS extraction
│   │   ├── go.py                  Go extraction (funcs, structs, gin/fiber routes, go.mod)
│   │   ├── rust.py                Rust extraction (pub fn, actix/axum macros, Cargo.toml)
│   │   └── csharp.py              C# extraction (methods, ASP.NET/Minimal API, csproj)
│   ├── generators/
│   │   ├── api.py                 API route extraction (Python, TS, Go, Rust, C#)
│   │   ├── callgraph.py           2-level function call graph
│   │   ├── changesurface.py       change surface ranking
│   │   ├── capabilities.py        semantic capability groups
│   │   ├── claude_md.py           convention detection → LLM.md (with Known Gaps)
│   │   ├── contracts.py           OpenAPI/GraphQL contracts
│   │   ├── database.py            database schema extraction
│   │   ├── dependencies.py        dependency graph
│   │   ├── entrypoints.py         entry point detection
│   │   ├── external.py            service boundary contracts
│   │   ├── schemas.py             type/schema extraction + type-graph.json
│   │   ├── summaries.py           LLM-powered module summaries
│   │   ├── symbols.py             symbol index (Python, TS, Go, Rust, C#)
│   │   └── tree.py                directory structure
│   ├── security/
│   │   └── manager.py             security mode, secret redaction, audit log
│   ├── utils/
│   │   ├── files.py               safe I/O, path utilities
│   │   ├── formatting.py          timestamps, human-readable sizes
│   │   ├── hashing.py             file hashing for incremental updates
│   │   └── logging.py             structured logging, --quiet/--verbose/--log-file
│   └── workspace/
│       ├── index.py               service-index.json builder (with last_commit timestamps)
│       ├── manifest.py            WorkspaceManifest, dependency ordering
│       ├── query.py               workspace query + context generation
│       ├── conflicts.py           cross-repo conflict detection
│       ├── discover.py            CrossRepoDiscovery — undeclared dep detection
│       ├── init.py                workspace init — directory scanner
│       └── serve.py               browser UI server + WebSocket live reload
└── tests/
    ├── unit/
    │   ├── test_extractors.py     Go, Rust, C# extractor unit tests (42 tests)
    │   └── test_generators.py     TypeScript type resolution unit tests
    ├── integration/               end-to-end tests with real fixture projects
    └── fixtures/                  python-fastapi, typescript-express, multi-repo
```

---

## CI Integration

### Keep context always fresh

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
pip install -e ".[dev]"        # or: pip install pytest
python -m pytest tests/ -q     # run all 91 tests
python -m pytest tests/unit/   # unit tests only
python -m pytest tests/integration/  # integration tests only
```

Tests run on Python 3.10, 3.11, 3.12 via GitHub Actions on every push.

Current test count: **91 passing** (40 integration + 42 unit extractor + 9 unit generator).

---

## Status

**Actively developed.**

| Feature | Status |
|---------|--------|
| Single-repo generation | ✅ Stable |
| Workspace mode (init/query/generate/discover/conflicts) | ✅ Stable |
| Interactive setup (`ccc setup`) | ✅ Working |
| Per-file debugger (`ccc inspect`) | ✅ Working |
| Task context assembly (`ccc context-for`) | ✅ Working |
| AI feedback loop (`ccc feedback`) | ✅ Working |
| Intent-based service resolution | ✅ Working (UI + CLI) |
| Browser UI with report views | ✅ Working |
| WebSocket live reload (`--live-reload`) | ✅ Working |
| Saved views in UI (localStorage) | ✅ Working |
| Call graph generation | ✅ Working |
| Change surface ranking | ✅ Working |
| TypeScript cross-file type resolution | ✅ Working |
| LLM.md drift detection | ✅ Working |
| Known Gaps in LLM.md | ✅ Working |
| Python extraction | ✅ Stable (AST-based) |
| TypeScript/JS extraction | ✅ Stable |
| Go extraction | ✅ Working |
| Rust extraction | ✅ Working |
| C# extraction | ✅ Working |
| Java extraction | 🔲 Planned |
| Query engine (`ccc query`) | ✅ Working (lexical) |
| Semantic/embedding search | 🔲 Planned (Phase 2) |
| Alignment engine (`ccc align`) | ✅ Working |
| LLM module summaries (`--with-summaries`) | ✅ Working (requires [ai]) |
| VSCode extension | 🔲 Planned |
| MCP server | 🔲 Planned |
| GitHub Actions integration | 🔲 Planned |

---

*Built for developers who like structure and precision when working with LLMs in large codebases.*
