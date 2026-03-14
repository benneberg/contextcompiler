# CCC — Code Context Compiler

**Generate structured, LLM-optimized project knowledge from codebases and workspaces.**

CCC is a developer tool for extracting high-signal context from repositories and turning it into a reusable knowledge layer for LLMs, onboarding, architecture understanding, and cross-repository change planning.

CCC generates **PKML** — a structured markdown- and JSON-based knowledge format that captures the parts of a codebase that matter most: APIs, schemas, contracts, dependencies, conventions, entry points, architecture, and cross-repo relationships.

---

## Why CCC Exists

Modern codebases are too large, too distributed, and too implicit.

LLMs can help implement, refactor, and explain code — but only if they receive the **right context**. Feeding an entire repository into a model is expensive, noisy, and usually counterproductive.

At the same time, the most valuable engineering knowledge is rarely documented:

- which modules are important
- what conventions a team follows
- where dangerous code lives
- which services depend on which
- in what order changes must land across repositories
- where a new feature should be implemented

CCC exists to make that knowledge **extractable, structured, portable, and reusable**.

---

## What Problem It Solves

CCC is built for three real-world problems:

### 1. LLM Context Compression
Instead of copying large codebases into prompts, CCC produces targeted context files that an LLM can actually use well.

### 2. Repository Understanding
CCC gives developers and AI assistants a compressed understanding of a repository’s structure, APIs, schemas, dependencies, and conventions.

### 3. Multi-Repository Discovery and Coordination
In multi-service systems, CCC helps answer:
- Which repos are involved in this task?
- What needs to change in each one?
- In what order should those changes land?

This is especially important in microservice and platform-heavy organizations where cross-repo knowledge is usually tribal knowledge.

---

## What Is PKML?

**PKML** stands for **Project Knowledge Markdown Language**.

PKML is the structured knowledge format that CCC generates and works with.

It is not a programming language. It is a **portable project knowledge layer** built from markdown and machine-readable companion files.

PKML exists to standardize how repositories describe:

- architecture
- conventions
- boundaries
- dependencies
- schemas
- routes
- symbols
- extension points
- workspace-level relationships

### Why PKML matters

Most repositories have code, but not knowledge.

PKML gives repositories a standard way to expose that knowledge in a format that is:

- readable by humans
- usable by LLMs
- version-controllable
- composable across multiple repositories
- incrementally maintainable

### PKML is designed to be:

- **LLM-friendly** — optimized for prompt context and retrieval
- **human-editable** — important judgment remains editable in markdown
- **machine-generated where possible** — avoid manual drudgery
- **layered** — single-repo and multi-repo knowledge can build on each other
- **non-invasive** — does not require changing your application architecture

### PKML Files

A PKML-enabled repository typically contains:

- `LLM.md` — project-specific conventions and guidance
- `ARCHITECTURE.md` — system-level understanding
- `.llm-context/tree.txt` — file structure
- `.llm-context/routes.txt` — API routes
- `.llm-context/public-api.txt` — exported/public functions
- `.llm-context/schemas-extracted.*` — types and schemas
- `.llm-context/dependency-graph.*` — internal dependency structure
- `.llm-context/symbol-index.json` — symbol navigation
- `.llm-context/entry-points.json` — runtime entry points
- `.llm-context/external-dependencies.json` — repo boundary declaration
- `workspace-context/*` — cross-repo PKML outputs in workspace mode

In other words:

> **CCC is the compiler. PKML is the output format and emerging standard.**

---

## What Is CCC?

CCC is the reference implementation and generator for PKML.

It scans repositories, extracts code intelligence, and builds PKML files automatically.

CCC supports:

- single-repository context generation
- incremental updates
- security-aware operation
- workspace / multi-repository mode
- conflict detection across services
- optional LLM-generated module summaries

---

## Core Concepts

### Single-Repo Mode
CCC analyzes one repository and generates `.llm-context/`, `CLAUDE.md`, and `ARCHITECTURE.md`.

### Workspace Mode
CCC reads multiple PKML-enabled repositories via a `ccc-workspace.yml` manifest and generates cross-repo context and dependency insights.

### Boundary Declarations
Each repository generates an `external-dependencies.json` file describing what it exposes and what it depends on externally. This is the foundation of workspace mode.

### Conflict Detection
CCC can detect cross-repo inconsistencies such as:

- enum mismatches
- type/interface drift
- constant drift
- API route mismatches
- naming inconsistencies

---

## Features

### Single-Repository Features

CCC generates a `.llm-context/` directory with:

