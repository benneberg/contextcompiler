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

## Later

- Plugin model for custom language extractors
- Richer TypeScript patterns (NestJS, tRPC, Next.js App Router, Prisma)
- Improved workspace aggregation
- Semantic retrieval / local vector indexing
