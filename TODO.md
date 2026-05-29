# CCC — Development TODO

## CCC — Improvement Backlog

> Generated from full codebase review.  
> Three priority levels: **P1** (high impact, low-medium effort — do these first), **P2** (high value, more involved), **P3** (longer term / nice-to-have).

-----

## P1 — Do First

*High impact, relatively contained. Each item improves daily usability or fixes a real correctness problem.*

-----

### UX & Onboarding

#### P1-01 · `ccc setup` — Interactive onboarding command

The current multi-step workflow (init → ccc per service → generate → serve) requires reading the README. A single `ccc setup` command should detect the situation (single repo vs. multi-repo), walk the user through choices, and run the right sequence automatically.

- Detect git repos in current directory → suggest workspace mode
- Prompt for workspace name and confirm discovered services
- Run `ccc` per service + `workspace generate` in one go
- End with: “Done. Run `ccc workspace serve` to explore.”
- Reuses all existing logic — pure UX shell

#### P1-02 · Fix audit log append mode (correctness + performance)

Current implementation reads the entire audit.log into memory then rewrites it on every `generate` run. This is O(n) in log size and will silently corrupt logs under concurrent access.

- Replace read-all + rewrite with `open(path, "a")` append mode
- Add max size rotation (e.g. 5MB, keep last N entries)
- Log `workspace serve` page views (currently nothing logged)
- Log which files were actually read during generation

#### P1-03 · Per-generator timing output

No timing information anywhere. On a large repo there is no way to know if `symbol-index` took 50ms or 8 seconds.

- `time.perf_counter()` around each generator future
- Print timing table at end of generation run
- Total wall-clock time in the summary line
- `--profile` flag that dumps full timing breakdown

#### P1-04 · Replace `print()` with structured logging + `--quiet` / `--verbose`

349 `print()` calls with no log levels. CI pipelines and automation cannot suppress noise.

- Replace with `logging.getLogger("ccc")` at appropriate levels (DEBUG / INFO / WARNING / ERROR)
- Add `--quiet` flag (WARNING and above only)
- Add `--verbose` flag (DEBUG level)
- Add `--log-file` flag (useful for watch mode)
- Keep existing console formatting for INFO level so human output is unchanged

#### P1-05 · Security headers on `workspace serve`

The HTTP server sends only `Content-Type`. If the port is forwarded (devcontainer, Docker, VS Code port forwarding) the UI is exposed with no protection.

- Add `X-Frame-Options: DENY`
- Add `X-Content-Type-Options: nosniff`
- Add `Cache-Control: no-store`
- Add `--bind` flag (default: `127.0.0.1`, allow `0.0.0.0` explicitly)
- Add `--token` flag for optional single-use access token in URL

#### P1-06 · `workspace discover` auto-runs during `workspace generate`

The undeclared dependency detection is genuinely valuable but almost no user knows it exists. It reads from already-generated artifacts so there is no extra scan cost.

- Run discovery automatically at end of `workspace generate`
- Print a short summary (N undeclared relationships found)
- Write `workspace-context/discovered-relationships.md` alongside other output
- Add `--skip-discover` flag to opt out

#### P1-07 · `ccc workspace serve` detects stale/missing per-service context

The UI loads silently incomplete when services have outdated or missing `.llm-context/`. Users don’t know what they’re missing.

- Compare `manifest.json` timestamps against last git commit timestamps per service
- Show a “stale context” warning banner in the UI for affected services
- Offer a one-click “regenerate” button that runs `ccc` for that service (via shell command hint or actual subprocess)
- Show clearly which services have no `.llm-context/` at all

#### P1-08 · Version from `pyproject.toml` via `importlib.metadata`

`VERSION = "0.1.0"` is hardcoded in `version.py` and will immediately diverge from `pyproject.toml` on any release.