- 📁 **File tree** — project structure overview
- 🔷 **Type definitions** — extracted schemas, interfaces, dataclasses
- 🛣️ **API routes** — route map and endpoint overview
- 📝 **Public API** — exported/public function signatures
- 🔗 **Dependency graph** — internal import relationships
- 🗺️ **Symbol index** — symbol navigation by class/function/type
- 🎯 **Entry points** — main files, servers, and executables
- 🗄️ **Database schema** — extracted model/schema information
- 🌐 **External dependencies** — repo boundary contracts
- 📋 **CLAUDE.md** — conventions, gotchas, dangerous areas
- 🏗️ **ARCHITECTURE.md** — architecture scaffold

### Multi-Repository Features

Workspace mode adds:

- service discovery by tags
- dependency ordering
- workspace-level context generation
- cross-repo API mapping
- change sequencing
- dependency graph visualization
- conflict detection across repos

---

## Security Modes

CCC supports three security modes:

### Offline
No external AI APIs. Safe default for proprietary repositories.

### Private-AI
Use internal infrastructure such as Azure OpenAI or self-hosted models.

### Public-AI
Use external providers such as OpenAI or Anthropic.

CCC also supports:

- automatic secret redaction
- audit logging
- exclusion of sensitive files and directories

---

## Installation

## Option 1 — Single File

Download and run:

```bash
curl -O https://raw.githubusercontent.com/benneberg/ccc/main/llm-context-setup.py
python3 llm-context-setup.py --doctor
```

## Option 2 — Add to a Repository

```bash
wget -O llm-context-setup.py https://raw.githubusercontent.com/yourusername/ccc/main/llm-context-setup.py
python3 llm-context-setup.py
```

## Option 3 — Package / Installed CLI (in progress)

The repository is being modularized into the `ccc/` package so it can support an installable CLI in addition to the single-file entrypoint.

Planned command:

```bash
pip install ccc
ccc generate
ccc workspace query --tags core
```

---

## Requirements

### Required
- Python 3.10+

### Optional
```bash
pip install pyyaml       # YAML config and workspace manifests
pip install watchdog     # watch mode
pip install anthropic    # LLM summaries
pip install openai       # LLM summaries
```

---

## Quick Start

### 1. Diagnose the environment

```bash
python3 llm-context-setup.py --doctor
```

### 2. Generate repository context

```bash
python3 llm-context-setup.py
```

### 3. Incrementally update after changes

```bash
python3 llm-context-setup.py --quick-update
```

### 4. Watch for file changes

```bash
python3 llm-context-setup.py --watch
```

---

## Single-Repository Usage

### Generate PKML context for a repository

```bash
python3 llm-context-setup.py
```

### Force regeneration

```bash
python3 llm-context-setup.py --force
```

### Show security configuration

```bash
python3 llm-context-setup.py --security-status
```

### Generate with module summaries

```bash
python3 llm-context-setup.py --with-summaries
```

---

## Output Example

A typical repository will end up with:

```text
your-project/
├── .llm-context/
│   ├── tree.txt
│   ├── schemas-extracted.py
│   ├── types-extracted.ts
│   ├── routes.txt
│   ├── public-api.txt
│   ├── dependency-graph.txt
│   ├── dependency-graph.md
│   ├── symbol-index.json
│   ├── entry-points.json
│   ├── db-schema.txt
│   ├── api-contract.md
│   ├── env-shape.txt
│   ├── recent-commits.txt
│   ├── external-dependencies.json
│   ├── manifest.json
│   └── audit.log
├── LLM.md
├── ARCHITECTURE.md
└── llm-context.yml
```

---

## Multi-Repository Mode

CCC supports multi-repository workspaces via a workspace manifest.

### Workspace Manifest

Create `ccc-workspace.yml`:

```yaml
name: streaming-platform
version: 1

services:
  client:
    path: ./client
    type: frontend
    tags: [platforms, ui, player]

  pairing-service:
    path: ./pairing-service
    type: backend-api
    tags: [platforms, devices, pairing]
    depends_on: [cms-db, auth-service]

  cms-db:
    path: ./cms-db
    type: data
    tags: [platforms, content, schema]

  auth-service:
    path: ./auth-service
    type: backend-api
    tags: [auth, security]
```

### Workspace Commands

List services:

```bash
python3 llm-context-setup.py workspace list
```

Query by tags:

```bash
python3 llm-context-setup.py workspace query --tags platforms
```

Inspect a specific service:

```bash
python3 llm-context-setup.py workspace query --service pairing-service --what all
```

Validate the workspace:

```bash
python3 llm-context-setup.py workspace validate
```

Generate workspace context:

```bash
python3 llm-context-setup.py workspace generate
```

---

## Conflict Detection

Workspace mode can detect cross-repo inconsistencies.

### Detect conflicts

```bash
python3 llm-context-setup.py workspace conflicts
```

### Alias

```bash
python3 llm-context-setup.py workspace doctor
```

### Example detected conflicts

- enum mismatch across services
- type/interface field drift
- constant value mismatch
- route mismatch between provider and consumer
- inconsistent naming conventions

### Generated report

```text
workspace-context/
└── conflicts-report.md
```

---

