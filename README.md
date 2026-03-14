# CCC — Code Context Compiler

**Turn any codebase into structured, LLM-ready knowledge.**

CCC scans your repositories and generates a `.llm-context/` directory containing everything an LLM needs to understand and work with your code — without flooding the context window with raw source.

```bash
pip install ccc-contextcompiler
ccc generate
```

-----

## Why CCC Exists

Modern codebases are too large, too distributed, and too implicit for LLMs to work with directly.

The most valuable engineering knowledge is rarely documented:

- which modules are important
- what conventions the team follows
- where dangerous code lives
- which services depend on which
- in what order changes must land across repositories

CCC makes that knowledge **extractable, structured, portable, and reusable**.

-----

## How It Works

CCC builds a single file index from one scan of your repository, then runs all generators in parallel to produce structured context files:

```
your-project/
├── .llm-context/
│   ├── tree.txt                    # directory structure
│   ├── routes.txt                  # API route map
│   ├── public-api.txt              # exported function signatures
│   ├── schemas-extracted.py        # dataclasses, Pydantic models, enums
│   ├── types-extracted.ts          # TypeScript interfaces, types, enums
│   ├── dependency-graph.txt        # internal import relationships
│   ├── dependency-graph.md         # same as Mermaid diagram
│   ├── symbol-index.json           # symbol → file:line navigation map
│   ├── external-dependencies.json  # what this service exposes and consumes
│   ├── env-shape.txt               # environment variable template
│   ├── recent-commits.txt          # last 20 commits
│   ├── manifest.json               # generation metadata for incremental updates
│   └── .ccc-hashcache.json         # mtime-gated hash cache
├── LLM.md                          # conventions scaffold (if-missing)
└── ARCHITECTURE.md                 # architecture scaffold (if-missing)
```

-----

## Installation

### Option 1 — Install as a package (recommended)

```bash
pip install ccc-contextcompiler
ccc generate
```

With optional dependencies:

```bash
pip install "ccc-contextcompiler[yaml]"    # YAML config + workspace manifests
pip install "ccc-contextcompiler[watch]"   # watch mode
pip install "ccc-contextcompiler[ai]"      # LLM-powered module summaries
pip install "ccc-contextcompiler[all]"     # everything
```

### Option 2 — Run the standalone script

```bash
curl -O https://raw.githubusercontent.com/benneberg/contextcompiler/main/llm-context-setup.py
python3 llm-context-setup.py
```

### Option 3 — Editable install from source

```bash
git clone https://github.com/benneberg/contextcompiler
cd contextcompiler
pip install -e .
ccc generate
```

**Requirements:** Python 3.10+. No mandatory dependencies — core generation works with zero installs.

-----

## Quick Start

```bash
# Check your environment
ccc --doctor

# Generate context for the current directory
ccc generate

# Fast incremental update (skips unchanged files)
ccc --quick-update

# Force full regeneration
ccc --force

# Watch for file changes and auto-update
ccc --watch
```

-----

## Single-Repository Usage

```bash
# Generate context for a specific path
ccc generate /path/to/project

# Generate with AI-powered module summaries
ccc --with-summaries

# Show security configuration
ccc --security-status

# Custom output directory
ccc --output .context
```

-----

## Output Files

|File                        |Contents                                        |
|----------------------------|------------------------------------------------|
|`tree.txt`                  |Annotated directory structure                   |
|`routes.txt`                |API route map (FastAPI, Flask, Express, NestJS) |
|`public-api.txt`            |Exported function signatures                    |
|`schemas-extracted.py`      |Python dataclasses, Pydantic models, enums      |
|`types-extracted.ts`        |TypeScript interfaces, types, enums             |
|`dependency-graph.txt`      |Internal import relationships                   |
|`dependency-graph.md`       |Mermaid dependency diagram                      |
|`symbol-index.json`         |Symbol → file:line navigation index             |
|`external-dependencies.json`|Service boundary contracts                      |
|`env-shape.txt`             |Environment variable shape (from `.env.example`)|
|`recent-commits.txt`        |Last 20 git commits                             |
|`LLM.md`                    |Conventions and gotchas scaffold                |
|`ARCHITECTURE.md`           |Architecture description scaffold               |

-----

## Language Support

|Language  |Schemas|Routes|Signatures|Deps|
|----------|-------|------|----------|----|
|Python    |✓      |✓     |✓         |✓   |
|TypeScript|✓      |✓     |✓         |✓   |
|JavaScript|—      |✓     |—         |✓   |
|Rust      |✓      |—     |—         |—   |
|Go        |✓      |—     |—         |—   |
|C#        |✓      |—     |—         |—   |

-----

## Multi-Repository (Workspace) Mode

CCC can coordinate across multiple services using a workspace manifest.

### Create `ccc-workspace.yml`