```python
from importlib.metadata import version, PackageNotFoundError
try:
    VERSION = version("ccc-contextcompiler")
except PackageNotFoundError:
    VERSION = "dev"
```

#### P1-09 · `ccc inspect <file>` — per-file context debugger

No way to see what CCC extracted from a specific file. Essential for debugging why context is incomplete.

- Show: symbols extracted, routes found, imports detected, schema types found
- Show: whether file is included in symbol-index, routes.txt, dependency graph
- Show: file size, last modified, whether it was skipped and why
- Usage: `ccc inspect src/thumbnail/encoder.py`

#### P1-10 · `workspace discover` surfaced inline in serve UI

The discovered-relationships report is written to disk but never shown in the browser UI. Users who don’t know the CLI command never see it.

- Add “Dependencies” tab or panel to serve UI
- Show undeclared relationships with confidence scores and evidence
- Color-coded: red (high confidence undeclared), yellow (medium), green (declared + confirmed)
- Link to relevant service detail pages

-----

### Security & Correctness

#### P1-11 · Deeper secret redaction patterns

Current patterns only catch `KEY=`, `PASSWORD=`, `SECRET=`, `TOKEN=` and Bearer tokens. Many real credential formats are missed.

- Private key blocks: `-----BEGIN RSA PRIVATE KEY-----`
- Connection strings: `postgresql://user:pass@host/db`, `amqp://user:pass@host`
- AWS-style access keys: `AKIA[0-9A-Z]{16}`
- JSON-embedded secrets: `"password": "value"`, `"api_key": "value"`
- Base64-encoded credentials (heuristic: long base64 strings in secret-named vars)
- Apply redaction to `pyproject.toml`, `package.json` copies too, not just `.env.example`

-----

## P2 — Do Next

*High value but more involved. Require new subsystems or significant additions to existing ones.*

-----

### LLM Efficiency

#### P2-01 · `context-manifest.json` — token budget hints per artifact

An LLM agent managing its own context window needs to know artifact sizes before loading them. Currently there is no machine-readable index of what exists and how large it is.

- Generate `context-manifest.json` alongside other artifacts
- Fields per artifact: `filename`, `size_bytes`, `estimated_tokens`, `description`, `last_updated`, `recommended_for` (e.g. “architecture questions”, “function lookup”)
- Enables agents to make informed include/exclude decisions
- Referenced in LLM.md header so agents know it exists

#### P2-02 · Call graph / 2-level function dependency tracing

The symbol index knows what functions exist but not how they call each other. For tasks like “add webm support,” an LLM needs to trace the call path from entry point to codec wrapper.

- Extend Python extractor (AST-based, already uses `ast` module) to record function calls
- Extend TypeScript extractor to record function calls (regex-based is acceptable for 2-level depth)
- Add `call-graph.json` artifact: `{ "process_thumbnail": ["encode_frame", "resize_image"], ... }`
- Annotate symbol-index entries with `calls` and `called_by` arrays
- Limit depth to 2 levels to keep artifact size manageable

#### P2-03 · Cross-file type resolution in TypeScript extractor

Types are extracted per-file but import relationships are not followed. `interface VideoConfig` defined in `types.ts` and imported+extended in `thumbnail.ts` appears as two disconnected things.

- Parse `import` statements in TypeScript extractor
- Build a type resolution map: for each type, record all files that import or extend it
- Annotate `types-extracted.ts` with `// used in: thumbnail.ts, encoder.ts`
- Add `type-graph.json`: `{ "VideoConfig": { "defined_in": "types.ts", "used_in": [...] } }`

#### P2-04 · `change-surface.json` — ranked file relevance for tasks

When an LLM is asked to implement something, the most useful signal is: which files are most likely to need editing.

- Score each file by: import fan-in (how many things import it), recent change frequency (from git log), pattern density (does it contain relevant keywords)
- Output `change-surface.json`: ranked list of files with relevance scores and reasons
- Regenerated on each `ccc` run
- Feeds into intent query in serve UI (see P2-07)