## Workspace Context Output

Workspace mode generates:

```text
workspace-context/
├── WORKSPACE.md
├── cross-repo-api.txt
├── change-sequence.md
├── dependency-graph.md
└── conflicts-report.md
```

### WORKSPACE.md
High-level description of services and how they connect.

### cross-repo-api.txt
Cross-service API call mapping.

### change-sequence.md
Recommended order of changes derived from dependency relationships.

### dependency-graph.md
Mermaid graph of service relationships.

### conflicts-report.md
Detected inconsistencies across repos.

---

## Why `external-dependencies.json` Matters

Every repository can generate:

```text
.llm-context/external-dependencies.json
```

This file is the boundary declaration for a service.

It tells CCC:

- what this repo exposes
- what APIs it consumes
- which services it depends on
- which databases and queues it uses
- which tags it belongs to

This file is the **bridge** between single-repo PKML and workspace PKML.

---

## TypeScript Support

TypeScript is a first-class target and currently the most heavily optimized language in CCC.

CCC detects:

- exported interfaces and types
- enums and constants
- Express routes
- Next.js route handlers and server actions
- NestJS controllers and event patterns
- tRPC procedures and routers
- GraphQL client usage
- Prisma, TypeORM, Drizzle, Mongoose patterns
- fetch / axios / got / ky requests
- queues and event systems
- WebSocket usage
- third-party SDK integration patterns

Because many modern multi-repo systems are TypeScript-heavy, workspace mode is especially effective there.

---

## Development Status

CCC is currently in an active modularization phase.

### What already exists
- single-file working generator
- incremental updates
- external dependency detection
- workspace query mode
- workspace context generation
- cross-repo conflict detection
- tests and fixtures
- package skeleton (`ccc/`) in progress

### What is currently being built
- modular package architecture
- migration from giant single file to importable package
- cleaner CLI separation
- extractors/generators split into modules

### Planned
- installable CLI package
- richer language extractor plugin model
- improved workspace aggregation
- better conflict intelligence
- optional semantic retrieval
- stronger CI packaging and release process

---

## Project Structure

Current / target structure:

```text
contextcompiler/
├── llm-context-setup.py
├── ccc/
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── manifest.py
│   ├── security/
│   ├── utils/
│   ├── extractors/
│   ├── generators/
│   └── workspace/
├── tests/
├── docs/
└── README.md
```

---

## Example Workflow

### Single repository

```bash
python3 llm-context-setup.py --doctor
python3 llm-context-setup.py
python3 llm-context-setup.py --quick-update
```

### Multi-repository

```bash
python3 llm-context-setup.py workspace validate
python3 llm-context-setup.py workspace query --tags platforms
python3 llm-context-setup.py workspace generate
python3 llm-context-setup.py workspace conflicts
```

---

## Configuration

Create `llm-context.yml`:

```yaml
output_dir: .llm-context

security:
  mode: offline
  redact_secrets: true
  audit_log: true

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
  api_contract: true
  external_dependencies: true
  recent_activity: true
  claude_md_scaffold: true
  architecture_md_scaffold: true
  module_summaries: false

llm_summaries:
  provider: anthropic
  model: claude-sonnet-4-20250514
  max_modules: 30
```

---

## Testing

Install test dependencies:

```bash
pip install -r tests/requirements.txt
```

Run tests:

```bash
python tests/run_tests.py --verbose
```

Integration fixtures currently include:
- Python FastAPI example
- TypeScript Express example
- Multi-repo workspace example

---

## Roadmap

### Near-term
- complete modularization into `ccc/`
- move workspace mode fully into package
- move doctor/watch/generator into package
- split extractors and generators by concern

### Mid-term
- installable CLI
- stronger TypeScript/NestJS/Next.js support
- richer workspace aggregation
- more complete cross-repo sequencing

### Long-term
- PKML as a documented standard
- multiple PKML producers and consumers
- semantic retrieval and local indexing
- editor/IDE integration
- enterprise/private-ai deployment workflows

---

## Contributing

Contributions are welcome.

Especially valuable areas:
- language extractors
- TypeScript framework support
- conflict detection improvements
- PKML documentation
- real-world output examples
- tests for edge cases
- packaging and release automation

---

## Positioning

CCC is not just a repo summarizer.

It is better understood as:

> **a compiler for repository knowledge**

And PKML is the output format that makes that knowledge reusable.

That is the long-term direction:
- repositories become self-describing
- workspaces become navigable
- LLM context becomes structured instead of improvised
- tribal knowledge becomes version-controlled knowledge

---

## License

MIT

---

## Status

Early but serious.

CCC is already useful today in single-repo and workspace mode, and is being actively evolved toward a stable modular architecture and a more explicit PKML standard.

If you are working with LLM-assisted development, multi-repo architecture navigation, or structured developer knowledge, this is exactly the problem space CCC is built for.
