"""
ccc workspace discover — find undeclared cross-repo relationships.

Reads .llm-context/ artifacts that CCC already generates and
cross-references them across services to surface hidden coupling.

No re-scanning of source code needed — all raw material is already
in the artifacts. This sits above individual ccc runs.

Usage:
    ccc workspace discover
    ccc workspace discover --tags platforms
    ccc workspace discover --min-confidence 0.7
    ccc workspace discover --output workspace-context/

Output:
    workspace-context/
    ├── discovered-relationships.json   machine-readable, full detail
    └── discovered-relationships.md     human-readable report
"""

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..models import ServiceConfig
from ..utils.files import safe_read_text, safe_write_text
from ..utils.formatting import get_timestamp
from .manifest import WorkspaceManifest


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class DiscoveredRelationship:
    """A relationship found by analyzing artifacts, not declared in manifest."""
    source: str          # service that depends on / is coupled to target
    target: str          # service being depended on
    rel_type: str        # api_call | shared_schema | schema_drift | shared_infra | event_coupling
    confidence: float    # 0.0 - 1.0
    evidence: str        # human-readable explanation
    declared: bool       # was this already in the manifest?
    detail: dict = field(default_factory=dict)  # type-specific detail


@dataclass
class ServiceArtifacts:
    """All .llm-context/ artifacts loaded for one service."""
    name: str
    path: Path
    routes: List[Dict]               # parsed from routes.txt
    schemas: List[Dict]              # parsed from schemas-extracted.*
    external_deps: Dict              # parsed from external-dependencies.json
    env_vars: List[str]              # parsed from env-shape.txt
    has_context: bool = False        # whether .llm-context/ exists


# ── Artifact parsers ──────────────────────────────────────────────────────────

def _parse_routes_txt(content: str) -> List[Dict]:
    """Parse routes.txt into list of {method, path} dicts."""
    routes = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("##"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0].upper() in {
            "GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"
        }:
            routes.append({"method": parts[0].upper(), "path": parts[1]})
        elif len(parts) == 1 and parts[0].startswith("/"):
            routes.append({"method": "ANY", "path": parts[0]})
    return routes


def _parse_schemas(context_dir: Path) -> List[Dict]:
    """
    Parse schema names and field lists from schemas-extracted.py or
    types-extracted.ts. Returns list of {name, kind, fields} dicts.
    """
    schemas = []

    for filename in ["schemas-extracted.py", "types-extracted.ts"]:
        content = safe_read_text(context_dir / filename)
        if not content:
            continue

        current: Optional[Dict] = None
        for line in content.splitlines():
            # Python: class Foo(BaseModel): / class Foo(str, Enum):
            py_class = re.match(r"^class (\w+)\(([^)]+)\):", line)
            # TypeScript: export interface Foo { / export enum Foo {
            ts_iface = re.match(r"^export (?:interface|type|enum|class) (\w+)", line)
            # Dataclass / TypedDict
            py_dc = re.match(r"^class (\w+)(?:\(TypedDict\)|\(Protocol\))?:", line)

            matched_name = None
            matched_kind = "class"
            if py_class:
                matched_name = py_class.group(1)
                base = py_class.group(2).lower()
                matched_kind = "enum" if "enum" in base else "model"
            elif ts_iface:
                matched_name = ts_iface.group(1)
                raw = line.split()
                matched_kind = raw[2] if len(raw) > 2 else "interface"

            if matched_name and not matched_name.startswith("_"):
                if current:
                    schemas.append(current)
                current = {"name": matched_name, "kind": matched_kind, "fields": []}
                continue

            # Collect field names
            if current:
                # Python field: name: type or name = value
                py_field = re.match(r"^\s{4}(\w+)\s*[=:]", line)
                # TS field: name: type; or name?: type;
                ts_field = re.match(r"^\s+(\w+)\??\s*:", line)
                f = py_field or ts_field
                if f:
                    fname = f.group(1)
                    if fname not in {"def", "class", "return", "self",
                                     "cls", "pass", "raise", "if", "else"}:
                        current["fields"].append(fname)
                elif line.strip() == "" and current:
                    schemas.append(current)
                    current = None

        if current:
            schemas.append(current)

    # Deduplicate by name
    seen = {}
    for s in schemas:
        if s["name"] not in seen:
            seen[s["name"]] = s
    return list(seen.values())


def _parse_env_shape(content: str) -> List[str]:
    """Extract env var names from env-shape.txt."""
    vars_found = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            var = line.split("=")[0].strip()
            if var and var.isupper():
                vars_found.append(var)
    return vars_found