#### P2-05 · LLM.md drift detection — suggest updates without overwriting

LLM.md is generated once (if-missing) and never updated. The codebase changes but the context doc stays frozen. Most users never manually update it.

- On each `ccc` run, compare what would be generated fresh vs. current LLM.md content
- If significant divergence detected, write `LLM.md.suggested-updates` alongside
- Print a short summary: “3 new routes detected since LLM.md was written. Run `ccc --update-llm-md` to review.”
- `--update-llm-md` opens a diff view or appends a dated “Changes since last update” section

#### P2-06 · Negative space / gaps documentation in LLM.md

What the codebase explicitly does NOT do is as important as what it does. LLMs hallucinate plausible-but-absent functions when this is unknown.

- `ccc align` already detects routes in PKML but not in code — expose this in LLM.md
- Add a `## Known Gaps` section to LLM.md scaffold listing: unimplemented PKML items, TODOs extracted from source, missing error handling patterns
- Feed `ai-observations.md` entries (see P2-09) into this section over time

#### P2-07 · Commitability of `service-index.json` — explicit workflow

The file is designed to be committed but there is no guidance and no tooling for it. This blocks the key workflow: teammate clones workspace repo, runs `ccc workspace serve`, gets full picture without cloning all service repos.

- Add `--commit-index` flag to `workspace generate` that stages the file
- Document the workflow explicitly in serve UI: “Share this workspace: commit workspace-context/ to your workspace repo”
- Add staleness warning when service-index.json is older than N days

-----

### Serve UI Improvements

#### P2-08 · Intent query — “what services are relevant to this task?”

A natural language input in the serve UI that maps task descriptions to relevant services and files. No LLM call needed — pure local scoring against indexed data.

- Parse input for: action verbs (add, fix, migrate), technology nouns (webm, redis, oauth), service name fragments
- Score services by: tag match, route keyword match, schema type match, dependency proximity, external-dependencies.json tech match
- Output ranked list: primary services + why, secondary (transitively affected), suggested files
- One-click “Copy workspace for Copilot” button that emits a ready-to-paste `#file:` block with all relevant LLM.md paths

#### P2-09 · Built-in report views in serve UI

The data for these reports already exists — they just need rendering surfaces.

- **Stale Context** — services with old or missing `.llm-context/`, sortable by age
- **Coverage Map** — which services have routes / schemas / symbols / full context vs. partial
- **Schema Drift** — types that exist in multiple services with different fields (from `discover`)
- **Change Impact** — enter a service, see propagation fan-out (what depends on it + transitively)
- **Undeclared Dependencies** — surfaces `discovered-relationships.json` inline (see P1-10)

#### P2-10 · Custom saved views in serve UI

Allow users to save tag filter combinations and view configurations as named views.

- Stored in `localStorage` (no backend needed)
- Saveable from any filtered state: name the current filter set, save it
- Appears in a “Saved Views” sidebar section
- Examples: “My team’s services”, “Auth stack”, “Data pipeline”
- Exportable as a URL hash for sharing

#### P2-11 · Auto-refresh option in serve UI

The UI is a static snapshot. Running `workspace generate` in another terminal while the UI is open shows stale data with no indication.

- `--auto-refresh N` flag (e.g. `--auto-refresh 30` for 30-second polling)
- Or a manual “Refresh” button that re-fetches `service-index.json`
- Show “last updated X seconds ago” in header
- Flash indicator when data changes after a refresh

-----

### Language Coverage

#### P2-12 · Go extractor

Framework detection already identifies gin/fiber but extraction falls back to regex. Go is increasingly common in microservice environments.

- Extract `func` signatures (exported only, i.e. capitalised)
- Extract struct type definitions
- Extract HTTP route registrations (`r.GET`, `r.POST`, gin/fiber patterns)
- Parse `go.mod` for module name and dependencies
- Output format compatible with existing `symbol-index.json` schema

