# CCC — Development Backlog

> Merged from codebase review + architecture notes.  
> **P1** — fix/ship now (correctness, onboarding, observability)  
> **P2** — core capability architecture + LLM efficiency upgrades  
> **P3** — planning/simulation layers, advanced integrations, long-term
> 
> Architecture principle: each layer depends on the previous.  
> Do not start P3 planning layer until P2 capability layers are validated on real repos.

-----

## P1 — Do First

*Correctness fixes, onboarding, observability. Relatively contained. These are prerequisites for everything else.*

-----

### Onboarding & UX

#### P1-01 · `ccc setup` — Interactive onboarding command

Current multi-step workflow (init → ccc per service → generate → serve) requires reading the README. Replace with a single guided command.

- Detect git repos in current directory → suggest workspace mode
- Prompt for workspace name and confirm discovered services
- Run `ccc` per service + `workspace generate` in one go
- End with: “Done. Run `ccc workspace serve` to explore.”
- Pure UX shell — reuses all existing logic

#### P1-02 · `ccc workspace serve` detects stale/missing per-service context

UI loads silently incomplete when services have outdated or missing `.llm-context/`. Users don’t know what they’re missing.

- Compare `manifest.json` timestamps against last git commit timestamps per service
- Show “stale context” warning banner in UI for affected services
- Show clearly which services have no `.llm-context/` at all
- Offer shell command hint to regenerate

#### P1-03 · `workspace discover` auto-runs during `workspace generate`

Undeclared dependency detection is genuinely valuable but almost no user knows it exists. It reads already-generated artifacts — zero extra scan cost.

- Run discovery automatically at end of `workspace generate`
- Print short summary: N undeclared relationships found
- Write `workspace-context/discovered-relationships.md` alongside other output
- Add `--skip-discover` flag to opt out

#### P1-04 · `workspace discover` surfaced inline in serve UI

Discovered-relationships report is written to disk but never shown in the browser UI.

- Add “Dependencies” tab or panel to serve UI
- Show undeclared relationships with confidence scores and evidence
- Color-coded: red (high confidence undeclared), yellow (medium), green (declared + confirmed)
- Link to relevant service detail pages

-----

### Observability

#### P1-05 · Per-generator timing output

No timing information anywhere. No way to know if `symbol-index` took 50ms or 8 seconds.

- `time.perf_counter()` around each generator future
- Print timing table at end of generation run
- Total wall-clock time in the summary line
- `--profile` flag for full timing breakdown

#### P1-06 · Replace `print()` with structured logging + `--quiet` / `--verbose`

349 `print()` calls, no log levels. CI pipelines and automation cannot suppress noise.

- Replace with `logging.getLogger("ccc")` at appropriate levels
- `--quiet` flag (WARNING and above only)
- `--verbose` flag (DEBUG level)
- `--log-file` flag (useful for watch mode)
- Keep existing console formatting for INFO so human output is unchanged

#### P1-07 · `ccc inspect <file>` — per-file context debugger

No way to see what CCC extracted from a specific file. Essential for debugging incomplete context.

- Show: symbols extracted, routes found, imports detected, schema types found
- Show: whether file is in symbol-index, routes.txt, dependency graph
- Show: file size, last modified, whether skipped and why
- Usage: `ccc inspect src/thumbnail/encoder.py`

-----

### Correctness & Security

#### P1-08 · Fix audit log append mode

Current implementation reads entire audit.log into memory then rewrites it on every `generate` run. O(n) in log size, corrupts under concurrent access.

- Replace read-all + rewrite with `open(path, "a")` append mode
- Add max size rotation (5MB, keep last N entries)
- Log `workspace serve` page views (currently nothing logged)

#### P1-09 · Security headers on `workspace serve`

HTTP server sends only `Content-Type`. Port forwarding (devcontainer, Docker, VS Code) exposes the UI with no protection.

- Add `X-Frame-Options: DENY`
- Add `X-Content-Type-Options: nosniff`
- Add `Cache-Control: no-store`
- Add `--bind` flag (default: `127.0.0.1`, allow `0.0.0.0` explicitly)
- Add `--token` flag for optional single-use access token in URL