def _load_artifacts(service: ServiceConfig) -> ServiceArtifacts:
    """Load all .llm-context/ artifacts for a service."""
    ctx_dir = service.path / ".llm-context"
    has_context = ctx_dir.exists()

    if not has_context:
        return ServiceArtifacts(
            name=service.name,
            path=service.path,
            routes=[], schemas=[], external_deps={}, env_vars=[],
            has_context=False,
        )

    routes_txt = safe_read_text(ctx_dir / "routes.txt") or ""
    routes = _parse_routes_txt(routes_txt)

    schemas = _parse_schemas(ctx_dir)

    ext_raw = safe_read_text(ctx_dir / "external-dependencies.json") or "{}"
    try:
        ext_deps = json.loads(ext_raw)
    except json.JSONDecodeError:
        ext_deps = {}

    env_txt = safe_read_text(ctx_dir / "env-shape.txt") or ""
    env_vars = _parse_env_shape(env_txt)

    return ServiceArtifacts(
        name=service.name,
        path=service.path,
        routes=routes,
        schemas=schemas,
        external_deps=ext_deps,
        env_vars=env_vars,
        has_context=True,
    )


# ── Route normalization ───────────────────────────────────────────────────────

def _normalize_route(path: str) -> str:
    """
    Normalize route patterns so they can be matched across services.
    /api/v1/users/:id  →  /users/{id}
    /api/v2/users/{id} →  /users/{id}
    POST /api/users    →  /users
    """
    # Strip method prefix if present
    parts = path.strip().split()
    path = parts[-1] if parts else path

    # Strip version prefix /api/v1, /api/v2, /v1, /v2
    path = re.sub(r"^/api/v\d+", "", path)
    path = re.sub(r"^/v\d+", "", path)

    # Normalize Express :param style → {param}
    path = re.sub(r":(\w+)", r"{\1}", path)

    # Strip trailing slash
    path = path.rstrip("/") or "/"
    return path


def _routes_match(route_a: str, route_b: str) -> float:
    """
    Return a match score 0.0-1.0 between two route paths.
    Exact match after normalization = 1.0
    Partial path match = 0.6
    """
    na = _normalize_route(route_a)
    nb = _normalize_route(route_b)

    if na == nb:
        return 1.0

    # One is a prefix of the other (gateway proxying)
    if nb.startswith(na) or na.startswith(nb):
        return 0.75

    # Last segment matches (e.g. /users vs /api/users)
    seg_a = na.split("/")[-1]
    seg_b = nb.split("/")[-1]
    if seg_a and seg_b and seg_a == seg_b:
        return 0.6

    return 0.0


# ── Discovery methods ─────────────────────────────────────────────────────────

