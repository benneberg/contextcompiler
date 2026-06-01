"""
Task context assembly.

Implements `ccc workspace query --intent "task description" --generate`.

Given a natural language task, this module:
1. Scores all services by relevance (same engine as the serve UI intent scoring)
2. Optionally expands to transitive dependencies (--depth 2)
3. Generates workspace-context/task-{slug}/ containing:
     TASK-CONTEXT.md       — which services, why, suggested implementation order
     relevant-symbols.txt  — symbols from matched services matching task keywords
     relevant-routes.txt   — routes from matched services matching task keywords
     change-sequence.md    — ordered implementation plan based on dependency graph

Design: keeps the scoring logic in sync with the JS engine in serve.py
by using the same TECH_HINTS and stopword approach.
"""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .workspace.manifest import WorkspaceManifest
from .utils.files import safe_read_text, safe_write_text
from .utils.formatting import get_timestamp


# ── Mirrors the JS scoring engine in serve.py ─────────────────────────────────

STOPWORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "is", "it", "be", "as", "by", "from", "that", "this", "which", "how", "what",
    "we", "i", "my", "our", "need", "want", "would", "should", "can", "will",
    "support", "add", "fix", "change", "update", "remove", "implement", "create",
    "new", "make", "get", "set", "put", "use", "show", "find", "help", "please",
}

TECH_HINTS: Dict[str, List[str]] = {
    "auth": ["auth", "security", "login", "jwt", "oauth", "session"],
    "user": ["users", "accounts", "profiles", "auth"],
    "payment": ["payments", "billing", "stripe", "checkout"],
    "email": ["notifications", "messaging", "mail", "smtp"],
    "file": ["storage", "media", "upload", "files", "s3", "cdn"],
    "image": ["media", "thumbnail", "storage", "cdn", "s3"],
    "video": ["media", "thumbnail", "encoder", "cdn", "transcode"],
    "webm": ["media", "thumbnail", "encoder", "codec", "transcode", "storage"],
    "mp4": ["media", "encoder", "codec", "transcode"],
    "thumbnail": ["thumbnail", "media", "image", "storage"],
    "notification": ["notifications", "messaging", "email", "push", "alerts"],
    "search": ["search", "index", "elastic", "solr", "query"],
    "cache": ["cache", "redis", "performance", "session"],
    "database": ["database", "data", "models", "schema", "migrations"],
    "queue": ["queue", "jobs", "workers", "async", "messaging", "rabbitmq"],
    "api": ["api", "gateway", "routing", "backend"],
    "frontend": ["frontend", "ui", "web", "react", "vue"],
    "platform": ["platforms", "devices", "adapters", "integration"],
    "websocket": ["realtime", "ws", "socket", "streaming"],
    "webhook": ["integration", "events", "notifications", "api"],
}


def _tokenise(text: str) -> List[str]:
    words = re.sub(r"[^a-z0-9\s]", " ", text.lower()).split()
    return [w for w in words if len(w) > 2 and w not in STOPWORDS]


def _score_service(svc: dict, words: List[str]) -> Tuple[int, List[str]]:
    """Score a service against intent keywords. Returns (score, reasons)."""
    score = 0
    reasons: List[str] = []

    svc_text = " ".join([
        svc.get("name", ""),
        " ".join(svc.get("tags", [])),
        svc.get("description", ""),
        svc.get("type", ""),
        svc.get("framework", "") or "",
    ]).lower()

    api_text = " ".join(svc.get("exposes", {}).get("api", [])).lower()

    for word in words:
        if word in svc.get("name", "").lower():
            score += 40
            reasons.append(f"name match: {word}")

        matched_tags = [t for t in svc.get("tags", [])
                        if word in t.lower() or t.lower() in word]
        if matched_tags:
            score += 25 * len(matched_tags)
            reasons.append(f"tags: {', '.join(matched_tags)}")

        if word in api_text:
            score += 20
            reasons.append(f"api: {word}")

        if word in (svc.get("description") or "").lower():
            score += 15
            reasons.append(f"description: {word}")

        for hint in TECH_HINTS.get(word, []):
            if hint in svc_text:
                score += 12
                reasons.append(f"tech: {word} → {hint}")

    if svc.get("has_context"):
        score += 5

    return score, list(dict.fromkeys(reasons))


