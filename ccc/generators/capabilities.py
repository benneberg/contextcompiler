"""
Capability Generator — produces .llm-context/capabilities.json

Reads the artifacts that CCC already generates (routes.txt, schemas-extracted.*,
external-dependencies.json, symbol-index.json) and groups them into logical
capabilities — semantic units that describe what a service *means*, not just
what it *contains*.

This is the foundation of the capability layer. It enables:
  - ccc workspace query "add a new platform"  (intent resolution)
  - capability-index.json aggregation         (workspace reasoning)
  - self-healing / model reconciliation       (drift detection)

Update strategy: if-missing on first run (human edits are preserved).
Force regeneration with: ccc --force
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .base import BaseGenerator
from ..file_index import FileIndex
from ..utils.files import safe_read_text
from ..utils.formatting import get_timestamp


# ── Domain vocabulary — maps code signals to semantic keywords ────────────────
#
# When a service has routes matching /platform or classes named PlatformConfig,
# we infer it has platform-related capabilities. These keywords appear in the
# capabilities.json and enable natural-language intent matching in Layer 3.

_DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    # Domain          # Code signals (route prefixes, class name fragments)
    "platform":       ["platform", "device", "adapter", "player", "signage"],
    "auth":           ["auth", "login", "logout", "token", "session", "permission",
                       "role", "password", "credential", "oauth", "jwt"],
    "user":           ["user", "profile", "account", "member", "subscriber"],
    "content":        ["content", "media", "asset", "playlist", "schedule",
                       "cms", "editorial", "article", "page"],
    "pairing":        ["pair", "pairing", "handshake", "register", "enroll",
                       "device", "activate"],
    "payment":        ["payment", "billing", "invoice", "subscription", "stripe",
                       "checkout", "order", "price"],
    "notification":   ["notification", "push", "email", "sms", "alert", "webhook"],
    "analytics":      ["analytics", "event", "track", "metric", "telemetry",
                       "report", "stat"],
    "search":         ["search", "query", "index", "elastic", "filter", "facet"],
    "data":           ["schema", "migration", "database", "seed", "model", "entity"],
    "gateway":        ["gateway", "proxy", "routing", "load", "balance"],
    "config":         ["config", "setting", "feature", "flag", "env", "preference"],
    "integration":    ["integration", "webhook", "sync", "import", "export",
                       "connector", "bridge"],
    "infra":          ["health", "status", "metrics", "monitor", "deploy",
                       "infra", "docker", "k8s"],
}

# Tag inference from route prefixes and directory names
_TAG_SIGNALS: Dict[str, List[str]] = {
    "platforms":     ["platform", "device", "adapter", "player", "tizen",
                      "webos", "android", "signage"],
    "auth":          ["auth", "login", "session", "token", "permission", "role"],
    "users":         ["user", "profile", "account", "member"],
    "content":       ["content", "media", "playlist", "schedule", "cms"],
    "pairing":       ["pair", "pairing", "handshake", "register", "enroll"],
    "payments":      ["payment", "billing", "stripe", "invoice", "subscription"],
    "notifications": ["notification", "push", "email", "sms", "alert"],
    "analytics":     ["analytics", "track", "metric", "telemetry"],
    "search":        ["search", "query", "elastic", "index"],
    "data":          ["schema", "migration", "database", "seed"],
    "gateway":       ["gateway", "proxy", "routing"],
    "config":        ["config", "setting", "feature", "flag"],
    "shared":        ["shared", "common", "lib", "util", "types"],
    "infra":         ["health", "metrics", "monitor", "deploy"],
    "core":          [],  # added to every service — everything is "core" of something
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _signals_from(text: str) -> Set[str]:
    """Extract lowercase word tokens from any string."""
    return {w.lower() for w in re.split(r"[^a-zA-Z0-9]+", text) if len(w) > 2}


def _infer_tags(signals: Set[str], existing_tags: List[str]) -> List[str]:
    """Infer semantic tags from code signals, merging with any existing tags."""
    tags: Set[str] = set(existing_tags)
    for tag, keywords in _TAG_SIGNALS.items():
        if any(kw in signals for kw in keywords):
            tags.add(tag)
    return sorted(tags)


def _infer_keywords(signals: Set[str]) -> List[str]:
    """Return domain keywords matched by code signals — used for intent matching."""
    matched: Set[str] = set()
    for domain, domain_signals in _DOMAIN_KEYWORDS.items():
        if any(sig in signals for sig in domain_signals):
            matched.add(domain)
    # Also add the top raw signals as keywords (capped to avoid noise)
    meaningful = {s for s in signals
                  if len(s) > 3 and not s.isdigit()
                  and s not in {"from", "import", "return", "class",
                                "function", "const", "this", "self",
                                "true", "false", "null", "none"}}
    return sorted(matched | set(list(meaningful)[:20]))


def _route_prefix(path: str) -> str:
    """Extract the first meaningful path segment: /api/users/123 → users"""
    parts = [p for p in path.strip("/").split("/") if p and p not in ("api", "v1", "v2", "v3")]
    return parts[0].lower() if parts else "root"


def _class_domain(name: str) -> str:
    """Infer domain from a class name: PlatformConfig → platform"""
    for domain, signals in _DOMAIN_KEYWORDS.items():
        if any(sig in name.lower() for sig in signals):
            return domain
    return "general"


# ── Artifact readers ──────────────────────────────────────────────────────────

def _read_routes(context_dir: Path) -> List[Dict]:
    """Parse routes.txt → list of {method, path} dicts."""
    content = safe_read_text(context_dir / "routes.txt") or ""
    routes = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) >= 2 and parts[0].upper() in {
            "GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"
        }:
            routes.append({"method": parts[0].upper(), "path": parts[1]})
    return routes


def _read_schemas(context_dir: Path) -> List[str]:
    """Extract class/interface/enum names from schemas-extracted.* files."""
    names = []
    seen = set()
    for filename in ["schemas-extracted.py", "types-extracted.ts",
                     "rust-types.rs", "go-types.go", "csharp-types.cs"]:
        content = safe_read_text(context_dir / filename) or ""
        for line in content.splitlines():
            m = (re.match(r"^class (\w+)", line) or
                 re.match(r"^export (?:interface|enum|type|class) (\w+)", line) or
                 re.match(r"^pub (?:struct|enum) (\w+)", line) or
                 re.match(r"^type (\w+) struct", line))
            if m:
                name = m.group(1)
                if name not in seen and not name.startswith("_"):
                    seen.add(name)
                    names.append(name)
    return names


def _read_symbols(context_dir: Path) -> Dict[str, dict]:
    """Load symbol-index.json."""
    content = safe_read_text(context_dir / "symbol-index.json") or "{}"
    try:
        data = json.loads(content)
        return data.get("symbols", {})
    except json.JSONDecodeError:
        return {}


def _read_external_deps(context_dir: Path) -> Dict:
    """Load external-dependencies.json."""
    content = safe_read_text(context_dir / "external-dependencies.json") or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


def _read_public_api(context_dir: Path) -> List[str]:
    """Read public-api.txt signatures."""
    content = safe_read_text(context_dir / "public-api.txt") or ""
    return [
        line.strip() for line in content.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


# ── Capability grouping ───────────────────────────────────────────────────────

def _group_routes_into_capabilities(routes: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Group routes by their first meaningful path segment.

    /api/platform/register  → platform
    /api/users/profile      → users
    /health                 → infra
    """
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for route in routes:
        prefix = _route_prefix(route["path"])
        groups[prefix].append(route)
    return dict(groups)