#### P2-13 · Rust extractor

Actix-web and Axum detection already exists. Rust services are common in performance-critical roles (media processing, gateways).

- Extract `pub fn` signatures
- Extract `struct` and `enum` definitions (with `pub` only)
- Extract route macros (`#[get("/path")]`, `#[post("/path")]`)
- Parse `Cargo.toml` for crate name and dependencies

#### P2-14 · C# extractor

C# is prevalent in enterprise environments, especially alongside TypeScript frontends.

- Extract `public` method signatures
- Extract class and interface definitions
- Extract ASP.NET route attributes (`[HttpGet]`, `[Route]`)
- Parse `.csproj` for package dependencies

#### P2-15 · Java extractor

Spring Boot is still the dominant enterprise backend framework.

- Extract `public` method signatures
- Extract class and interface definitions
- Extract Spring MVC annotations (`@GetMapping`, `@PostMapping`, `@RequestMapping`)
- Parse `pom.xml` or `build.gradle` for dependencies

-----

### AI Feedback Loop

#### P2-16 · `ai-observations.md` convention + prompt template

A lightweight convention for LLMs to record what was missing, unclear, or helpful after using CCC context for a task. Builds organic signal over time without requiring any new infrastructure.

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
- `ccc doctor` reads and summarises observations: “3 entries mention missing codec configuration”

#### P2-17 · `ccc feedback` — structured post-session feedback command

A lightweight CLI for recording structured feedback after an AI session.

- Prompts: which services were involved, was context sufficient, what was missing
- Stores in `.llm-context/feedback-log.jsonl`
- `ccc feedback --analyze` summarizes patterns across entries
- Feeds into `ccc doctor` recommendations

-----

## P3 — Longer Term

*Valuable but more complex, or dependent on P2 work being done first. Lower urgency.*

-----

### Advanced LLM Efficiency

#### P3-01 · Semantic chunking for large symbol indexes

For repos with 10,000+ symbols, `symbol-index.json` becomes too large to include in full. Currently there is no chunking strategy.

- Split symbol-index by module/package
- Generate `symbol-index-toc.json` as a lightweight table of contents
- Agents query TOC first, then fetch relevant chunk
- Each chunk stays under a configurable token budget

#### P3-02 · Query-time context assembly — `ccc context-for <task>`

Given a task description, assemble a complete, token-budget-aware context package ready to paste into an AI chat.

- Uses intent scoring from P2-08 to identify relevant services
- Selects artifacts per service based on task type (API task → routes.txt + public-api.txt; schema task → schemas + types)
- Respects a `--budget` token limit, ranks and trims to fit
- Outputs a ready-to-use prompt block with `#file:` references and task framing
- CLI: `ccc context-for "add webm support to thumbnail pipeline" --budget 8000`

#### P3-03 · Multi-language call graph (cross-service)

Extend call graph (P2-02) to cross service boundaries using `external-dependencies.json` APIs as bridge points.

- Link `service-a` calling `POST /api/encode` → `thumbnail-service` handler function
- Produces a workspace-level call graph, not just per-service
- High complexity, requires all services to have context generated
- Depends on P2-02 and P2-03 being complete

#### P3-04 · Incremental symbol index (file-level granularity)

Currently the symbol index regenerates entirely when any source file changes. For large repos with frequent edits this is slow.

- Track per-file symbol extraction in `manifest.json`
- On incremental run, only re-extract changed files
- Merge updated file results into existing index
- Depends on P1-03 (timing) to validate the improvement

-----

### Serve UI — Advanced

#### P3-05 · Workspace graph visualization

A force-directed graph of service dependencies in the serve UI.

- Nodes: services, sized by context coverage
- Edges: declared dependencies (solid) + discovered/undeclared (dashed)
- Color-coded by service type
- Click node → go to service detail
- No external library needed: D3 or a simple canvas implementation
- Useful for understanding topology at a glance, especially for onboarding