def resolve_intent(
    manifest: WorkspaceManifest,
    task: str,
    depth: int = 1,
) -> List[Dict]:
    """
    Score all services by relevance to the task description.
    Returns ranked list of {name, score, reasons, svc} dicts.
    """
    # Load service-index.json for richer data (has_context, exposes etc.)
    index_path = manifest.root / "workspace-context" / "service-index.json"
    services: Dict[str, dict] = {}
    if index_path.exists():
        try:
            data = json.loads(safe_read_text(index_path) or "{}")
            services = data.get("services", {})
        except Exception:
            pass

    # Fall back to manifest-only data
    if not services:
        for name, svc in manifest.services.items():
            services[name] = {
                "name": name,
                "tags": list(svc.tags),
                "description": svc.description or "",
                "type": svc.type or "",
                "depends_on": list(svc.depends_on),
                "path": str(svc.path.relative_to(manifest.root)),
                "has_context": (svc.path / ".llm-context").exists(),
                "exposes": {"api": [], "events": [], "types": []},
            }

    words = _tokenise(task)
    if not words:
        return []

    results = []
    for name, svc in services.items():
        score, reasons = _score_service(svc, words)
        if score > 0:
            results.append({"name": name, "score": score, "reasons": reasons, "svc": svc})

    results.sort(key=lambda x: -x["score"])

    # Depth-2: expand transitive dependencies
    if depth >= 2:
        top_names = {r["name"] for r in results[:4]}
        seen = {r["name"] for r in results}
        for r in list(results[:4]):
            for dep in r["svc"].get("depends_on", []):
                if dep not in seen and dep in services:
                    results.append({
                        "name": dep, "score": 6,
                        "reasons": [f"transitive dep of {r['name']}"],
                        "svc": services[dep],
                    })
                    seen.add(dep)
            # Also include dependents
            for name2, svc2 in services.items():
                if name2 not in seen and r["name"] in svc2.get("depends_on", []):
                    results.append({
                        "name": name2, "score": 5,
                        "reasons": [f"depends on {r['name']}"],
                        "svc": svc2,
                    })
                    seen.add(name2)

    return results


def _topo_sort(names: List[str], services: Dict[str, dict]) -> List[str]:
    """Simple topological sort based on depends_on — leaves first."""
    visited: Set[str] = set()
    order: List[str] = []

    def visit(name: str) -> None:
        if name in visited:
            return
        visited.add(name)
        for dep in services.get(name, {}).get("depends_on", []):
            if dep in services:
                visit(dep)
        order.append(name)

    for name in names:
        visit(name)
    return order


def _extract_relevant_symbols(svc: dict, words: List[str], root: Path) -> List[str]:
    """Extract symbols from this service's symbol-index.json matching the task words."""
    ctx_dir = root / svc.get("path", "") / ".llm-context"
    sym_path = ctx_dir / "symbol-index.json"
    if not sym_path.exists():
        return []
    try:
        data = json.loads(safe_read_text(sym_path) or "{}")
        symbols = data.get("symbols", {})
        matched = []
        for name, info in symbols.items():
            if any(w in name.lower() for w in words):
                kind = info.get("kind", "")
                file_ = info.get("file", "")
                line = info.get("line", "")
                matched.append(f"  {kind:10s} {name}  ({file_}:{line})")
        return matched[:30]
    except Exception:
        return []


def _extract_relevant_routes(svc: dict, words: List[str], root: Path) -> List[str]:
    """Extract routes from routes.txt matching the task words."""
    ctx_dir = root / svc.get("path", "") / ".llm-context"
    routes_path = ctx_dir / "routes.txt"
    if not routes_path.exists():
        # Fall back to exposes.api from service data
        return [f"  {r}" for r in svc.get("exposes", {}).get("api", [])[:15]]
    content = safe_read_text(routes_path) or ""
    matched = []
    for line in content.splitlines():
        if any(w in line.lower() for w in words) or re.search(r"\s(GET|POST|PUT|DELETE|PATCH)\s", line):
            matched.append(f"  {line.strip()}")
    return matched[:20]