def _group_schemas_into_capabilities(
    schema_names: List[str],
) -> Dict[str, List[str]]:
    """Group schema/class names by detected domain."""
    groups: Dict[str, List[str]] = defaultdict(list)
    for name in schema_names:
        domain = _class_domain(name)
        groups[domain].append(name)
    return dict(groups)


def _build_capability(
    name: str,
    routes: List[Dict],
    schemas: List[str],
    all_signals: Set[str],
    ext_deps: Dict,
    existing_tags: List[str],
) -> Dict:
    """Build a single capability entry."""
    cap_signals = _signals_from(name)
    for r in routes:
        cap_signals |= _signals_from(r["path"])
    for s in schemas:
        cap_signals |= _signals_from(s)

    tags = _infer_tags(cap_signals, existing_tags)
    keywords = _infer_keywords(cap_signals)

    # Build exposes from routes + schemas
    api_routes = [f"{r['method']} {r['path']}" for r in routes]

    # Build consumes from external-dependencies
    consumes_apis = [
        a for a in ext_deps.get("depends_on", {}).get("apis_consumed", [])
        if any(sig in a.lower() for sig in cap_signals)
    ]
    consumes_services = ext_deps.get("depends_on", {}).get("services", [])
    consumes_dbs = ext_deps.get("depends_on", {}).get("databases", [])

    # Exported types relevant to this capability
    exposed_types = [
        s for s in schemas
        if any(sig in s.lower() for sig in cap_signals)
    ][:10]

    exposed_events = [
        e for e in ext_deps.get("exposes", {}).get("events", [])
        if any(sig in e.lower() for sig in cap_signals)
    ]

    return {
        "name": name,
        "description": f"TODO: describe what {name} does",
        "tags": tags,
        "keywords": keywords[:15],
        "owns": schemas[:10],
        "exposes": {
            "api": api_routes,
            "events": exposed_events,
            "types": exposed_types,
        },
        "consumes": {
            "services": consumes_services,
            "apis": consumes_apis[:5],
            "types": [],
        },
    }