#### P1-10 · Deeper secret redaction patterns

Current patterns only catch `KEY=`, `PASSWORD=`, `SECRET=`, `TOKEN=`, Bearer tokens. Many real credential formats missed.

- Private key blocks: `-----BEGIN RSA PRIVATE KEY-----`
- Connection strings: `postgresql://user:pass@host/db`, `amqp://user:pass@host`
- AWS-style access keys: `AKIA[0-9A-Z]{16}`
- JSON-embedded secrets: `"password": "value"`
- Apply redaction to `pyproject.toml` and `package.json` copies too, not just `.env.example`

#### P1-11 · Version from `pyproject.toml` via `importlib.metadata`

`VERSION = "0.1.0"` hardcoded in `version.py` will diverge from `pyproject.toml` on first release.

```python
from importlib.metadata import version, PackageNotFoundError
try:
    VERSION = version("ccc-contextcompiler")
except PackageNotFoundError:
    VERSION = "dev"
```

-----

## P2 — Core Architecture + LLM Efficiency

*The capability layer is the structural upgrade that makes CCC a reasoning engine, not just a context tool. Implement layers in order — each depends on the previous.*

-----

### Capability Layer 1 — `capabilities.json` (Foundation)

*Makes repos self-describing at a semantic level, not just structural.*

#### P2-01 · Define `capabilities.json` schema

Richer than `external-dependencies.json`: adds keywords, ownership, capability grouping.

```
.llm-context/capabilities.json:
  service, version, generated
  capabilities[]:
    name, description
    tags[]       — connects to existing tag system
    keywords[]   — for intent matching ("platform", "adapter", "device")
    owns[]       — domain classes this capability owns (e.g. PlatformConfig)
    exposes:     api[], events[], types[]
    consumes:    services[], apis[], types[]
```

- Add schema definition to `docs/`
- Update `ccc-workspace.yml` schema docs

#### P2-02 · `CapabilityGenerator` — auto-generate `capabilities.json`

- Reads: `routes.txt`, `schemas-extracted.*`, `external-dependencies.json`, `symbol-index.json`
- Groups routes and schemas into logical capabilities by prefix/namespace
- Auto-suggests tags and keywords from route patterns and class names
- Uses **if-missing** update strategy — human edits preserved after first run
- Wire into `generator.py` parallel step

#### P2-03 · Aggregate capabilities into `service-index.json`

- Extend `workspace/index.py` to read each service’s `capabilities.json`
- Add `capabilities[]` array to each service entry in `service-index.json`
- Update serve UI to show capabilities per service card

-----

### Capability Layer 2 — Workspace Capability Index

*Aggregates all `capabilities.json` into a queryable workspace index. Foundation for intent resolution.*

#### P2-04 · Build `workspace-context/capability-index.json`

Generated by `ccc workspace generate` (extend existing).

```
capability-index.json:
  by_tag:      { "platforms": { repos[], capabilities[] } }
  by_keyword:  { "platform": ["pairing-service", "cms"] }
  by_api:      { "POST /api/pairing/initiate": "pairing-service" }
  by_type:     { "PlatformConfig": ["pairing-service", "cms"] }
  by_owner:    { "PairingSession": "pairing-service" }
```

#### P2-05 · Build consumer index alongside capability index

- Maps each API/type → which repos consume it
- Enables: “what would break if PlatformConfig changes?”
- Structural foundation for semantic blast radius (P3)

-----

### Capability Layer 3 — Intent Resolver

*Maps human language to relevant repos. The missing decision layer.*

#### P2-06 · `intent_keywords` config in `ccc-workspace.yml`

Curated map from domain vocabulary to tags. Human-maintained fallback — no LLM required.

```yaml
intent_keywords:
  platform: [platforms, devices, adapters]
  auth: [authentication, security, login]
  user: [users, profiles, accounts]
```

#### P2-07 · `IntentResolver` in `ccc/workspace/intent.py`