```yaml
name: my-platform
version: 1

services:
  auth-service:
    path: ./auth-service
    type: backend-api
    tags: [auth, security, core]

  user-service:
    path: ./user-service
    type: backend-api
    tags: [users, core]
    depends_on: [auth-service]

  api-gateway:
    path: ./api-gateway
    type: backend-api
    tags: [gateway, core]
    depends_on: [auth-service, user-service]
```

### Workspace Commands

```bash
# List all services
ccc workspace list

# Query by tags
ccc workspace query --tags core

# Inspect a specific service and its dependencies
ccc workspace query --service auth-service --what all

# Validate paths and dependency declarations
ccc workspace validate

# Generate cross-repo context (WORKSPACE.md, change-sequence.md, etc.)
ccc workspace generate

# Detect conflicts across services
ccc workspace conflicts

# Alias for conflicts
ccc workspace doctor
```

### Workspace Output

```
workspace-context/
├── WORKSPACE.md          # service map and connection overview
├── cross-repo-api.txt    # cross-service API call map
├── change-sequence.md    # dependency-ordered change plan
├── dependency-graph.md   # Mermaid graph of service relationships
└── conflicts-report.md   # detected inconsistencies
```

-----

## Conflict Detection

`ccc workspace conflicts` scans all services and reports:

|Conflict Type       |Severity|Example                                                    |
|--------------------|--------|-----------------------------------------------------------|
|Enum mismatch       |Error   |`UserStatus` has different values in two services          |
|Interface drift     |Warning |`UserProfile` has different fields across services         |
|Constant mismatch   |Warning |`MAX_RETRY` is `3` in one service and `5` in another       |
|API route mismatch  |Warning |Service calls `/users/:id` but provider exposes `/user/:id`|
|Event naming        |Info    |Mix of `user.created` and `userCreated` event names        |
|Naming inconsistency|Info    |`UserId` vs `userId` vs `user_id` across services          |

-----

## Symbol Index

`symbol-index.json` provides a flat navigation map for LLMs and tooling:

```json
{
  "_meta": {
    "generated": "2025-03-14 10:00 UTC",
    "total_symbols": 342
  },
  "symbols": {
    "UserService.create_user": { "file": "services/user.py", "line": 42, "kind": "method" },
    "AuthMiddleware":          { "file": "middleware/auth.py", "line": 10, "kind": "class" },
    "POST /api/users":         { "file": "routes/users.py", "line": 88, "kind": "route" },
    "UserSchema":              { "file": "schemas/user.py", "line": 15, "kind": "class" }
  }
}
```

This lets an LLM resolve `UserService.create_user` to an exact file and line rather than searching through source.

-----

## Incremental Updates

CCC tracks what was generated and skips files that haven’t changed:

```bash
ccc --quick-update   # fastest: skips db_schema and module_summaries
ccc generate         # normal: respects if-changed strategy
ccc --force          # regenerates everything unconditionally
```

Update strategies per file (configurable in `llm-context.yml`):

|Strategy    |Behaviour                                               |
|------------|--------------------------------------------------------|
|`always`    |Regenerate every run (tree, recent-commits)             |
|`if-changed`|Regenerate only when source files change                |
|`if-missing`|Generate once, never overwrite (LLM.md, ARCHITECTURE.md)|

A mtime-gated hash cache (`.ccc-hashcache.json`) makes incremental runs near-instant for large repos.

-----

## Security Modes

```yaml
# llm-context.yml
security:
  mode: offline       # default — no external AI calls
  redact_secrets: true
  audit_log: true
```

|Mode        |Description                                             |
|------------|--------------------------------------------------------|
|`offline`   |No external AI APIs. Safe for proprietary repositories. |
|`private-ai`|Use internal infrastructure (Azure OpenAI, self-hosted).|
|`public-ai` |Use external providers (Anthropic, OpenAI).             |

CCC also automatically redacts secrets and skips sensitive paths (`.env`, `keys/`, `certs/`, etc.).

-----

## Configuration

Create `llm-context.yml` in your project root:

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
  env_shape: true
  recent_activity: true
  external_dependencies: true
  claude_md_scaffold: true
  architecture_md_scaffold: true
  module_summaries: false   # requires AI mode

llm_summaries:
  provider: anthropic
  model: claude-haiku-4-5-20251001
  max_modules: 30