def generate_task_context(
    manifest: WorkspaceManifest,
    task: str,
    depth: int = 1,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Generate a task-specific context package.

    Creates workspace-context/task-{slug}/ with:
      TASK-CONTEXT.md       — which services and why
      relevant-symbols.txt  — symbols matching task keywords
      relevant-routes.txt   — routes matching task keywords
      change-sequence.md    — ordered implementation plan

    Returns the output directory path.
    """
    results = resolve_intent(manifest, task, depth=depth)
    words = _tokenise(task)

    if not output_dir:
        output_dir = manifest.root / "workspace-context"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Slug from task text
    slug = re.sub(r"[^a-z0-9]+", "-", task.lower())[:40].strip("-")
    task_dir = output_dir / f"task-{slug}"
    task_dir.mkdir(exist_ok=True)

    # Load services dict for topo sort
    index_path = output_dir / "service-index.json"
    all_services: Dict[str, dict] = {}
    if index_path.exists():
        try:
            data = json.loads(safe_read_text(index_path) or "{}")
            all_services = data.get("services", {})
        except Exception:
            pass

    primary   = [r for r in results if r["score"] >= 20]
    secondary = [r for r in results if r["score"] < 20]
    all_names = [r["name"] for r in results]
    ordered   = _topo_sort(all_names, all_services)

    # ── TASK-CONTEXT.md ───────────────────────────────────────────────────────
    lines = [
        f"# Task Context: {task}",
        f"",
        f"> Generated by CCC on {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"> Dependency depth: {depth}  ",
        f"> {len(results)} service(s) matched",
        f"",
        f"## How to use this",
        f"",
        f"Copy the `#file:` references below into your Copilot / Claude chat,",
        f"then describe your task. The services are ordered by implementation",
        f"dependency (leaf services first).",
        f"",
        f"## Context files",
        f"",
    ]

    for name in ordered:
        r = next((x for x in results if x["name"] == name), None)
        if not r:
            continue
        svc = r["svc"]
        path = svc.get("path", name)
        has_ctx = svc.get("has_context", False)
        tier = "primary" if r["score"] >= 20 else "secondary"
        reasons_str = ", ".join(r["reasons"][:3])

        if has_ctx:
            lines.append(f"```")
            lines.append(f"#file:{path}/.llm-context/LLM.md")
            lines.append(f"```")
        lines.append(f"**{name}** ({tier}, score {r['score']}) — {reasons_str}")
        if not has_ctx:
            lines.append(f"> ⚠ No context — run `ccc` in `{path}` first")
        lines.append(f"")

    if secondary:
        lines += [
            f"## Also relevant (transitive / secondary)",
            f"",
        ]
        for r in secondary:
            svc = r["svc"]
            path = svc.get("path", r["name"])
            reasons_str = ", ".join(r["reasons"][:2])
            lines.append(f"- **{r['name']}** — {reasons_str}")
        lines.append("")

    safe_write_text(task_dir / "TASK-CONTEXT.md", "\n".join(lines))

    # ── relevant-symbols.txt ──────────────────────────────────────────────────
    sym_lines = [
        f"# Relevant Symbols — {task}",
        f"# Generated: {get_timestamp()}",
        f"# Symbols matching task keywords from matched services",
        f"",
    ]
    for r in primary[:5]:  # top 5 services
        syms = _extract_relevant_symbols(r["svc"], words, manifest.root)
        if syms:
            sym_lines.append(f"## {r['name']}")
            sym_lines.extend(syms)
            sym_lines.append("")

    safe_write_text(task_dir / "relevant-symbols.txt", "\n".join(sym_lines))

    # ── relevant-routes.txt ───────────────────────────────────────────────────
    route_lines = [
        f"# Relevant Routes — {task}",
        f"# Generated: {get_timestamp()}",
        f"",
    ]
    for r in primary[:5]:
        routes = _extract_relevant_routes(r["svc"], words, manifest.root)
        if routes:
            route_lines.append(f"## {r['name']}")
            route_lines.extend(routes)
            route_lines.append("")

    safe_write_text(task_dir / "relevant-routes.txt", "\n".join(route_lines))

    # ── change-sequence.md ────────────────────────────────────────────────────
    seq_lines = [
        f"# Change Sequence: {task}",
        f"",
        f"> Implementation order based on dependency graph.",
        f"> Start with leaf services (no dependencies) and work up.",
        f"",
    ]

    for i, name in enumerate(ordered, 1):
        r = next((x for x in results if x["name"] == name), None)
        if not r:
            continue
        svc = r["svc"]
        deps = svc.get("depends_on", [])
        dep_str = f" (after: {', '.join(deps)})" if deps else " (no dependencies — start here)"
        seq_lines.append(f"### Phase {i} — {name}{dep_str}")
        seq_lines.append(f"")
        seq_lines.append(f"- Path: `{svc.get('path', name)}`")
        seq_lines.append(f"- Why: {', '.join(r['reasons'][:3])}")
        if svc.get("exposes", {}).get("api"):
            seq_lines.append(f"- Exposes: {', '.join(svc['exposes']['api'][:3])}")
        if not svc.get("has_context"):
            seq_lines.append(f"- ⚠ Run `ccc` here first to generate context")
        seq_lines.append("")

    safe_write_text(task_dir / "change-sequence.md", "\n".join(seq_lines))

    return task_dir