- Input: natural language string
- Step 1: tokenize, remove stopwords
- Step 2: match tokens against capability keywords (from `capability-index.json`)
- Step 3: match against `intent_keywords` config
- Step 4: score repos by match count, return ranked with explanations
- Step 5: expand via dependency graph (include deps and dependents)
- Output: ranked repo list with confidence + which keywords matched

#### P2-08 · Wire IntentResolver into CLI

```
ccc workspace query "add a new platform"
```

Resolves to tags automatically, shows reasoning:

```
Matched keyword 'platform' → tags: [platforms, devices]
Found 3 repos: pairing-service (0.92), cms (0.88), tizen-player (0.75)
```

#### P2-09 · Optional LLM upgrade path for intent extraction

- If `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` configured, use LLM for intent extraction
- Falls back to keyword map gracefully without a key
- Keyword map must always work standalone — LLM is enhancement only

-----

### Capability Layer 4 — Task Context Assembly

*Generates task-specific workspace context, not just generic cross-repo context.*

#### P2-10 · Task context generation

```
ccc workspace query "add a new platform" --generate
```

Produces `workspace-context/task-{slug}/`:

- `TASK-CONTEXT.md` — which repos, why matched, suggested implementation order
- `relevant-symbols.txt` — symbols from all matched repos relevant to intent
- `relevant-routes.txt` — routes matching intent across repos
- `change-sequence.md` — ordered implementation plan for this task

#### P2-11 · Depth-aware dependency expansion

- `--depth 1` — direct deps/dependents only (default)
- `--depth 2` — transitive (full blast radius context)

#### P2-12 · “Copy workspace for Copilot” — one-click context export

In serve UI: after intent query resolves relevant services, emit a ready-to-paste block:

```
#file:pairing-service/.llm-context/LLM.md
#file:cms/.llm-context/LLM.md
#file:shared-types/.llm-context/LLM.md

Task: Add webOS platform support.
Matched services: pairing-service (primary), cms (config owner), shared-types (type definitions).
```

-----

### LLM Efficiency — Complementary Artifacts

#### P2-13 · `context-manifest.json` — token budget hints per artifact

An LLM agent managing its own context window needs to know artifact sizes before loading them.

- Fields per artifact: `filename`, `size_bytes`, `estimated_tokens`, `description`, `last_updated`, `recommended_for`
- Enables agents to make informed include/exclude decisions
- Referenced in LLM.md header so agents know it exists

#### P2-14 · Call graph / 2-level function dependency tracing

Symbol index knows what functions exist but not how they call each other.

- Extend Python extractor (already uses `ast`) to record function calls
- Extend TypeScript extractor (regex acceptable for 2-level depth)
- Add `call-graph.json`: `{ "process_thumbnail": ["encode_frame", "resize_image"], ... }`
- Annotate symbol-index entries with `calls` and `called_by` arrays
- Limit to 2 levels to keep artifact size manageable

#### P2-15 · Cross-file type resolution in TypeScript extractor

Types extracted per-file but import relationships not followed. `VideoConfig` in `types.ts` imported and extended in `thumbnail.ts` appears as two disconnected things.

- Parse `import` statements in TypeScript extractor
- Build type resolution map: for each type, record all files that import or extend it
- Add `type-graph.json`: `{ "VideoConfig": { "defined_in": "types.ts", "used_in": [...] } }`

#### P2-16 · `change-surface.json` — ranked file relevance for tasks

When an LLM is asked to implement something, the most useful signal is which files most likely need editing.

- Score each file by: import fan-in, recent change frequency (git log), pattern density
- Ranked list with relevance scores and reasons
- Feeds into intent query and task context assembly (P2-10)

#### P2-17 · LLM.md drift detection — suggest updates without overwriting

LLM.md is generated once (if-missing) and never updated. Codebase changes but context doc stays frozen.

- On each `ccc` run, compare what would be generated fresh vs. current LLM.md
- If significant divergence detected, write `LLM.md.suggested-updates` alongside
- Print summary: “3 new routes detected since LLM.md was written”
- `--update-llm-md` appends a dated “Changes since last update” section

#### P2-18 · Negative space / gaps documentation in LLM.md

