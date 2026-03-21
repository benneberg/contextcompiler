"""
CCC Query Engine — interrogate .llm-context/ artifacts at runtime.

Instead of reading generated files manually, you ask questions:

    ccc query "UserService"
    ccc query symbol CreateUser
    ccc query route /users
    ccc query impact UserService
    ccc query context "authentication flow"   # LLM-ready output

The engine loads artifacts once and answers multiple queries against
the in-memory index. No re-scanning of source code needed.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .utils.files import safe_read_text
from .utils.formatting import get_timestamp


# ── Data shapes ───────────────────────────────────────────────────────────────

@dataclass
class SymbolMatch:
    name: str
    file: str
    line: int
    kind: str       # class | function | route | type


@dataclass
class RouteMatch:
    method: str
    path: str
    file: Optional[str] = None


@dataclass
class DependencyMatch:
    source: str
    target: str
    raw: str


@dataclass
class QueryResult:
    query: str
    symbols: List[SymbolMatch] = field(default_factory=list)
    routes: List[RouteMatch] = field(default_factory=list)
    dependencies: List[DependencyMatch] = field(default_factory=list)
    public_api: List[str] = field(default_factory=list)
    schemas: List[str] = field(default_factory=list)

    @property
    def total_hits(self) -> int:
        return (len(self.symbols) + len(self.routes) +
                len(self.dependencies) + len(self.public_api) +
                len(self.schemas))

    def is_empty(self) -> bool:
        return self.total_hits == 0


# ── Artifact loaders ──────────────────────────────────────────────────────────

def _load_symbols(context_dir: Path) -> Dict[str, dict]:
    raw = safe_read_text(context_dir / "symbol-index.json")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data.get("symbols", {})
    except json.JSONDecodeError:
        return {}


def _load_routes(context_dir: Path) -> List[RouteMatch]:
    raw = safe_read_text(context_dir / "routes.txt")
    if not raw:
        return []
    routes = []
    current_file = None
    for line in raw.splitlines():
        if line.startswith("##"):
            current_file = line[2:].strip()
            continue
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0].upper() in {
            "GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "ANY"
        }:
            routes.append(RouteMatch(
                method=parts[0].upper(),
                path=parts[1],
                file=current_file,
            ))
    return routes


def _load_dep_graph(context_dir: Path) -> List[DependencyMatch]:
    raw = safe_read_text(context_dir / "dependency-graph.txt")
    if not raw:
        return []
    deps = []
    for line in raw.splitlines():
        if "->" in line:
            parts = line.split("->")
            if len(parts) >= 2:
                src = parts[0].strip().lstrip("#").strip()
                tgt = parts[1].strip()
                if src and tgt:
                    deps.append(DependencyMatch(
                        source=src, target=tgt, raw=line.strip()
                    ))
    return deps


def _load_public_api(context_dir: Path) -> List[str]:
    raw = safe_read_text(context_dir / "public-api.txt")
    if not raw:
        return []
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def _load_schemas(context_dir: Path) -> List[str]:
    """Load schema lines from schemas-extracted.* files."""
    lines = []
    for filename in ["schemas-extracted.py", "types-extracted.ts"]:
        raw = safe_read_text(context_dir / filename)
        if raw:
            for line in raw.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    lines.append(stripped)
    return lines


def _build_dep_graph_nx(deps: List[DependencyMatch]):
    """Build a networkx digraph if available, else None."""
    try:
        import networkx as nx
        g = nx.DiGraph()
        for d in deps:
            g.add_edge(d.source, d.target)
        return g
    except ImportError:
        return None


# ── Query Engine ──────────────────────────────────────────────────────────────

class CCCQueryEngine:
    """
    Runtime query interface over .llm-context/ artifacts.

    Load once, query many times:

        engine = CCCQueryEngine()
        result = engine.query("UserService")
        context = engine.build_llm_context("authentication flow")
        impact = engine.find_impact("UserService")
    """

    def __init__(self, context_dir: str = ".llm-context"):
        self.context_dir = Path(context_dir)

        if not self.context_dir.exists():
            raise FileNotFoundError(
                f"No .llm-context/ found at {self.context_dir}\n"
                f"Run `ccc` first to generate context files."
            )

        self._symbols = _load_symbols(self.context_dir)
        self._routes = _load_routes(self.context_dir)
        self._deps = _load_dep_graph(self.context_dir)
        self._public_api = _load_public_api(self.context_dir)
        self._schemas = _load_schemas(self.context_dir)
        self._graph = _build_dep_graph_nx(self._deps)

    # ── Symbol queries ────────────────────────────────────────────────────────

    def find_symbol(self, name: str) -> Optional[SymbolMatch]:
        """Exact symbol lookup by name."""
        entry = self._symbols.get(name)
        if entry:
            return SymbolMatch(
                name=name,
                file=entry.get("file", ""),
                line=entry.get("line", 0),
                kind=entry.get("kind", "unknown"),
            )
        return None

    def search_symbols(self, query: str) -> List[SymbolMatch]:
        """Case-insensitive substring search across all symbol names."""
        q = query.lower()
        results = []
        for name, entry in self._symbols.items():
            if q in name.lower():
                results.append(SymbolMatch(
                    name=name,
                    file=entry.get("file", ""),
                    line=entry.get("line", 0),
                    kind=entry.get("kind", "unknown"),
                ))
        # Exact matches first, then prefix, then substring
        results.sort(key=lambda s: (
            0 if s.name.lower() == q else
            1 if s.name.lower().startswith(q) else 2,
            s.name
        ))
        return results

    # ── Route queries ─────────────────────────────────────────────────────────

    def find_routes(self, keyword: str) -> List[RouteMatch]:
        """Find routes whose path or method contains keyword."""
        q = keyword.lower()
        return [
            r for r in self._routes
            if q in r.path.lower() or q in r.method.lower()
        ]

    def find_route_exact(self, method: str, path: str) -> Optional[RouteMatch]:
        """Find exact route by method and path."""
        m = method.upper()
        for r in self._routes:
            if r.method == m and r.path == path:
                return r
        return None

    # ── Dependency queries ────────────────────────────────────────────────────

    def find_dependencies(self, keyword: str) -> List[DependencyMatch]:
        """Find dependency edges where keyword appears in source or target."""
        q = keyword.lower()
        return [
            d for d in self._deps
            if q in d.source.lower() or q in d.target.lower()
        ]

    def find_usages(self, symbol: str) -> List[DependencyMatch]:
        """Find all modules that import/use the given symbol or file."""
        q = symbol.lower()
        return [
            d for d in self._deps
            if q in d.target.lower()
        ]

    def find_impact(self, symbol: str) -> Dict[str, Any]:
        """
        What is affected if this symbol/module changes?
        Returns direct and transitive dependents with file locations.

        Uses networkx if available for graph traversal,
        falls back to simple text matching.
        """
        direct: List[str] = []
        transitive: List[str] = []

        if self._graph is not None:
            try:
                import networkx as nx
                # Find the node — match by substring
                matching_nodes = [
                    n for n in self._graph.nodes
                    if symbol.lower() in n.lower()
                ]
                for node in matching_nodes:
                    # Who directly imports this?
                    direct.extend([
                        pred for pred in self._graph.predecessors(node)
                        if pred not in direct
                    ])
                    # Full transitive fan-out
                    ancestors = nx.ancestors(self._graph, node)
                    transitive.extend([
                        a for a in ancestors
                        if a not in direct and a not in transitive
                    ])
            except Exception:
                pass
        else:
            # Fallback: text matching
            for dep in self._deps:
                if symbol.lower() in dep.target.lower():
                    if dep.source not in direct:
                        direct.append(dep.source)

        # Enrich with symbol locations
        def _enrich(names: List[str]) -> List[Dict]:
            result = []
            for name in names:
                sym = self.find_symbol(name)
                result.append({
                    "module": name,
                    "file": sym.file if sym else None,
                    "line": sym.line if sym else None,
                })
            return result

        return {
            "symbol": symbol,
            "direct_dependents": _enrich(direct),
            "transitive_dependents": _enrich(transitive),
            "total_affected": len(direct) + len(transitive),
            "graph_available": self._graph is not None,
        }

    # ── API search ────────────────────────────────────────────────────────────

    def search_public_api(self, keyword: str) -> List[str]:
        """Search public function signatures by keyword."""
        q = keyword.lower()
        return [line for line in self._public_api if q in line.lower()]

    def search_schemas(self, keyword: str) -> List[str]:
        """Search schema/type definitions by keyword."""
        q = keyword.lower()
        return [line for line in self._schemas if q in line.lower()]

    # ── Unified query ─────────────────────────────────────────────────────────

    def query(self, q: str, limit: int = 10) -> QueryResult:
        """
        Unified query across all artifact types.
        Returns ranked results from symbols, routes, deps, API, schemas.
        """
        result = QueryResult(query=q)
        result.symbols = self.search_symbols(q)[:limit]
        result.routes = self.find_routes(q)[:limit]
        result.dependencies = self.find_dependencies(q)[:limit]
        result.public_api = self.search_public_api(q)[:limit]
        result.schemas = self.search_schemas(q)[:limit]
        return result

    # ── LLM context builder ───────────────────────────────────────────────────

    def build_llm_context(
        self,
        query: str,
        max_symbols: int = 10,
        max_routes: int = 10,
        max_api: int = 10,
        max_schemas: int = 8,
        format: str = "markdown",  # markdown | json | compact
    ) -> str:
        """
        Build a focused, ranked context block for pasting into an LLM prompt.

        Instead of dumping entire context files, this queries for relevant
        sections and builds a minimal, precise context window.

        Args:
            query:       Natural language or symbol name to focus on
            max_*:       Result limits per section
            format:      Output format — markdown (default), json, or compact

        Returns:
            A string ready to paste into an LLM prompt as context.
        """
        result = self.query(query)

        if format == "json":
            return self._format_json(query, result, max_symbols,
                                     max_routes, max_api, max_schemas)
        elif format == "compact":
            return self._format_compact(query, result, max_symbols,
                                        max_routes, max_api, max_schemas)
        else:
            return self._format_markdown(query, result, max_symbols,
                                         max_routes, max_api, max_schemas)

    def _format_markdown(
        self, query: str, result: QueryResult,
        max_sym: int, max_routes: int, max_api: int, max_sch: int,
    ) -> str:
        lines = [
            f"# CCC Context: `{query}`",
            f"",
            f"*Focused context extracted from .llm-context/ — "
            f"{result.total_hits} relevant items found.*",
            f"",
        ]

        if result.symbols:
            lines += [f"## Symbols ({len(result.symbols[:max_sym])})", ""]
            for s in result.symbols[:max_sym]:
                lines.append(f"- **`{s.name}`** — {s.kind} in `{s.file}` line {s.line}")
            lines.append("")

        if result.routes:
            lines += [f"## API Routes ({len(result.routes[:max_routes])})", ""]
            for r in result.routes[:max_routes]:
                file_hint = f"  ← `{r.file}`" if r.file else ""
                lines.append(f"- `{r.method} {r.path}`{file_hint}")
            lines.append("")

        if result.public_api:
            lines += [f"## Function Signatures ({len(result.public_api[:max_api])})", ""]
            for sig in result.public_api[:max_api]:
                lines.append(f"- `{sig}`")
            lines.append("")

        if result.schemas:
            lines += [f"## Type Definitions ({len(result.schemas[:max_sch])})", ""]
            for s in result.schemas[:max_sch]:
                lines.append(f"    {s}")
            lines.append("")

        if result.dependencies:
            lines += [f"## Dependencies ({len(result.dependencies[:8])})", ""]
            for d in result.dependencies[:8]:
                lines.append(f"- `{d.source}` → `{d.target}`")
            lines.append("")

        if result.is_empty():
            lines.append(f"*No results found for `{query}`. "
                         f"Try a different term or check that `ccc` has been run.*")

        return "\n".join(lines)

    def _format_json(
        self, query: str, result: QueryResult,
        max_sym: int, max_routes: int, max_api: int, max_sch: int,
    ) -> str:
        data = {
            "query": query,
            "generated": get_timestamp(),
            "total_hits": result.total_hits,
            "symbols": [
                {"name": s.name, "file": s.file, "line": s.line, "kind": s.kind}
                for s in result.symbols[:max_sym]
            ],
            "routes": [
                {"method": r.method, "path": r.path, "file": r.file}
                for r in result.routes[:max_routes]
            ],
            "public_api": result.public_api[:max_api],
            "schemas": result.schemas[:max_sch],
            "dependencies": [
                {"source": d.source, "target": d.target}
                for d in result.dependencies[:8]
            ],
        }
        return json.dumps(data, indent=2)

    def _format_compact(
        self, query: str, result: QueryResult,
        max_sym: int, max_routes: int, max_api: int, max_sch: int,
    ) -> str:
        """Single-line compact format, minimal tokens."""
        parts = [f"[CCC:{query}]"]
        if result.symbols:
            syms = ", ".join(f"{s.name}({s.file}:{s.line})"
                             for s in result.symbols[:max_sym])
            parts.append(f"SYMBOLS:{syms}")
        if result.routes:
            rts = ", ".join(f"{r.method} {r.path}"
                            for r in result.routes[:max_routes])
            parts.append(f"ROUTES:{rts}")
        if result.public_api:
            parts.append(f"API:{'; '.join(result.public_api[:max_api])}")
        return " | ".join(parts)

    # ── Utility ───────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, int]:
        """Quick summary of what's indexed."""
        return {
            "symbols": len(self._symbols),
            "routes": len(self._routes),
            "dependency_edges": len(self._deps),
            "public_api_entries": len(self._public_api),
            "schema_lines": len(self._schemas),
            "graph_nodes": len(self._graph.nodes) if self._graph else 0,
        }