# ── CapabilityGenerator ───────────────────────────────────────────────────────

class CapabilityGenerator(BaseGenerator):
    """
    Generate .llm-context/capabilities.json.

    Reads existing CCC artifacts (routes, schemas, symbols, external-deps)
    and groups them into named capability units with tags, keywords, owns,
    exposes, and consumes fields.

    Update strategy: if-missing (human edits are preserved after first generation).
    Use --force to regenerate from scratch.
    """

    def __init__(
        self,
        root: Path,
        config: dict,
        file_index: FileIndex,
        languages: List[str],
        framework: str = "",
        service_name: str = "",
    ):
        super().__init__(root, config)
        self.index = file_index
        self.languages = languages
        self.framework = framework
        self.service_name = service_name or root.name

        # Read from .llm-context/ — these must already exist
        self._context_dir = root / config.get("output_dir", ".llm-context")

    @property
    def output_filename(self) -> str:
        return "capabilities.json"

    def generate(self) -> Tuple[str, List[Path]]:
        data = self._build()
        return json.dumps(data, indent=2), []

    def _build(self) -> Dict:
        """Build the full capabilities.json structure."""
        routes = _read_routes(self._context_dir)
        schema_names = _read_schemas(self._context_dir)
        symbols = _read_symbols(self._context_dir)
        ext_deps = _read_external_deps(self._context_dir)
        public_api = _read_public_api(self._context_dir)

        # Collect all code signals for tag/keyword inference
        all_signals: Set[str] = set()
        for r in routes:
            all_signals |= _signals_from(r["path"])
        for s in schema_names:
            all_signals |= _signals_from(s)
        all_signals |= _signals_from(self.service_name)
        all_signals |= _signals_from(self.framework)

        # Group routes and schemas into capability buckets
        route_groups = _group_routes_into_capabilities(routes)
        schema_groups = _group_schemas_into_capabilities(schema_names)

        # Merge into a unified set of capability names
        cap_names: Set[str] = set(route_groups.keys()) | set(schema_groups.keys())

        # Remove noise names
        noise = {"root", "general", "src", "app", "api", "index"}
        cap_names -= noise

        # If nothing was grouped, fall back to a single capability
        # representing the whole service
        if not cap_names:
            cap_names = {self.service_name}

        # Build capability entries
        capabilities = []
        for name in sorted(cap_names):
            cap_routes = route_groups.get(name, [])
            cap_schemas = schema_groups.get(name, []) + schema_groups.get("general", [])
            # Remove duplicates while preserving order
            seen_schemas: Set[str] = set()
            unique_schemas = []
            for s in cap_schemas:
                if s not in seen_schemas:
                    seen_schemas.add(s)
                    unique_schemas.append(s)

            existing_tags = ext_deps.get("tags", [])
            cap = _build_capability(
                name=name,
                routes=cap_routes,
                schemas=unique_schemas[:8],
                all_signals=all_signals,
                ext_deps=ext_deps,
                existing_tags=existing_tags,
            )

            # Only include capabilities that have something meaningful
            if cap["exposes"]["api"] or cap["owns"] or cap["exposes"]["events"]:
                capabilities.append(cap)

        # If all capabilities were empty, add one covering the whole service
        if not capabilities:
            capabilities.append(_build_capability(
                name=self.service_name,
                routes=routes,
                schemas=schema_names[:10],
                all_signals=all_signals,
                ext_deps=ext_deps,
                existing_tags=ext_deps.get("tags", []),
            ))

        # Service-level signals for top-level tags
        top_tags = _infer_tags(all_signals, ext_deps.get("tags", []))
        top_keywords = _infer_keywords(all_signals)

        return {
            "service": self.service_name,
            "version": "1",
            "generated": get_timestamp(),
            "generated_by": "ccc-capability-generator",
            "note": (
                "Auto-generated by CCC. Review and edit descriptions. "
                "This file uses if-missing strategy — your edits are preserved on re-runs. "
                "Use `ccc --force` to regenerate from scratch."
            ),
            "tags": top_tags,
            "keywords": top_keywords[:20],
            "capabilities": capabilities,
        }