class CrossRepoDiscovery:
    """
    Analyze .llm-context/ artifacts across repos to discover
    undeclared cross-repo relationships.

    Reads only what CCC already generated — no re-scanning needed.
    """

    def __init__(self, manifest: WorkspaceManifest, min_confidence: float = 0.5):
        self.manifest = manifest
        self.min_confidence = min_confidence
        self._declared = self._build_declared_set()

    def _build_declared_set(self) -> set:
        """Build set of (source, target) pairs already in manifest."""
        declared = set()
        for name, svc in self.manifest.services.items():
            for dep in svc.depends_on:
                declared.add((name, dep))
        return declared

    def _is_declared(self, source: str, target: str) -> bool:
        return (source, target) in self._declared

    def discover(
        self, services: Optional[List[ServiceConfig]] = None
    ) -> List[DiscoveredRelationship]:
        """
        Run all discovery methods across the given services.
        Returns relationships sorted by confidence descending.
        """
        if services is None:
            services = list(self.manifest.services.values())

        # Load artifacts for all services
        artifacts: Dict[str, ServiceArtifacts] = {}
        print(f"\n  Loading artifacts from {len(services)} service(s)...")
        for svc in services:
            art = _load_artifacts(svc)
            artifacts[svc.name] = art
            status = "✓" if art.has_context else "⚠ no .llm-context/"
            print(f"    {svc.name:30s} {status}")

        print(f"\n  Running discovery analysis...")

        relationships: List[DiscoveredRelationship] = []

        # Method 1: API consumer → provider matching
        found = self._match_api_consumers_to_providers(artifacts)
        print(f"    API route matching:       {len(found)} relationship(s)")
        relationships.extend(found)

        # Method 2: Schema drift / shared types
        found = self._detect_schema_relationships(artifacts)
        print(f"    Schema cross-reference:   {len(found)} relationship(s)")
        relationships.extend(found)

        # Method 3: Shared infrastructure via env vars
        found = self._detect_shared_infrastructure(artifacts)
        print(f"    Shared infrastructure:    {len(found)} relationship(s)")
        relationships.extend(found)

        # Method 4: Event coupling
        found = self._detect_event_coupling(artifacts)
        print(f"    Event coupling:           {len(found)} relationship(s)")
        relationships.extend(found)

        # Filter by confidence and deduplicate
        relationships = [r for r in relationships if r.confidence >= self.min_confidence]
        relationships = self._deduplicate(relationships)
        relationships.sort(key=lambda r: r.confidence, reverse=True)

        return relationships

    def _match_api_consumers_to_providers(
        self, artifacts: Dict[str, ServiceArtifacts]
    ) -> List[DiscoveredRelationship]:
        """
        Cross-reference routes.txt from each service against
        apis_consumed in other services' external-dependencies.json.

        If service A calls POST /api/auth/login and service B
        exposes POST /api/auth/login — that's a dependency.
        """
        relationships = []

        # Build provider map: normalized route → (service_name, original_route, method)
        provider_map: Dict[str, List[Tuple[str, str, str]]] = {}
        for name, art in artifacts.items():
            for route in art.routes:
                norm = _normalize_route(route["path"])
                if norm not in provider_map:
                    provider_map[norm] = []
                provider_map[norm].append((name, route["path"], route["method"]))

        # Also build from external-dependencies.json exposes.api
        for name, art in artifacts.items():
            for exposed in art.external_deps.get("exposes", {}).get("api", []):
                norm = _normalize_route(exposed)
                if norm not in provider_map:
                    provider_map[norm] = []
                entry = (name, exposed, exposed.split()[0] if " " in exposed else "ANY")
                if entry not in provider_map[norm]:
                    provider_map[norm].append(entry)

        # Check each service's consumed APIs against provider map
        for consumer_name, art in artifacts.items():
            consumed = art.external_deps.get("depends_on", {}).get("apis_consumed", [])

            for consumed_route in consumed:
                consumed_norm = _normalize_route(consumed_route)
                best_match_score = 0.0
                best_providers: List[Tuple[str, str]] = []

                for provider_norm, providers in provider_map.items():
                    score = _routes_match(consumed_norm, provider_norm)
                    if score > best_match_score:
                        best_match_score = score
                        best_providers = [
                            (p[0], p[1]) for p in providers
                            if p[0] != consumer_name
                        ]

                for provider_name, provider_route in best_providers:
                    if provider_name == consumer_name:
                        continue
                    relationships.append(DiscoveredRelationship(
                        source=consumer_name,
                        target=provider_name,
                        rel_type="api_call",
                        confidence=round(best_match_score * 0.95, 2),
                        evidence=(
                            f"{consumer_name} calls `{consumed_route}` "
                            f"→ matched to `{provider_route}` in {provider_name}"
                        ),
                        declared=self._is_declared(consumer_name, provider_name),
                        detail={
                            "consumer_calls": consumed_route,
                            "provider_exposes": provider_route,
                            "match_score": best_match_score,
                        },
                    ))

        # Also match env var service URLs against service names
        # e.g. AUTH_SERVICE_URL → auth-service
        for consumer_name, art in artifacts.items():
            for env_var in art.env_vars:
                # AUTH_SERVICE_URL, USER_SERVICE_URL, PAYMENT_SERVICE_HOST etc.
                m = re.match(
                    r"^([A-Z][A-Z0-9]+)_SERVICE_(?:URL|HOST|ADDR|PORT|BASE)$",
                    env_var
                )
                if not m:
                    continue
                service_hint = m.group(1).lower().replace("_", "-")

                # Try to match hint to a known service
                for candidate_name in artifacts:
                    if candidate_name == consumer_name:
                        continue
                    # e.g. "auth" matches "auth-service"
                    if (service_hint in candidate_name or
                            candidate_name.startswith(service_hint)):
                        relationships.append(DiscoveredRelationship(
                            source=consumer_name,
                            target=candidate_name,
                            rel_type="api_call",
                            confidence=0.72,
                            evidence=(
                                f"{consumer_name} has env var `{env_var}` "
                                f"→ likely connects to {candidate_name}"
                            ),
                            declared=self._is_declared(consumer_name, candidate_name),
                            detail={"env_var": env_var},
                        ))

        return relationships

    def _detect_schema_relationships(
        self, artifacts: Dict[str, ServiceArtifacts]
    ) -> List[DiscoveredRelationship]:
        """
        Compare schemas across services to find shared or diverged types.

        - Identical schema in two services → likely shared type (possible source of truth issue)
        - Same name, different fields → schema drift (high-risk inconsistency)
        - One is subset of other → likely one service owns it
        """
        relationships = []

        # Group schema names across services
        by_name: Dict[str, List[Tuple[str, Dict]]] = {}
        for svc_name, art in artifacts.items():
            for schema in art.schemas:
                name = schema["name"]
                if len(name) < 3:  # skip trivial names
                    continue
                by_name.setdefault(name, []).append((svc_name, schema))

        for schema_name, locations in by_name.items():
            if len(locations) < 2:
                continue

            for i, (svc_a, schema_a) in enumerate(locations):
                for svc_b, schema_b in locations[i + 1:]:
                    if svc_a == svc_b:
                        continue

                    fields_a = set(schema_a.get("fields", []))
                    fields_b = set(schema_b.get("fields", []))

                    if not fields_a and not fields_b:
                        # Both empty (e.g. bare enums) — lower confidence
                        confidence = 0.5
                        rel_type = "shared_schema"
                        evidence = (
                            f"Type `{schema_name}` exists in both "
                            f"{svc_a} and {svc_b} (no field detail available)"
                        )
                    elif fields_a == fields_b:
                        confidence = 0.82
                        rel_type = "shared_schema_identical"
                        evidence = (
                            f"Type `{schema_name}` is identical in {svc_a} and {svc_b} "
                            f"({len(fields_a)} fields) — consider sharing a single source"
                        )
                    elif fields_a.issubset(fields_b) or fields_b.issubset(fields_a):
                        smaller, larger = (
                            (svc_a, svc_b) if len(fields_a) < len(fields_b)
                            else (svc_b, svc_a)
                        )
                        confidence = 0.68
                        rel_type = "shared_schema_subset"
                        evidence = (
                            f"Type `{schema_name}` in {smaller} is a subset of "
                            f"{larger}'s version — possible intentional slimming or drift"
                        )
                    else:
                        only_a = fields_a - fields_b
                        only_b = fields_b - fields_a
                        confidence = 0.75
                        rel_type = "schema_drift"
                        evidence = (
                            f"Type `{schema_name}` has diverged: "
                            f"{svc_a} has {{{', '.join(sorted(only_a)[:3])}}} "
                            f"not in {svc_b}, and vice versa "
                            f"{{{', '.join(sorted(only_b)[:3])}}}"
                        )

                    relationships.append(DiscoveredRelationship(
                        source=svc_a,
                        target=svc_b,
                        rel_type=rel_type,
                        confidence=confidence,
                        evidence=evidence,
                        declared=self._is_declared(svc_a, svc_b),
                        detail={
                            "schema_name": schema_name,
                            "fields_a": sorted(fields_a),
                            "fields_b": sorted(fields_b),
                            "only_in_source": sorted(fields_a - fields_b),
                            "only_in_target": sorted(fields_b - fields_a),
                        },
                    ))

        return relationships

    def _detect_shared_infrastructure(
        self, artifacts: Dict[str, ServiceArtifacts]
    ) -> List[DiscoveredRelationship]:
        """
        Compare env-shape.txt across services.
        Services sharing infrastructure patterns (same DB, cache, queue)
        have implicit coupling even without direct API calls.
        """
        relationships = []

        infra_patterns: Dict[str, List[str]] = {
            "database":     ["DATABASE_URL", "DB_HOST", "DB_NAME", "POSTGRES_",
                             "MYSQL_", "MONGO_URI", "MONGO_URL"],
            "cache":        ["REDIS_URL", "REDIS_HOST", "MEMCACHED_URL"],
            "queue":        ["KAFKA_", "RABBITMQ_URL", "SQS_", "AMQP_URL",
                             "CELERY_BROKER"],
            "storage":      ["S3_BUCKET", "STORAGE_BUCKET", "BLOB_CONTAINER",
                             "GCS_BUCKET"],
            "auth":         ["JWT_SECRET", "AUTH0_", "OAUTH_SECRET", "API_SECRET"],
        }

        # For each service, find which infra types it uses
        service_infra: Dict[str, Dict[str, List[str]]] = {}
        for svc_name, art in artifacts.items():
            service_infra[svc_name] = {}
            for infra_type, patterns in infra_patterns.items():
                matching = [
                    v for v in art.env_vars
                    if any(p in v for p in patterns)
                ]
                if matching:
                    service_infra[svc_name][infra_type] = matching

        # Find services sharing infra types
        services = list(service_infra.keys())
        for i, svc_a in enumerate(services):
            for svc_b in services[i + 1:]:
                for infra_type in infra_patterns:
                    vars_a = service_infra[svc_a].get(infra_type, [])
                    vars_b = service_infra[svc_b].get(infra_type, [])
                    if not vars_a or not vars_b:
                        continue

                    # Check if they likely share the SAME instance
                    # by looking for identical var names
                    shared_var_names = set(vars_a) & set(vars_b)

                    if shared_var_names:
                        confidence = 0.7  # same var name = likely same instance
                        note = f"share env var(s): {', '.join(sorted(shared_var_names))}"
                    else:
                        confidence = 0.45  # same type but might be different instances
                        note = (
                            f"{svc_a} has {vars_a[0]}, "
                            f"{svc_b} has {vars_b[0]}"
                        )

                    relationships.append(DiscoveredRelationship(
                        source=svc_a,
                        target=svc_b,
                        rel_type=f"shared_{infra_type}",
                        confidence=confidence,
                        evidence=(
                            f"{svc_a} and {svc_b} both use {infra_type} — {note}"
                        ),
                        declared=self._is_declared(svc_a, svc_b),
                        detail={
                            "infra_type": infra_type,
                            "source_vars": vars_a,
                            "target_vars": vars_b,
                        },
                    ))

        return relationships

    def _detect_event_coupling(
        self, artifacts: Dict[str, ServiceArtifacts]
    ) -> List[DiscoveredRelationship]:
        """
        Cross-reference events exposed by one service against
        events that might be consumed by another.

        Uses external-dependencies.json exposes.events.
        """
        relationships = []

        # Build event provider map
        event_providers: Dict[str, str] = {}
        for svc_name, art in artifacts.items():
            for event in art.external_deps.get("exposes", {}).get("events", []):
                event_providers[event.lower()] = svc_name

        if not event_providers:
            return relationships

        # Look for consumers — services whose code references known event names
        # (only possible if we have the source, otherwise skip)
        # This is a lighter signal — just note where shared events exist
        for svc_name, art in artifacts.items():
            consumed_events = art.external_deps.get(
                "depends_on", {}
            ).get("events", [])
            for event in consumed_events:
                provider = event_providers.get(event.lower())
                if provider and provider != svc_name:
                    relationships.append(DiscoveredRelationship(
                        source=svc_name,
                        target=provider,
                        rel_type="event_coupling",
                        confidence=0.88,
                        evidence=(
                            f"{svc_name} consumes event `{event}` "
                            f"published by {provider}"
                        ),
                        declared=self._is_declared(svc_name, provider),
                        detail={"event": event},
                    ))

        return relationships

    def _deduplicate(
        self, relationships: List[DiscoveredRelationship]
    ) -> List[DiscoveredRelationship]:
        """Keep highest-confidence relationship for each (source, target, type) triple."""
        seen: Dict[Tuple, DiscoveredRelationship] = {}
        for rel in relationships:
            key = (rel.source, rel.target, rel.rel_type)
            if key not in seen or rel.confidence > seen[key].confidence:
                seen[key] = rel
        return list(seen.values())