```

-----

## Architecture

CCC is built around four performance principles:

**1. Single filesystem scan**
`FileIndex` walks the repository once at startup. Every generator filters the index instead of re-scanning disk. For a 100k-file repo this reduces scan time from ~20s to ~3s.

**2. Parallel generation**
All independent generators (tree, schemas, routes, API, dependencies, symbols) run concurrently via `ThreadPoolExecutor`. Typical speedup: 4–5×.

**3. Streaming detection**
Framework detection reads files line-by-line and stops on the first match. Never loads entire files into memory.

**4. Mtime-gated hash cache**
`HashCache` skips rehashing files whose mtime hasn’t changed. Incremental runs on large repos become near-instant.

```
LLMContextGenerator
 │
 ├── FileIndex          single scan, shared by all generators
 ├── HashCache          mtime → hash cache for fast incrementals
 ├── ProjectDetector    uses FileIndex, streaming framework detection
 │
 ├── [parallel]
 │   ├── TreeGenerator
 │   ├── SchemaGenerator
 │   ├── APIGenerator
 │   ├── DependencyGenerator
 │   └── SymbolIndexGenerator
 │
 └── [sequential]
     ├── env-shape, dep files, git activity
     ├── ExternalDependencyDetector
     └── LLM.md / ARCHITECTURE.md scaffolds
```

-----

## Relationship to PKML

CCC and [PKML](https://github.com/benneberg/pkml) are complementary tools that form a complete knowledge layer for AI-assisted development:

|            |CCC                        |PKML                                 |
|------------|---------------------------|-------------------------------------|
|**Input**   |Source code                |Human-written product descriptions   |
|**Output**  |`.llm-context/` files      |`pkml.json` product knowledge file   |
|**Answers** |*How does this code work?* |*What does this product do?*         |
|**Audience**|Developers, AI coding tools|Developers, PMs, marketing, AI agents|

**Together:** CCC generates the technical context; PKML captures the product intent. An LLM that has both can understand what a system is *supposed* to do and how it’s actually built.

CCC can bootstrap a `pkml.json` draft from your codebase, which you then refine in the [PKML editor](https://github.com/benneberg/pkml).

-----

## Package Structure

```
contextcompiler/
├── llm-context-setup.py      standalone single-file entrypoint
├── pyproject.toml            package definition and CLI registration
├── ccc/
│   ├── cli.py                argument parsing and command dispatch
│   ├── generator.py          main orchestrator (parallel execution)
│   ├── file_index.py         FileIndex + HashCache
│   ├── config.py             defaults and config loading
│   ├── manifest.py           SmartUpdater + GenerationManifest
│   ├── models.py             shared dataclasses
│   ├── doctor.py             diagnostics
│   ├── watch.py              file watcher
│   ├── extractors/
│   │   ├── python.py         Python AST extractor
│   │   └── typescript.py     TypeScript/JS extractor
│   ├── generators/
│   │   ├── tree.py           directory tree
│   │   ├── schemas.py        type definitions (5 languages)
│   │   ├── api.py            routes + public signatures
│   │   ├── dependencies.py   import graph + Mermaid
│   │   └── symbols.py        semantic symbol index
│   ├── security/
│   │   ├── manager.py        security orchestration
│   │   ├── modes.py          mode definitions
│   │   └── redactor.py       secret redaction
│   ├── utils/
│   │   ├── files.py          safe read/write, path filtering
│   │   ├── formatting.py     timestamps, human sizes
│   │   └── hashing.py        file hashing
│   └── workspace/
│       ├── manifest.py       workspace YAML parsing
│       ├── query.py          service querying and context generation
│       ├── conflicts.py      cross-repo conflict detection
│       └── aggregator.py     workspace aggregation
└── tests/
    ├── unit/                 extractor and generator tests
    ├── integration/          full generation tests
    └── fixtures/             Python FastAPI, TypeScript Express, multi-repo
```

-----

## Testing

```bash
pip install -r tests/requirements.txt
python tests/run_tests.py --verbose
```

Tests run against real fixture projects (Python FastAPI, TypeScript Express, multi-repo workspace) to catch regressions during refactoring.

CI runs on Python 3.10, 3.11, and 3.12 via GitHub Actions.

-----

## Roadmap

**Near-term**

- Complete migration of remaining generators from `llm-context-setup.py` into `ccc/`
- PyPI release (`pip install ccc-contextcompiler`)
- Entry points for db schema and API contract generators

**Mid-term**

- Plugin model for custom language extractors
- Richer TypeScript support (NestJS, tRPC, Next.js App Router)
- Improved workspace aggregation and change sequencing

**Long-term**

- PKML as a published standard with a JSON Schema
- Semantic retrieval and local vector indexing
- Editor/IDE integration
- Enterprise deployment workflows

-----

## Contributing

Contributions are welcome. Especially valuable:

- Language extractors (Java, Ruby, Go routes, Rust routes)
- TypeScript framework patterns (NestJS, tRPC, Prisma, Drizzle)
- Conflict detection improvements
- Real-world output examples and documentation
- Test coverage for edge cases

-----

## License

MIT — see <LICENSE>.

-----

## Status

**Functional and actively developed.**

Both single-repo and workspace mode work today. The `ccc` package is modular and installable. The standalone `llm-context-setup.py` remains available as a zero-dependency fallback.