#### P3-06 · Serve UI dark/light theme toggle + export to PDF/PNG

Minor but frequently requested for report sharing.

- CSS variable swap for theme
- Print stylesheet for clean PDF export
- “Export report” button for the current view

#### P3-07 · `workspace serve` WebSocket live reload

A proper solution to the stale-data problem (vs. the polling approach in P2-11).

- Watch `workspace-context/service-index.json` for changes using `watchdog`
- Push update event to connected browsers via WebSocket
- Browser reloads data without full page refresh
- Requires `websockets` or stdlib `asyncio` — still zero external frontend deps

-----

### Tooling & Integration

#### P3-08 · GitHub Actions / CI integration

A `ccc-check` action that runs as part of PR workflows.

- Fail PR if `workspace discover` finds new high-confidence undeclared dependencies
- Fail PR if per-service context is stale by more than N days
- Post a comment with the coverage map diff (new routes/schemas detected vs. last run)
- Outputs machine-readable JSON for downstream steps

#### P3-09 · VS Code extension (or Copilot Extension)

Surface CCC data directly inside the editor without switching to the browser.

- Status bar item showing context freshness for the current repo
- Command palette: “CCC: Copy context for current file” → inserts `#file:` reference
- Hover on a service import → show service summary from `external-dependencies.json`
- Depends on serve UI and CLI being stable first

#### P3-10 · `ccc analyze-feedback` — feedback pattern aggregation

Reads all `ai-observations.md` and `feedback-log.jsonl` entries across the workspace and identifies systemic gaps.

- Clusters observations by keyword (missing, unclear, assumed, hallucinated)
- Produces a `feedback-summary.md` per service with concrete improvement suggestions
- Feeds suggestions back into `ccc doctor` recommendations
- Depends on P2-16 and P2-17 having accumulated entries

#### P3-11 · Plugin / extractor API

Allow third-party extractors to be registered without modifying CCC source.

- Define `BaseExtractor` interface as a public API
- Support `ccc_extractors` entry point in `pyproject.toml` for pip-installable extractors
- Example: a `ccc-extractor-kotlin` package that adds Kotlin support
- Useful for enterprise environments with internal languages or conventions

-----

## Summary Count

|Priority |Count |Focus                                                        |
|---------|------|-------------------------------------------------------------|
|P1       |11    |Correctness, onboarding, observability, quick wins           |
|P2       |17    |LLM efficiency, language coverage, UI features, feedback loop|
|P3       |11    |Advanced features, integrations, long-term architecture      |
|**Total**|**39**|                                                             |

-----

*Last updated: 2026-05-29*  
*Source: full codebase review of contextcompiler-main v0.1.0*
---

## 🧠 Capability Layer — Core Upgrade
> Evolves CCC from "context tool" to "reasoning engine over distributed codebases"
> Implement in strict order — each layer depends on the previous

### Layer 1 — capabilities.json (Foundation)
> Makes repos self-describing at a semantic level, not just structural

- [ ] Define capabilities.json schema and add to docs/
      Richer than external-dependencies.json: adds keywords, owns, capability grouping

      Target schema per repo (.llm-context/capabilities.json):
        service, version, generated
        capabilities[]:
          name, description
          tags[]      — for filtering (connects to existing tag system)
          keywords[]  — for intent matching ("platform", "adapter", "device")
          owns[]      — domain classes this capability owns (e.g. PlatformConfig)
          exposes:    api[], events[], types[]
          consumes:   services[], apis[], types[]

- [ ] Add CapabilityGenerator to ccc/generators/capabilities.py
      Reads: routes.txt, schemas-extracted.*, external-dependencies.json,
             symbol-index.json
      Groups routes and schemas into logical capabilities by prefix/namespace
      Auto-suggests tags and keywords from route patterns and class names
      Uses if-missing update strategy — human edits are preserved after first run