# ── Report generation ─────────────────────────────────────────────────────────

def generate_discovery_report(
    relationships: List[DiscoveredRelationship],
    manifest: WorkspaceManifest,
    output_dir: Path,
    min_confidence: float = 0.5,
) -> Tuple[Path, Path]:
    """
    Write discovered-relationships.json and discovered-relationships.md
    to output_dir.

    Returns (json_path, md_path).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── JSON output ───────────────────────────────────────────────────────────
    undeclared = [r for r in relationships if not r.declared]
    declared_confirmed = [r for r in relationships if r.declared]

    data = {
        "workspace": manifest.name,
        "generated": get_timestamp(),
        "summary": {
            "total_relationships": len(relationships),
            "undeclared": len(undeclared),
            "declared_confirmed": len(declared_confirmed),
            "high_confidence": len([r for r in relationships if r.confidence >= 0.75]),
        },
        "relationships": [
            {
                "source": r.source,
                "target": r.target,
                "type": r.rel_type,
                "confidence": r.confidence,
                "declared": r.declared,
                "evidence": r.evidence,
                "detail": r.detail,
            }
            for r in relationships
        ],
    }

    json_path = output_dir / "discovered-relationships.json"
    safe_write_text(json_path, json.dumps(data, indent=2))

    # ── Markdown report ───────────────────────────────────────────────────────
    lines = [
        f"# {manifest.name} — Discovered Relationships",
        f"",
        f"Generated: {get_timestamp()}  ",
        f"Min confidence threshold: {min_confidence:.0%}",
        f"",
        f"## Summary",
        f"",
        f"| | Count |",
        f"|---|---|",
        f"| Total relationships found | **{len(relationships)}** |",
        f"| Undeclared (not in manifest) | **{len(undeclared)}** |",
        f"| Confirmed declared deps | **{len(declared_confirmed)}** |",
        f"| High confidence (≥75%) | **{len([r for r in relationships if r.confidence >= 0.75])}** |",
        f"",
    ]

    if undeclared:
        lines += [
            f"## ⚠️ Undeclared Dependencies",
            f"",
            f"These relationships were discovered from artifact analysis but are",
            f"**not listed in ccc-workspace.yml**. Review and add to `depends_on`",
            f"if confirmed.",
            f"",
        ]
        for rel in sorted(undeclared, key=lambda r: -r.confidence):
            pct = int(rel.confidence * 100)
            icon = "🔴" if pct >= 80 else "🟡" if pct >= 60 else "🔵"
            lines += [
                f"### {icon} {rel.source} → {rel.target}",
                f"",
                f"- **Type**: `{rel.rel_type}`",
                f"- **Confidence**: {pct}%",
                f"- **Evidence**: {rel.evidence}",
                f"",
            ]
            if rel.rel_type == "api_call" and rel.detail:
                lines.append(f"```")
                lines.append(f"Consumer calls: {rel.detail.get('consumer_calls', '')}")
                lines.append(f"Provider route: {rel.detail.get('provider_exposes', '')}")
                lines.append(f"```")
                lines.append(f"")
            elif rel.rel_type in ("schema_drift", "shared_schema_identical",
                                   "shared_schema_subset") and rel.detail:
                only_src = rel.detail.get("only_in_source", [])
                only_tgt = rel.detail.get("only_in_target", [])
                if only_src:
                    lines.append(f"  Only in `{rel.source}`: `{', '.join(only_src[:5])}`")
                if only_tgt:
                    lines.append(f"  Only in `{rel.target}`: `{', '.join(only_tgt[:5])}`")
                lines.append(f"")

    if declared_confirmed:
        lines += [
            f"## ✅ Declared Dependencies Confirmed by Analysis",
            f"",
            f"These are in your manifest and were also detected in the artifacts.",
            f"",
        ]
        for rel in declared_confirmed:
            lines.append(
                f"- `{rel.source}` → `{rel.target}` "
                f"({rel.rel_type}, {int(rel.confidence * 100)}%): {rel.evidence}"
            )
        lines.append("")

    if not relationships:
        lines += [
            f"## No Relationships Found",
            f"",
            f"This may mean:",
            f"- Services don't have `.llm-context/` generated yet (run `ccc` in each)",
            f"- Services are genuinely independent",
            f"- Confidence threshold ({min_confidence:.0%}) is too high",
            f"",
        ]

    lines += [
        f"---",
        f"",
        f"*Generated by CCC workspace discover.*",
        f"*To add undeclared dependencies: edit `ccc-workspace.yml` and add to `depends_on`.*",
    ]

    md_path = output_dir / "discovered-relationships.md"
    safe_write_text(md_path, "\n".join(lines))

    return json_path, md_path


# ── Public entry point ────────────────────────────────────────────────────────

def run_discovery(
    manifest: WorkspaceManifest,
    services: Optional[List[ServiceConfig]] = None,
    output_dir: Optional[Path] = None,
    min_confidence: float = 0.5,
) -> Tuple[List[DiscoveredRelationship], Path, Path]:
    """
    Run full cross-repo discovery and write reports.

    Returns (relationships, json_path, md_path).
    """
    out_dir = output_dir or (manifest.root / "workspace-context")

    discovery = CrossRepoDiscovery(manifest, min_confidence=min_confidence)
    relationships = discovery.discover(services)

    json_path, md_path = generate_discovery_report(
        relationships, manifest, out_dir, min_confidence
    )

    return relationships, json_path, md_path