What the codebase does NOT do is as important as what it does. LLMs hallucinate plausible-but-absent functions.

- Add `## Known Gaps` section to LLM.md scaffold
- List: unimplemented PKML items (from `ccc align`), TODOs extracted from source, missing error handling patterns
- Feed `ai-observations.md` entries (P2-22) into this section over time

#### P2-19 · Committable `service-index.json` — explicit workflow

File is designed to be committed but there is no guidance or tooling. This blocks the key workflow: teammate clones workspace repo, runs `ccc workspace serve`, gets full picture without cloning all service repos.

- Add `--commit-index` flag to `workspace generate` that stages the file
- Document the workflow explicitly in serve UI
- Staleness warning when `service-index.json` is older than N days

-----

### Serve UI Improvements

#### P2-20 · Built-in report views

Data already exists — needs rendering surfaces.

- **Stale Context** — services with old or missing `.llm-context/`, sortable by age
- **Coverage Map** — which services have routes / schemas / symbols / full context vs. partial
- **Schema Drift** — types that exist in multiple services with diverged fields
- **Change Impact** — enter a service, see propagation fan-out
- **Undeclared Dependencies** — surfaces `discovered-relationships.json` inline (see P1-04)

#### P2-21 · Custom saved views

- Stored in `localStorage` — no backend needed
- Saveable from any filtered state: name the current tag filter set
- “Saved Views” sidebar section
- Exportable as URL hash for sharing

#### P2-22 · Auto-refresh option

UI is a static snapshot — stale data shows with no indication.

- `--auto-refresh N` flag (seconds polling interval)
- Manual “Refresh” button as baseline
- “Last updated X seconds ago” in header

-----

### Language Coverage

#### P2-23 · Go extractor

Framework detection already identifies gin/fiber but extraction falls back to regex.

- Extract exported `func` signatures (capitalised)
- Extract struct type definitions
- Extract HTTP route registrations (`r.GET`, `r.POST`, gin/fiber patterns)
- Parse `go.mod` for module name and dependencies

#### P2-24 · Rust extractor

Actix-web and Axum detection exists. Common in performance-critical services (media, gateways).

- Extract `pub fn` signatures
- Extract `pub struct` and `pub enum` definitions
- Extract route macros (`#[get("/path")]`, `#[post("/path")]`)
- Parse `Cargo.toml` for crate name and dependencies

#### P2-25 · TypeScript full AST extraction via tree-sitter

Current TS extractor uses regex — adequate but imprecise.

- Use `tree-sitter-typescript` Python binding (no Node.js required)
- Do NOT use `ts-morph` — requires Node.js sidecar, breaks zero-dep philosophy
- Delivers precise type resolution needed for P2-15

#### P2-26 · C# extractor

Common in enterprise environments alongside TypeScript frontends.

- Extract `public` method signatures
- Extract class and interface definitions
- Extract ASP.NET route attributes (`[HttpGet]`, `[Route]`)
- Parse `.csproj` for package dependencies

-----

### AI Feedback Loop

#### P2-27 · `ai-observations.md` convention + prompt template

Lightweight convention for LLMs to record what was missing or helpful after a session. Builds organic signal over time, no new infrastructure needed.

- Add to LLM.md scaffold:
  
  ```markdown
  ## For the AI Assistant
  After completing a task using this context, please append to
  `.llm-context/ai-observations.md`:
  - Date and task description
  - What context was sufficient
  - What was missing or required assumptions
  - Which files you needed that weren't referenced here
  ```
- Create `ai-observations.md` template on first `ccc` run
- `ccc doctor` reads and summarises: “3 entries mention missing codec configuration”

#### P2-28 · `ccc feedback` — structured post-session feedback command

- Prompts: which services were involved, was context sufficient, what was missing
- Stores in `.llm-context/feedback-log.jsonl`
- `ccc feedback --analyze` summarizes patterns
- Feeds into `ccc doctor` recommendations

-----

## P3 — Planning, Simulation & Long-term

*Depends on P2 capability layers being validated on real repos first. Do not start Phase 2/3 planning until Layers 1-4 are working.*

