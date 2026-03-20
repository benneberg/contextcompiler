# CCC — TODO

## Done ✓

- Single-repo generation (tree, schemas, routes, public-api, dependencies, symbols)
- Workspace mode (list, query, validate, generate, conflicts/doctor)
- Conflict detection (enum, interface, constant, API route, event naming)
- FileIndex — single filesystem scan shared by all generators
- HashCache — mtime-gated hash cache for fast incremental runs
- Parallel generation via ThreadPoolExecutor
- Streaming framework detection (line-by-line, early exit)
- Symbol index (SymbolIndexGenerator → symbol-index.json)
- Security modes (offline, private-ai, public-ai) + secret redaction
- SmartUpdater with if-changed / if-missing / always strategies
- Watch mode
- Diagnostics (–doctor)
- pyproject.toml with `ccc` CLI entry point
- Python + TypeScript extractors
- Schema extraction: Python, TypeScript, Rust, Go, C#
- CI on Python 3.10 / 3.11 / 3.12

## Next

- Migrate remaining generators from llm-context-setup.py into ccc/
  - DatabaseSchemaExtractor → ccc/generators/database.py
  - APIContractExtractor   → ccc/generators/contracts.py
  - EntryPointDetector     → ccc/generators/entrypoints.py
  - ExternalDependencyDetector → ccc/generators/external.py
  - ModuleSummaryGenerator → ccc/generators/summaries.py
  - ScaffoldGenerator      → ccc/generators/scaffolds.py
- Wire generator.py to use the above (remove bridge to standalone script)
- PyPI release

- 	1.	ccc/generators/contracts.py — APIContractExtractor
	2.	ccc/generators/summaries.py — ModuleSummaryGenerator
	3.	ccc/generators/external.py — ExternalDependencyDetector (replaces the importlib bridge)
	4.	Wire all of them into generator.py (remove the bridge)
	5.	ccc/generators/pkml.py — the ccc pkml command that bootstraps a pkml.json
	6.	Add ccc pkml to cli.py
The natural next addition on the CCC side (once you’ve done testing) is a ccc pkml command that bootstraps a pkml.json draft from the generated context — that creates a concrete workflow between the two
## Later

- Plugin model for custom language extractors
- Richer TypeScript patterns (NestJS, tRPC, Next.js App Router, Prisma)
- Improved workspace aggregation
- Semantic retrieval / local vector indexing

  20 mars 2026
  # CCC — Development TODO

## ✅ Done

- Single-repo generation (tree, schemas, routes, public-api, dependencies, symbols)
- Workspace mode (list, query, validate, generate, conflicts/doctor)
- Conflict detection (enum, interface, constant, API route, event naming)
- FileIndex, HashCache, ThreadPoolExecutor parallel generation
- Security modes (offline, private-ai, public-ai) + secret redaction
- SmartUpdater, watch mode, diagnostics (–doctor)
- pyproject.toml with `ccc` CLI entry point, CI on Python 3.10/3.11/3.12
- Python + TypeScript extractors, schema extraction for Py/TS/Rust/Go/C#
- ClaudeMdEnhancer — auto-detect conventions for LLM.md
- ccc workspace init — scan directories, generate ccc-workspace.yml draft
- service-index.json — cached artifact for offline workspace queries
- ccc workspace serve — browser UI (tag filter, copy/download, change sequence)
- ccc workspace discover — CrossRepoDiscovery (schema drift, API route matching,
  shared infra, event coupling, confidence scoring)
- ccc query — runtime query engine (symbol, route, impact, context builder)
  all output formats: human, json, compact, markdown
- ccc align — alignment engine, CCC vs PKML drift detection
  (missing impl, undocumented endpoints, event/dep drift, graceful PKML degradation)

-----

## 🔴 High Priority (correctness)