- [ ] Wire CapabilityGenerator into generator.py
- [ ] Add capabilities.json to service-index.json aggregation in workspace/index.py
- [ ] Update workspace serve UI to show capabilities per service card

### Layer 2 — Capability Index (Workspace Reasoning Foundation)
> Aggregates all capabilities.json into a queryable workspace index

- [ ] Build workspace-level capability index
      Generated by: ccc workspace generate (extend existing)
      Output: workspace-context/capability-index.json
      Contains:
        by_tag: { "platforms": { repos[], capabilities[] } }
        by_keyword: { "platform": ["pairing-service", "cms"] }
        by_api: { "POST /api/pairing/initiate": "pairing-service" }
        by_type: { "PlatformConfig": ["pairing-service", "cms"] }
        by_owner: { "PairingSession": "pairing-service" }

- [ ] Build consumer index alongside capability index
      Maps: each API/type → which repos consume it
      Enables: "what would break if PlatformConfig changes?"
      This is the structural foundation for semantic blast radius (Phase 3)

### Layer 3 — Intent Resolver (Natural Language → Repos)
> The missing decision layer: maps human intent to relevant repos

- [ ] Add intent_keywords config to ccc-workspace.yml schema
      Curated map from domain vocabulary to tags:
        intent_keywords:
          platform: [platforms, devices, adapters]
          auth: [authentication, security, login]
          user: [users, profiles, accounts]
      This is the human-maintained fallback — no LLM required

- [ ] Implement IntentResolver in ccc/workspace/intent.py
      Input: natural language string
      Step 1: tokenize, remove stopwords
      Step 2: match tokens against capability keywords (from capability-index.json)
      Step 3: match against intent_keywords config
      Step 4: score repos by match count, return ranked with explanations
      Step 5: expand via dependency graph (include deps and dependents)
      Output: ranked repo list with confidence + which keywords matched

- [ ] Update CLI: ccc workspace query accepts free text
      ccc workspace query "add a new platform"
      Resolves to tags automatically, shows reasoning:
        "Matched keyword 'platform' → tags: [platforms, devices]
         Found 3 repos: pairing-service (0.92), cms (0.88), tizen-player (0.75)"

- [ ] Optional LLM upgrade path
      If ANTHROPIC_API_KEY or OPENAI_API_KEY configured, use LLM for intent extraction
      Falls back to keyword map gracefully without key
      Never required — keyword map must always work standalone

### Layer 4 — Task Context Assembly
> Generates task-specific workspace context, not just generic cross-repo context

- [ ] Task context generation
      ccc workspace query "add a new platform" --generate
      Produces workspace-context/task-{slug}/
        TASK-CONTEXT.md       which repos, why matched, implementation order
        relevant-symbols.txt  symbols from all repos matching intent
        relevant-routes.txt   routes matching intent across repos
        change-sequence.md    ordered implementation plan for this task

- [ ] Depth-aware dependency expansion
      --depth 1  direct deps/dependents only (default)
      --depth 2  transitive (full blast radius context)

---

## 🚀 Phase 2 — Planning Layer
> Build after Layers 1-4 validated on real repos

- [ ] CapabilityDiff: compare intent against current capabilities
      "add webOS platform" → identifies per repo: modify | create | no change
      Flags capability gaps: intent mentions something no repo currently owns

- [ ] FeaturePlanner: generate ordered per-repo task list
      Uses: owns field to locate which file to change
      Output example:
        Phase 1 — shared-types:    modify Platform enum (owns: Platform)
        Phase 2 — cms:             modify platform config (owns: PlatformConfig)
        Phase 3 — pairing-service: modify platform handshake (owns: PairingSession)
        Phase 4 — tizen-player:    create webOS adapter (pattern: Tizen adapter)

