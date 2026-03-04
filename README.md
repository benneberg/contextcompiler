# LLM Context Compiler

Automatically generate LLM-optimized context files for any codebase.

Stop copying entire repositories into LLM prompts. This tool intelligently extracts and summarizes the essential context an LLM needs to understand and modify your code — types, APIs, architecture, conventions — without flooding the context window.

---

## What It Does

Generates a `.llm-context/` directory with:

* 📁 **File tree** — Project structure overview
* 🔷 **Type definitions** — Extracted schemas, interfaces, dataclasses (Python, TypeScript, Rust, Go, C#)
* 🛣️ **API routes** — All endpoints mapped
* 📝 **Public API** — Function signatures across the codebase
* 🔗 **Dependency graph** — Import relationships (text + Mermaid diagram)
* 📋 **CLAUDE.md** — Project conventions, dangerous areas, common tasks (your secret weapon)
* 🏗️ **ARCHITECTURE.md** — System design, data flow, key decisions
* ⚙️ **Config shapes** — Environment variables, dependencies

Plus:

* Smart incremental updates (only regenerates what changed)
* Watch mode
* Optional LLM-powered module summaries

---

## Why This Matters

| Without Context Files             | With Context Files                     |
| --------------------------------- | -------------------------------------- |
| Copy 50+ files into chat          | Drop 3–5 curated context files         |
| LLM sees code, misses conventions | LLM knows *why* and *how we do things* |
| Repeatedly explain architecture   | `ARCHITECTURE.md` does it once         |
| Context window filled with noise  | High signal-to-noise ratio             |
| Every session starts from zero    | Persistent project knowledge           |

**CLAUDE.md is the game-changer.**
It tells the LLM about your dangerous files, coding patterns, and gotchas — things no amount of code reading provides.

---

# Installation

## Option 1: Single File (Zero Dependencies)

Download and run:

```bash
curl -O https://raw.githubusercontent.com/yourusername/llm-context/main/llm_context_setup.py
python3 llm_context_setup.py
```

---

## Option 2: Drop Into Your Repo

```bash
# Add to your project
wget -O generate-context.py https://raw.githubusercontent.com/yourusername/llm-context/main/llm_context_setup.py

# Run it
python3 generate-context.py
```

---

## Option 3: Install as a Tool (Recommended for Multi-Project Use)

```bash
pip install llm-context-generator

# Now available everywhere
llm-context
```

### Requirements

* Python 3.10+
* Core functionality has **zero dependencies**

Optional features:

```bash
pip install anthropic     # or
pip install openai        # LLM-powered module summaries

pip install pyyaml        # YAML config files
pip install watchdog      # Watch mode
```

---

# Quick Start

```bash
# Full generation (first run)
python3 llm_context_setup.py

# Fast incremental update
python3 llm_context_setup.py --quick-update

# Watch mode (auto-update on save)
python3 llm_context_setup.py --watch

# Force full regeneration
python3 llm_context_setup.py --force

# Include LLM-powered module summaries
python3 llm_context_setup.py --with-summaries
```

---

# Usage

## First Time Setup

Run the generator:

```bash
python3 llm_context_setup.py
```

Generated structure:

```
.llm-context/
├── tree.txt
├── schemas-extracted.py
├── routes.txt
├── public-api.txt
├── dependency-graph.txt
├── dependency-graph.md
└── manifest.json

CLAUDE.md
ARCHITECTURE.md
```

Complete the scaffolds:

* Edit `CLAUDE.md` to add conventions, dangerous areas, gotchas
* Edit `ARCHITECTURE.md` to document system design

---

# Daily Workflow

## Manual Updates (Recommended)

```bash
python3 llm_context_setup.py --quick-update
```

Takes <2 seconds and only regenerates changed files.

---

## Automatic Updates (Git Hook)

Create `.git/hooks/post-commit`:

```bash
#!/bin/bash

if git diff HEAD~1 --name-only | grep -qE "\.(py|ts|js|rs|go|cs)$"; then
  echo "Updating LLM context..."
  python3 llm_context_setup.py --quick-update
fi
```

Make executable:

```bash
chmod +x .git/hooks/post-commit
```

---

## Watch Mode

```bash
python3 llm_context_setup.py --watch
```

Auto-updates context whenever files change.

---

# Using Context Files with LLMs

## Claude / ChatGPT

Upload in this order:

```
1. CLAUDE.md
2. ARCHITECTURE.md
3. .llm-context/schemas-extracted.py
4. .llm-context/routes.txt
5. Specific file you're editing
```

Then prompt normally:

> "I need to add a new endpoint for user notifications..."

---

## Cursor / GitHub Copilot

Add to `.cursorules` or `.github/copilot-instructions.md`:

```markdown
# Project Context

Before suggesting changes, review:
- `/CLAUDE.md`
- `/ARCHITECTURE.md`
- `/.llm-context/schemas-extracted.py`
- `/.llm-context/routes.txt`
```

---

## Continue.dev / Aider

`.continuerc.json`:

```json
{
  "context": [
    "CLAUDE.md",
    "ARCHITECTURE.md",
    ".llm-context/**/*.txt",
    ".llm-context/**/*.md"
  ]
}
```

---

# Configuration

Create `llm-context.yml`:

```yaml
output_dir: .llm-context

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
  recent_activity: true
  claude_md_scaffold: true
  architecture_md_scaffold: true
  module_summaries: false

update_strategies:
  tree.txt: always
  schemas-extracted.py: if-changed
  ../CLAUDE.md: if-missing

llm_summaries:
  provider: anthropic
  model: claude-sonnet-4-20250514
  max_modules: 30
```

---

# Advanced Features

## LLM-Powered Module Summaries

```bash
export ANTHROPIC_API_KEY="sk-..."
python3 llm_context_setup.py --with-summaries
```

Creates `.llm-context/modules/`.

---

## Remote Repository Scanning

```bash
python3 llm_context_setup.py --remote username/repo
```

---

## Custom Output Directory

```bash
python3 llm_context_setup.py --output docs/llm-context
```

---

# CI/CD Integration

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
        run: python3 llm_context_setup.py

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

# Command Reference

```bash
# Basic
llm_context_setup.py [path]

# Update modes
llm_context_setup.py --quick-update
llm_context_setup.py --force
llm_context_setup.py --watch

# Features
llm_context_setup.py --with-summaries
llm_context_setup.py --remote user/repo

# Config
llm_context_setup.py --output DIR
llm_context_setup.py --config FILE

# Info
llm_context_setup.py --version
llm_context_setup.py --help
```

---

# What Makes This Different

**vs. Repomix**
Repomix concatenates files. This extracts semantic context (types, routes, dependencies) and supports incremental updates.

**vs. Manual Copying**
Automated, consistent, always fresh.

**vs. AI-Generated Docs**
This generates inputs for LLMs — optimized for context windows — not human-facing documentation.

**Key Insight:**
`CLAUDE.md` captures conventions and judgment that cannot be inferred from code.

---

# Tips for Maximum Impact

* Invest 30 minutes in `CLAUDE.md`
* Run `--quick-update` after every session
* Start every LLM conversation with `CLAUDE.md`
* Use dependency graphs for refactoring
* Commit `.llm-context/` to version control

---

# Troubleshooting

### "No module named 'yaml'"

```bash
pip install pyyaml
```

### "No module named 'anthropic'"

```bash
pip install anthropic
# or
pip install openai
```

### Watch mode not working

```bash
pip install watchdog
```

### Context files stale

```bash
python3 llm_context_setup.py --force
```

---

# File Structure Reference

```
your-project/
├── .llm-context/
│   ├── tree.txt
│   ├── schemas-extracted.py
│   ├── types-extracted.ts
│   ├── routes.txt
│   ├── public-api.txt
│   ├── dependency-graph.txt
│   ├── dependency-graph.md
│   ├── env-shape.txt
│   ├── recent-commits.txt
│   ├── pyproject.toml
│   ├── manifest.json
│   └── modules/
├── CLAUDE.md
├── ARCHITECTURE.md
├── llm-context.yml
└── llm_context_setup.py
```

---

# License

MIT

---

# Contributing

PRs welcome, especially for:

* Additional language support (Java, PHP, Ruby, Kotlin)
* Framework-specific extractors
* Database schema reverse engineering
* MCP server integration

---

# Ready to give your LLM the context it deserves?

```bash
python3 llm_context_setup.py
```