- [ ] Fix version mismatch: ccc/**init**.py says 0.4.0, pyproject.toml says 0.1.0
- [ ] Add –help descriptions to all main CLI flags (currently blank)
- [ ] Fix SQLAlchemy detected twice in LLM.md (_detect_orm in claude_md.py)
- [ ] Clean up stub files: security/redactor.py and security/modes.py
- [ ] WorkspaceAggregator (workspace/aggregator.py) is orphaned — wire in or delete

-----

## 🟡 Medium Priority (quality & completeness)

- [ ] Test ccc workspace discover on real company repos — calibrate confidence scores
- [ ] Extend workspace serve UI to show discovered vs declared relationships
  Solid edges = declared, dashed = discovered with confidence %
- [ ] Update workspace generate to auto-run discover and annotate WORKSPACE.md
- [ ] ccc align integrated into CI as a pass/fail gate
  Exit code 1 on errors already works — just needs .github/workflows/ example
- [ ] Add git hook template, Copilot integration files to docs/examples/
- [ ] Add real output examples to README (LLM.md + routes.txt from a real project)
- [ ] Slim llm-context-setup.py once package delegation verified on real repos

-----

## 🔵 Phase 2 — Graph Persistence + Semantic Layer

- [ ] Graph persistence
  Currently dependency graph is rebuilt in memory on every CCCQueryEngine()
  instantiation. For large repos or repeated queries, serialize the networkx
  graph to .llm-context/dependency-graph.pkl between runs.
  Only rebuild when dependency-graph.txt has changed (use HashCache).
- [ ] Embeddings + hybrid retrieval
  Currently ccc query is purely lexical — substring matching.
  “Find everything related to authentication” only works if things are named auth.
  Add optional semantic layer: embed symbol names, route paths, and doc strings
  using a local model (sentence-transformers) or API (OpenAI/Anthropic embeddings).
  Store in .llm-context/embeddings.pkl
  Query: combine lexical (fast, precise) + semantic (fuzzy, intent-aware)
  Requires: pip install sentence-transformers  OR  anthropic/openai key
  This is the biggest remaining capability gap in the query engine.

-----

## 🚀 Opportunity 3 — CI Pipeline as Documentation Engine

- [ ] Per-repo CI workflow (.github/workflows/ccc-update.yml)
  Runs ccc on every push to main, commits .llm-context/ automatically,
  sends webhook to index repo to trigger re-aggregation
- [ ] PR documentation diff
  On pull_request: generate context for PR branch, diff against main,
  post as PR comment: “This change adds 2 routes, modifies User schema”
  Makes code review aware of documentation impact automatically
- [ ] ccc align in CI
  Run ccc align on every PR, fail build if documented routes go missing
  Closes the feedback loop: Code → CCC → Alignment → CI gate → Fix
- [ ] Index repo webhook receiver
  Lightweight script that pulls .llm-context/ from service repos on push,
  triggers discover + generate, keeps workspace-context/ always current

-----

## 🚀 Opportunity 4 — Multi-Audience Rendering

- [ ] AudienceRenderer (ccc/workspace/render.py)
  render_developer_workspace() — symbols, routes, conventions, gotchas
  render_manager_summary()     — service catalog: purpose, owners, health
  render_support_guide()       — customer-facing endpoints, escalation
  render_llm_context()         — optimized paste-into-AI-session format
  Principle: same source data (service-index.json), rendered differently
- [ ] Extend workspace serve UI with audience selector
  Toggle: Developer / Manager / Support / LLM views
  “Copy for LLM” already works — extend to other audiences
- [ ] Note: manager + support views need PKML populated for full value
  (purpose and owners fields come from pkml.json, not CCC artifacts)

-----

## 🔵 Phase 3 — Automation & Integrations (Later)

- [ ] GitHub automation: auto-PR when ccc align detects drift
  e.g. “Route POST /reset-password is in PKML but missing from code”
  → opens a GitHub issue or PR automatically
- [ ] VSCode extension
  Current Copilot integration via config files is a workaround.
  A real extension would: show symbol locations inline, run ccc query
  from command palette, highlight undocumented routes in editor.
- [ ] MCP server: serve .llm-context/ directly to Claude without file uploads
  ccc serve –mcp  →  exposes query engine as MCP tool calls
- [ ] Plugin model for custom language extractors
- [ ] Richer TypeScript patterns (NestJS, tRPC, Next.js App Router, Prisma)
- [ ] Java / Kotlin / PHP / Ruby extractors
- [ ] PyPI release as ccc-contextcompiler

-----

## Architecture Reminder

```
Code → CCC (IR) → .llm-context/ artifacts
                       ↓
              Query Engine (ccc query)     ← runtime access, lexical today
              Graph (networkx)             ← impact analysis
              Semantic Layer               ← embeddings, Phase 2
                       ↓
              Alignment Engine (ccc align) ← CCC reality vs PKML intent
              Cross-repo Discovery         ← undeclared dependencies
                       ↓
              CI Gate / LLM / Tools        ← consumers
```

CCC = Reality (what exists, extracted deterministically)
PKML = Intent (what should exist, declared by humans)
Never merge them — combine via Alignment Engine only.

-----

> Delete items as implemented.
> Add friction discovered during real daily use — that’s the most reliable roadmap input.
> Phase 2 (embeddings) is the biggest remaining capability gap. Build after validating
> query engine on real repos first.