- [ ] ccc workspace plan command
      ccc workspace plan "add webOS platform support"
      Output: workspace-context/plan.md with full ordered implementation guide

---

## 🚀 Phase 3 — Simulation + Self-Healing
> Build after Planning Layer validated

- [ ] Semantic blast radius
      find_impact() currently works at module level (dependency-graph.txt)
      Extend: "if PlatformConfig changes, which capabilities in which repos break?"
      Uses consumer index from Layer 2

- [ ] Self-healing / model reconciliation
      Compare AST reality (routes.txt, schemas) against capabilities.json model
      Detect: stale APIs, missing capabilities, new routes not in model
      Run as: ccc capabilities --check (report only)
      Apply as: ccc capabilities --reconcile (with human review, never silent)
      CRITICAL: never auto-overwrite human-edited capability descriptions

- [ ] Graph persistence
      Serialize networkx graph to .llm-context/dependency-graph.pkl
      Rebuild only when source changes — faster repeated impact queries

---

## 🚀 Phase 4 — Embeddings + Visualization
> Biggest remaining capability gap

- [ ] Embeddings + hybrid retrieval
      ccc query is purely lexical today — substring matching only
      Add semantic layer: sentence-transformers or API embeddings
      Store: .llm-context/embeddings.pkl
      Hybrid: lexical (precise) + semantic (intent-aware)

- [ ] Enhanced workspace serve UI graph view
      Interactive dependency graph: repos, capabilities, APIs as nodes
      Edges: declared (solid), discovered (dashed with %), capability ownership
      Views: dependency graph | plan timeline | impact simulation
      Note: React Flow adds npm build step — decide on zero-dep constraint first

- [ ] TypeScript full AST extraction
      Current TS uses regex — adequate but imprecise
      Use tree-sitter-typescript (Python binding, no Node.js required)
      Do NOT use ts-morph — requires Node.js sidecar, breaks zero-dep philosophy

---

## 🔵 Later

- [ ] GitHub automation: auto-PR when ccc align detects drift
- [ ] VSCode extension (real extension, not just config files)
- [ ] MCP server: serve context directly to Claude without file uploads
- [ ] Plugin model for custom language extractors
- [ ] Java / Kotlin / PHP / Ruby extractors
- [ ] NestJS, tRPC, Next.js App Router, Prisma framework patterns
- [ ] PyPI release as ccc-contextcompiler

---

## Architecture Reference

```
Code (AST)
    ↓
Structural Layer  → .llm-context/ artifacts          [EXISTS]
    ↓
Semantic Layer    → capabilities.json per repo        [Layer 1 — NEW]
    ↓
Indexing Layer    → capability-index.json workspace   [Layer 2 — NEW]
    ↓
Reasoning Layer   → IntentResolver, task context      [Layer 3-4 — NEW]
    ↓
Planning Layer    → CapabilityDiff, FeaturePlanner     [Phase 2]
    ↓
Simulation Layer  → semantic blast radius, self-heal  [Phase 3]
    ↓
LLMs / Copilot / CI / Tools
```

Key distinctions:
  Tags        = flat projection for filtering (exists, works today)
  Capabilities = structured semantic units for reasoning (new, Layer 1)
  Repos       = implementation details (nodes in the graph)
  Intent      = human-language entry point to the reasoning chain
  Self-healing = capabilities.json vs AST reconciliation, NOT auto-overwrite

Design principles:
  Keep capabilities lightweight — avoid full ontology modeling
  Prefer heuristics over LLM early — keyword map must work standalone
  Human refinement always possible — auto-generated is the floor, not the ceiling
  Build incrementally — validate each layer on real repos before building next
  Human approval gates on self-healing — never silently overwrite curated data

---

> Delete items as implemented.
> Pilot project (webOS port) will generate the most valuable calibration data.
> Do not start Phase 2 until Layers 1-4 are validated on real repos.
> The capability layer is the difference between a context tool and a reasoning engine.
