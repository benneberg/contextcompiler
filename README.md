# CCC - Code Context Compiler (LLM-ready)

**LLM-ready context, instantly.
Automatically generate LLM-optimized context files and turn your codebase into AI-readable knowledge.**


No more copying entire repositories into LLM prompts. This tool intelligently extracts and summarizes the essential context an LLM needs to understand and modify your code — types, APIs, architecture, conventions — without flooding the context window.

- Stop flooding LLM prompts: Only provide relevant context
- Persistent project knowledge: LLMs understand conventions, architecture, and core logic
- Incremental updates & watch mode: Keep context fresh effortlessly
- Secret redaction & audit logs: Safe for corporate use
---

## What It Does

Generates a `.llm-context/` directory with:

- 📁 **File tree** — Project structure overview
- 🔷 **Type definitions** — Extracted schemas, interfaces, dataclasses (Python, TypeScript, Rust, Go, C#)
- 🛣️ **API routes** — All endpoints mapped
- 📝 **Public API** — Function signatures across the codebase
- 🔗 **Dependency graph** — Import relationships (text + Mermaid diagram)
- 🗺️ **Symbol index** — Navigate classes and functions across your codebase
- 🎯 **Entry points** — Main files, servers, CLI tools detected
- 🗄️ **Database schema** — SQLAlchemy, Django, Prisma, TypeORM models extracted
- 📋 **CLAUDE.md** — Auto-detected conventions, dangerous areas, common tasks
- 🏗️ **ARCHITECTURE.md** — System design scaffold
- ⚙️ **Config shapes** — Environment variables, dependencies

**Plus:**
- ✅ Smart incremental updates (only regenerates what changed)
- 🔒 Security modes (offline/private-ai/public-ai)
- 👁️ Watch mode with intelligent debouncing
- 🩺 Built-in diagnostics (`--doctor`)
- 🔐 Automatic secret redaction
- 📊 Audit logging
- 🚀 Zero required dependencies for core features

---

## Why This Matters

| Without Context Files | With Context Files |
|---|---|
| Copy 50+ files into chat | Drop 3-5 curated context files |
| LLM sees code, misses conventions | LLM knows **why** and **how we do things** |
| Repeatedly explain architecture | `ARCHITECTURE.md` does it once |
| Context window filled with noise | High signal-to-noise ratio |
| Every session starts from zero | Persistent project knowledge |

**CLAUDE.md is the game-changer:** It tells the LLM about your dangerous files, coding patterns, and gotchas — things no amount of code reading provides. **Now auto-populated** with detected conventions!

---

## Installation

### Option 1: Single File (Zero Dependencies)

Download and run:

```bash
curl -O https://raw.githubusercontent.com/yourusername/llm-context/main/llm-context-setup.py
python3 llm-context-setup.py
```

### Option 2: Drop Into Your Repo

```bash
# Add to your project
wget -O llm-context-setup.py https://raw.githubusercontent.com/yourusername/llm-context/main/llm-context-setup.py

# Run it
python3 llm-context-setup.py
```

### Option 3: Install as a Tool (Coming Soon)

```bash
pip install llm-context-generator
llm-context
```

**Requirements:**
- Python 3.10+
- Core functionality has **zero dependencies**

**Optional features:**
```bash
pip install anthropic     # or openai - for LLM module summaries
pip install pyyaml        # for YAML config files
pip install watchdog      # for watch mode
```

---

## Quick Start

```bash
# Check everything is working
python3 llm-context-setup.py --doctor

# Full generation (first run)
python3 llm-context-setup.py

# Fast incremental update (only regenerates changed files)
python3 llm-context-setup.py --quick-update

# Watch mode (auto-update on file changes)
python3 llm-context-setup.py --watch

# Force full regeneration (ignore cache)
python3 llm-context-setup.py --force

# Include LLM-powered module summaries (requires API key)
python3 llm-context-setup.py --with-summaries

# Show security configuration
python3 llm-context-setup.py --security-status
```

---

## Usage

### First Time Setup

1. **Run the generator:**
```bash
python3 llm-context-setup.py
```

2. **Review generated files:**
```
.llm-context/
├── tree.txt                    # File structure
├── schemas-extracted.py        # Type definitions
├── routes.txt                  # API endpoints
├── public-api.txt              # Function signatures
├── dependency-graph.txt        # Import relationships
├── dependency-graph.md         # Visual graph (Mermaid)
├── symbol-index.json           # Symbol navigation
├── entry-points.json           # Main files detected
├── db-schema.txt               # Database schema (if found)
├── api-contract.md             # OpenAPI/GraphQL (if found)
└── manifest.json               # Tracks generation metadata

CLAUDE.md                       # ⭐ Auto-populated! Review and enhance
ARCHITECTURE.md                 # ⭐ Scaffold created - fill in TODOs
```

3. **Complete the scaffolds:**
   - Review `CLAUDE.md` — conventions are auto-detected!
   - Fill in `ARCHITECTURE.md` TODOs
   - Customize `llm-context.yml` if needed

---

## Daily Workflow

### Manual Updates (Recommended)

After a development session:

```bash
python3 llm-context-setup.py --quick-update
```

Takes <2 seconds and only regenerates changed files.

### Automatic Updates (Git Hooks)

Create `.git/hooks/post-commit`:

```bash
#!/bin/bash
# Auto-update context after commits with source file changes

if git diff HEAD~1 --name-only | grep -qE "\.(py|ts|js|rs|go|cs)$"; then
  echo "🔄 Updating LLM context..."
  python3 llm-context-setup.py --quick-update
fi
```

Make executable:
```bash
chmod +x .git/hooks/post-commit
```

### Watch Mode (Active Development)

```bash
python3 llm-context-setup.py --watch
```

Auto-updates context whenever you save a file. Changes are debounced (waits 2 seconds after last change).

---

## Security Features

The tool supports three security modes:

### Offline Mode (Default)
```yaml
# llm-context.yml
security:
  mode: offline
  redact_secrets: true
  audit_log: true
```

- ❌ No external API calls
- ❌ LLM summaries disabled
- ✅ All analysis is local
- ✅ Safe for proprietary code

### Private AI Mode
```yaml
security:
  mode: private-ai
```

- Use with Azure OpenAI or self-hosted models
- Code stays in your infrastructure

### Public AI Mode
```yaml
security:
  mode: public-ai
```

- Enables OpenAI/Anthropic API calls
- **Warning displayed** before sending code

**Secret redaction is automatic:**
- API keys, passwords, tokens masked
- Sensitive files excluded
- Audit log tracks all operations

Check security status:
```bash
python3 llm-context-setup.py --security-status
```

---

## Using Context Files with LLMs

### Claude / ChatGPT

**For a new task:**

Upload in this order:
1. `CLAUDE.md`
2. `ARCHITECTURE.md`
3. `.llm-context/schemas-extracted.py`
4. `.llm-context/routes.txt`
5. Specific file you're working on

Then prompt:
> "I need to add a new endpoint for user notifications..."

### Cursor / GitHub Copilot

Add to `.cursorules` or `.github/copilot-instructions.md`:

```markdown
# Project Context

Before suggesting changes, review:
- `/CLAUDE.md` — conventions and patterns
- `/ARCHITECTURE.md` — system design
- `/.llm-context/schemas-extracted.py` — data models
- `/.llm-context/routes.txt` — existing endpoints
- `/.llm-context/symbol-index.json` — code navigation
```

### Continue.dev / Aider

`.continuerc.json`:
```json
{
  "context": [
    "CLAUDE.md",
    "ARCHITECTURE.md",
    ".llm-context/**/*.txt",
    ".llm-context/**/*.md",
    ".llm-context/**/*.json"
  ]
}
```

---

## Configuration

Create `llm-context.yml` in your project root:

```yaml
output_dir: .llm-context

security:
  mode: offline              # offline | private-ai | public-ai
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
  api_contract: true
  recent_activity: true
  claude_md_scaffold: true
  architecture_md_scaffold: true
  module_summaries: false    # requires LLM API key

# How often to regenerate each file
update_strategies:
  tree.txt: always                    # Always fresh
  schemas-extracted.py: if-changed    # Only if schemas changed
  ../CLAUDE.md: if-missing            # Never overwrite

llm_summaries:
  provider: anthropic  # or openai
  model: claude-sonnet-4-20250514
  max_modules: 30
```

---

## Advanced Features

### LLM-Powered Module Summaries

Generate natural language summaries of your modules:

```bash
# Requires ANTHROPIC_API_KEY or OPENAI_API_KEY
export ANTHROPIC_API_KEY="sk-..."

python3 llm-context-setup.py --with-summaries
```

Creates `.llm-context/modules/` with per-module explanations.

**Note:** This switches to `public-ai` mode automatically. Use `private-ai` for company infrastructure.

### Diagnostics

Run comprehensive checks:

```bash
python3 llm-context-setup.py --doctor
```

Checks:
- ✅ Python version and dependencies
- ✅ Project structure and languages
- ✅ Generated context status
- ✅ Security configuration
- ✅ Recommendations for improvement

### Custom Output Directory

```bash
python3 llm-context-setup.py --output docs/llm-context
```

### CI/CD Integration

`.github/workflows/llm-context.yml`:

```yaml
name: Update LLM Context
on:
  push:
    branches: [main]
    paths-ignore: ['.llm-context/**']

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 5
      
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Generate context
        run: python3 llm-context-setup.py
      
      - name: Commit changes
        run: |
          git config user.name "github-actions"
          git config user.email "actions@github.com"
          git add .llm-context/ CLAUDE.md ARCHITECTURE.md
          git diff --staged --quiet || \
            git commit -m "chore: update LLM context [skip ci]" && \
            git push
```

---

## Command Reference

```bash
# Basic usage
python3 llm-context-setup.py [path]              # Generate for project at path

# Update modes
python3 llm-context-setup.py --quick-update      # Fast incremental (skip expensive ops)
python3 llm-context-setup.py --force             # Ignore cache, regenerate everything
python3 llm-context-setup.py --watch             # Watch for changes, auto-update

# Features
python3 llm-context-setup.py --with-summaries    # Include LLM module summaries
python3 llm-context-setup.py --doctor            # Run diagnostics
python3 llm-context-setup.py --security-status   # Show security config

# Configuration
python3 llm-context-setup.py --output DIR        # Custom output directory
python3 llm-context-setup.py --config FILE       # Custom config file

# Info
python3 llm-context-setup.py --version           # Show version
python3 llm-context-setup.py --help              # Show help
```

---

## What Makes This Different

**vs. Repomix:** Repomix concatenates files. This extracts *semantic* context (types, routes, dependencies) with incremental updates and security controls.

**vs. Manual copying:** Automated extraction, always fresh, enforces consistent structure.

**vs. AI-generated docs:** Generates *inputs* for LLMs optimized for context windows, not human documentation.

**Key insight:** `CLAUDE.md` captures *conventions and judgment* that can't be extracted from code. Now **auto-populated** with detected patterns!

---

## Auto-Detection Features

The tool automatically detects and populates `CLAUDE.md` with:

✅ **Error handling patterns** (Result type vs exceptions)  
✅ **Testing frameworks** (pytest, jest, vitest, etc.)  
✅ **Async/await usage** (heavy async, mixed, sync)  
✅ **ORM/database layer** (SQLAlchemy, Prisma, TypeORM, etc.)  
✅ **API style** (REST, GraphQL, gRPC)  
✅ **Logging frameworks** (stdlib, loguru, structlog)  
✅ **Code quality tools** (ruff, black, mypy, eslint, prettier)  
✅ **Dangerous files** (payment, auth, crypto, migration code)  

All automatically analyzed and documented!

---

## Tips for Maximum Impact

1. **Review auto-generated `CLAUDE.md`** — Add project-specific details to the TODOs
2. **Run `--quick-update` after each session** — It's <2s and keeps context fresh
3. **Start every LLM conversation with `CLAUDE.md`** — Sets the right context immediately
4. **Use dependency graphs** — The Mermaid diagrams are great for refactoring
5. **Version control your context** — Commit `.llm-context/` and manual files
6. **Use `--doctor` regularly** — Catches issues early

---

## Troubleshooting

**"No module named 'yaml'"**
```bash
pip install pyyaml
```

**"No module named 'anthropic'"**
```bash
pip install anthropic  # or: pip install openai
```

**"Watch mode not working"**
```bash
pip install watchdog
```

**Context files are stale**
```bash
python3 llm-context-setup.py --force
```

**Too slow / too much output**
- Edit `llm-context.yml` to disable expensive operations
- Use `--quick-update` instead of full generation

**Security concerns**
```bash
# Check current mode
python3 llm-context-setup.py --security-status

# Ensure offline mode in llm-context.yml
security:
  mode: offline
```

---

## File Structure Reference

```
your-project/
├── .llm-context/                    # Generated context (commit this)
│   ├── tree.txt                     # Project file structure
│   ├── schemas-extracted.py         # Type definitions
│   ├── types-extracted.ts           # TypeScript interfaces
│   ├── routes.txt                   # API endpoints
│   ├── public-api.txt               # Function signatures
│   ├── dependency-graph.txt         # Import relationships
│   ├── dependency-graph.md          # Mermaid visualization
│   ├── symbol-index.json            # Symbol navigation
│   ├── entry-points.json            # Entry point detection
│   ├── db-schema.txt                # Database schema (if found)
│   ├── api-contract.md              # OpenAPI/GraphQL (if found)
│   ├── env-shape.txt                # Environment variables
│   ├── recent-commits.txt           # Recent git activity
│   ├── pyproject.toml               # Dependencies (copy)
│   ├── manifest.json                # Generation metadata
│   ├── audit.log                    # Security audit log
│   └── modules/                     # LLM module summaries (optional)
│       ├── services__payment.md
│       └── ...
├── CLAUDE.md                        # ⭐ Auto-populated conventions
├── ARCHITECTURE.md                  # ⭐ System design scaffold
├── llm-context.yml                  # Optional: configuration
└── llm-context-setup.py             # The generator script
```

---

## What's New in v0.4.0

- 🔒 **Security modes** (offline/private-ai/public-ai)
- 🔐 **Automatic secret redaction**
- 📊 **Audit logging**
- 🗺️ **Symbol indexing**
- 🎯 **Entry point detection**
- 🗄️ **Database schema extraction**
- 🧠 **Enhanced CLAUDE.md auto-detection**
- 🩺 **Diagnostics command** (`--doctor`)
- 🛡️ **Binary file detection**
- 📝 **UTF-8 encoding everywhere**
- ⚡ **Better incremental updates**
- 👁️ **Improved watch mode**

---

## License

MIT

---

## Contributing

PRs welcome! Especially for:
- Additional language support (Java, PHP, Ruby, Kotlin)
- Framework-specific extractors (Spring Boot, Rails, Laravel)
- Enhanced database schema reverse engineering
- MCP server integration

---

**Ready to give your LLM the context it deserves?**

```bash
python3 llm-context-setup.py --doctor
python3 llm-context-setup.py
```

---

*Built for developers who likes structure and optimation when working with llm's in larger codebase and code birds nests.*

---