-----

### Phase 2 — Planning Layer

#### P3-01 · `CapabilityDiff` — intent vs. current capabilities

Compare intent against current capabilities to identify per-repo work type.

- “add webOS platform” → identifies per repo: `modify` | `create` | `no change`
- Flags capability gaps: intent mentions something no repo currently owns

#### P3-02 · `FeaturePlanner` — ordered per-repo task list

Uses `owns` field from `capabilities.json` to locate which file to change.

```
Phase 1 — shared-types:    modify Platform enum        (owns: Platform)
Phase 2 — cms:             modify platform config       (owns: PlatformConfig)
Phase 3 — pairing-service: modify platform handshake   (owns: PairingSession)
Phase 4 — tizen-player:    create webOS adapter         (pattern: Tizen adapter)
```

#### P3-03 · `ccc workspace plan` command

```
ccc workspace plan "add webOS platform support"
```

Output: `workspace-context/plan.md` with full ordered implementation guide.

-----

### Phase 3 — Simulation + Self-Healing

#### P3-04 · Semantic blast radius

`find_impact()` currently works at module level. Extend to capability level.

- “If PlatformConfig changes, which capabilities in which repos break?”
- Uses consumer index from P2-05
- Depends on P2-02 call graph being complete

#### P3-05 · Graph persistence

- Serialize networkx graph to `.llm-context/dependency-graph.pkl`
- Rebuild only when source changes — faster repeated impact queries

#### P3-06 · Self-healing / model reconciliation

Compare AST reality (routes.txt, schemas) against `capabilities.json` model.

- Detect: stale APIs, missing capabilities, new routes not in model
- `ccc capabilities --check` — report only
- `ccc capabilities --reconcile` — with human review, never silent
- **Critical**: never auto-overwrite human-edited capability descriptions

#### P3-07 · Semantic chunking for large symbol indexes

For repos with 10,000+ symbols, `symbol-index.json` becomes too large to include in full.

- Split by module/package
- Generate `symbol-index-toc.json` as lightweight table of contents
- Agents query TOC first, then fetch relevant chunk
- Each chunk stays under a configurable token budget

#### P3-08 · `ccc context-for <task>` — query-time context assembly

Given a task description, assemble a complete, token-budget-aware context package.

- Uses intent scoring (P2-07) to identify relevant services
- Selects artifacts per service based on task type
- Respects `--budget` token limit, ranks and trims to fit
- CLI: `ccc context-for "add webm support to thumbnail pipeline" --budget 8000`

#### P3-09 · Multi-language call graph (cross-service)

Extend call graph (P2-14) to cross service boundaries.

- Link `service-a` calling `POST /api/encode` → `thumbnail-service` handler function
- Workspace-level call graph, not just per-service
- Depends on P2-14 and P2-15 being complete

#### P3-10 · Incremental symbol index (file-level granularity)

Symbol index regenerates entirely when any source file changes.

- Track per-file symbol extraction in `manifest.json`
- On incremental run, only re-extract changed files
- Merge updated results into existing index
- Validate improvement with timing from P1-05

-----

### Phase 4 — Embeddings + Visualization

#### P3-11 · Embeddings + hybrid retrieval

`ccc query` is purely lexical today — substring matching only.

- Add semantic layer: `sentence-transformers` or API embeddings
- Store: `.llm-context/embeddings.pkl`
- Hybrid: lexical (precise) + semantic (intent-aware)
- Optional dependency — keyword matching must always work standalone

#### P3-12 · Workspace graph visualization in serve UI

Interactive dependency graph.

- Nodes: services, sized by context coverage
- Edges: declared (solid) + discovered/undeclared (dashed with confidence %)
- Color-coded by service type and capability tags
- Views: dependency graph | plan timeline | impact simulation
- Note: React Flow adds npm build step — decide on zero-dep constraint first

#### P3-13 · `ccc analyze-feedback` — feedback pattern aggregation

Reads all `ai-observations.md` and `feedback-log.jsonl` across workspace.

- Clusters observations by keyword (missing, unclear, assumed, hallucinated)
- Produces `feedback-summary.md` per service with concrete improvement suggestions
- Feeds suggestions back into `ccc doctor`
- Depends on P2-27 and P2-28 having accumulated entries

-----

### Tooling & Integration

#### P3-14 · GitHub Actions / CI integration

- Fail PR if `workspace discover` finds new high-confidence undeclared dependencies
- Fail PR if per-service context is stale by more than N days
- Post coverage map diff as PR comment
- Outputs machine-readable JSON for downstream steps

#### P3-15 · VS Code extension

- Status bar item showing context freshness for current repo
- Command palette: “CCC: Copy context for current file” → inserts `#file:` reference
- Hover on service import → show service summary from `external-dependencies.json`
- Depends on serve UI and CLI being stable first

#### P3-16 · MCP server

Serve context directly to Claude and other MCP-compatible agents without file uploads.

- Exposes: symbol lookup, route search, service capabilities, intent resolution
- No file sharing needed — agents query CCC directly

#### P3-17 · Java extractor

- Extract `public` method signatures
- Extract class and interface definitions
- Extract Spring MVC annotations (`@GetMapping`, `@PostMapping`, `@RequestMapping`)
- Parse `pom.xml` or `build.gradle` for dependencies

#### P3-18 · Plugin / extractor API

Allow third-party extractors without modifying CCC source.

- Define `BaseExtractor` as a public API
- Support `ccc_extractors` entry point in `pyproject.toml` for pip-installable extractors
- Unblocks: Kotlin, PHP, Ruby, NestJS patterns, tRPC, Prisma

#### P3-19 · `workspace serve` WebSocket live reload

Proper solution to stale-data problem.

- Watch `workspace-context/service-index.json` for changes using `watchdog`
- Push update event to connected browsers via WebSocket
- Requires `websockets` or stdlib `asyncio` — still zero external frontend deps

#### P3-20 · PyPI release as `ccc-contextcompiler`

- Resolve P1-11 (version management) first
- Add `CHANGELOG.md`
- CI publish workflow on tag

-----

## Summary

|Priority |Count |Focus                                                                          |
|---------|------|-------------------------------------------------------------------------------|
|P1       |11    |Correctness, onboarding, observability — do these first                        |
|P2       |28    |Capability layer (Layers 1–4), LLM efficiency, language coverage, feedback loop|
|P3       |20    |Planning/simulation/self-healing, embeddings, integrations, long-term          |
|**Total**|**59**|                                                                               |

-----

## Architecture Reference

```
Code (AST)
    ↓
Structural Layer   → .llm-context/ artifacts              [EXISTS]
    ↓
Semantic Layer     → capabilities.json per repo           [P2-01 – P2-03]
    ↓
Indexing Layer     → capability-index.json workspace      [P2-04 – P2-05]
    ↓
Reasoning Layer    → IntentResolver, task context         [P2-06 – P2-12]
    ↓
Planning Layer     → CapabilityDiff, FeaturePlanner       [P3-01 – P3-03]
    ↓
Simulation Layer   → blast radius, self-healing           [P3-04 – P3-10]
    ↓
LLMs / Copilot / CI / Tools
```

**Key distinctions:**

- **Tags** = flat projection for filtering (exists, works today)
- **Capabilities** = structured semantic units for reasoning (new, P2 Layer 1)
- **Repos** = implementation details (nodes in the graph)
- **Intent** = human-language entry point to the reasoning chain
- **Self-healing** = capabilities.json vs AST reconciliation — NOT auto-overwrite

**Design principles:**

- Keep capabilities lightweight — avoid full ontology modeling
- Prefer heuristics over LLM early — keyword map must work standalone
- Human refinement always possible — auto-generated is the floor, not the ceiling
- Build incrementally — validate each layer on real repos before building next
- Human approval gates on self-healing — never silently overwrite curated data

-----

*Last updated: 2026-05-29*  
*Source: codebase review of contextcompiler-main v0.1.0 + architecture notes*  
*Delete items as implemented. Pilot project (webOS port) will generate the most valuable calibration data.*
