"""
CCC Alignment Engine — detect drift between code (CCC) and intent (PKML).

Compares what the code actually does (.llm-context/ artifacts) against
what the product documentation says it should do (pkml.json).

    ccc align                    # check current directory
    ccc align --pkml path/to/pkml.json
    ccc align --format json

Output example:
    ✓  GET /api/users         — documented and implemented
    ⚠  POST /reset-password  — in PKML but not in code (missing implementation)
    ⚠  DELETE /internal/user  — in code but not in PKML (undocumented endpoint)

Degrades gracefully: partial PKML = partial checking, not an error.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .utils.files import safe_read_text
from .utils.formatting import get_timestamp


# ── Data shapes ───────────────────────────────────────────────────────────────

@dataclass
class AlignmentIssue:
    kind: str           # missing_impl | undocumented | schema_drift | event_mismatch
    severity: str       # error | warning | info
    item: str           # the route, schema, or event in question
    message: str
    suggestion: str = ""


@dataclass
class AlignmentReport:
    service: str
    generated: str
    has_pkml: bool
    pkml_completeness: float    # 0.0 - 1.0, how much of PKML is filled in
    issues: List[AlignmentIssue] = field(default_factory=list)
    confirmed: List[str] = field(default_factory=list)  # things that match

    @property
    def errors(self) -> List[AlignmentIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[AlignmentIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def is_clean(self) -> bool:
        return len(self.errors) == 0 and len(self.warnings) == 0


# ── PKML loader ───────────────────────────────────────────────────────────────

def _load_pkml(pkml_path: Path) -> Optional[Dict]:
    """Load and parse a pkml.json file."""
    content = safe_read_text(pkml_path)
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _pkml_completeness(pkml: Dict) -> float:
    """
    Estimate how complete a PKML file is.
    0.0 = empty scaffold, 1.0 = fully populated.
    """
    score = 0
    total = 6

    if pkml.get("service") and not pkml["service"].startswith("TODO"):
        score += 1
    if pkml.get("exposes", {}).get("api"):
        score += 1
    if pkml.get("depends_on", {}).get("services"):
        score += 1
    if pkml.get("description") and "TODO" not in pkml.get("description", ""):
        score += 1
    if pkml.get("owners"):
        score += 1
    if pkml.get("tags"):
        score += 1

    return round(score / total, 2)


# ── Route normalization ───────────────────────────────────────────────────────

def _normalize_route(route: str) -> str:
    """Normalize a route string for comparison."""
    # Strip method prefix: "POST /api/users" → "/api/users"
    parts = route.strip().split()
    path = parts[-1] if parts else route

    # Normalize param styles: :id → {id}
    path = re.sub(r":(\w+)", r"{\1}", path)
    # Strip trailing slash
    path = path.rstrip("/") or "/"
    return path.lower()


def _routes_match(a: str, b: str) -> bool:
    """True if two route strings refer to the same endpoint after normalization."""
    return _normalize_route(a) == _normalize_route(b)


def _extract_method_path(route_str: str) -> Tuple[str, str]:
    """Split 'POST /api/users' into ('POST', '/api/users')."""
    parts = route_str.strip().split(None, 1)
    if len(parts) == 2:
        return parts[0].upper(), parts[1]
    return "ANY", route_str


# ── Alignment Engine ──────────────────────────────────────────────────────────

class AlignmentEngine:
    """
    Compare CCC artifacts (what the code does) against PKML (what it should do).

    Designed to degrade gracefully:
    - No PKML at all → reports "no product documentation" and exits cleanly
    - Partial PKML   → checks only what's declared, skips the rest
    - Full PKML      → comprehensive alignment check
    """

    def __init__(self, context_dir: Path, pkml_path: Optional[Path] = None):
        self.context_dir = context_dir
        self.pkml_path = pkml_path or self._find_pkml(context_dir)
        self.pkml: Optional[Dict] = None

        if self.pkml_path and self.pkml_path.exists():
            self.pkml = _load_pkml(self.pkml_path)

        # Load CCC artifacts
        self._actual_routes = self._load_actual_routes()
        self._actual_events = self._load_actual_events()
        self._actual_schemas = self._load_actual_schemas()
        self._service_name = self._detect_service_name()

    def _find_pkml(self, context_dir: Path) -> Optional[Path]:
        """Search common locations for pkml.json."""
        root = context_dir.parent
        candidates = [
            root / "pkml.json",
            root / "product-knowledge" / "pkml.json",
            root / ".pkml" / "pkml.json",
        ]
        for p in candidates:
            if p.exists():
                return p
        return None

    def _detect_service_name(self) -> str:
        ext_deps = safe_read_text(self.context_dir / "external-dependencies.json")
        if ext_deps:
            try:
                return json.loads(ext_deps).get("service", "unknown")
            except Exception:
                pass
        return self.context_dir.parent.name

    def _load_actual_routes(self) -> List[str]:
        """Load all routes from routes.txt."""
        content = safe_read_text(self.context_dir / "routes.txt") or ""
        routes = []
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) >= 2 and parts[0].upper() in {
                "GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"
            }:
                routes.append(f"{parts[0].upper()} {parts[1]}")
        return routes

    def _load_actual_events(self) -> List[str]:
        """Load exposed events from external-dependencies.json."""
        content = safe_read_text(
            self.context_dir / "external-dependencies.json"
        )
        if not content:
            return []
        try:
            data = json.loads(content)
            return data.get("exposes", {}).get("events", [])
        except Exception:
            return []

    def _load_actual_schemas(self) -> Set[str]:
        """Load schema/type names from schemas-extracted.*"""
        names = set()
        for filename in ["schemas-extracted.py", "types-extracted.ts"]:
            content = safe_read_text(self.context_dir / filename) or ""
            for line in content.splitlines():
                m = re.match(r"^class (\w+)", line)
                if not m:
                    m = re.match(r"^export (?:interface|enum|type|class) (\w+)", line)
                if m:
                    names.add(m.group(1))
        return names

    # ── Check methods ─────────────────────────────────────────────────────────

    def check_routes(self) -> Tuple[List[AlignmentIssue], List[str]]:
        """
        Compare PKML declared API routes against routes.txt.

        Returns (issues, confirmed_matches).
        """
        issues = []
        confirmed = []

        if not self.pkml:
            return issues, confirmed

        pkml_apis: List[str] = self.pkml.get("exposes", {}).get("api", [])
        if not pkml_apis:
            return issues, confirmed

        actual_normalized = {_normalize_route(r) for r in self._actual_routes}

        for pkml_route in pkml_apis:
            norm = _normalize_route(pkml_route)
            if norm in actual_normalized:
                confirmed.append(pkml_route)
            else:
                # Check for close match (method mismatch or path drift)
                method, path = _extract_method_path(pkml_route)
                path_norm = _normalize_route(path)

                close_match = next(
                    (r for r in self._actual_routes
                     if _normalize_route(r.split(None, 1)[-1]) == path_norm),
                    None
                )

                if close_match:
                    actual_method = close_match.split()[0]
                    issues.append(AlignmentIssue(
                        kind="method_mismatch",
                        severity="warning",
                        item=pkml_route,
                        message=(
                            f"Route `{path}` exists but with method "
                            f"`{actual_method}`, not `{method}` as declared in PKML"
                        ),
                        suggestion=f"Update PKML to `{actual_method} {path}` or fix the implementation",
                    ))
                else:
                    issues.append(AlignmentIssue(
                        kind="missing_impl",
                        severity="error",
                        item=pkml_route,
                        message=(
                            f"`{pkml_route}` is declared in PKML "
                            f"but not found in routes.txt"
                        ),
                        suggestion="Implement this endpoint or remove it from PKML",
                    ))

        # Find routes in code but not in PKML
        pkml_normalized = {_normalize_route(r) for r in pkml_apis}
        for actual_route in self._actual_routes:
            norm = _normalize_route(actual_route)
            if norm not in pkml_normalized:
                method, path = _extract_method_path(actual_route)
                # Skip obviously internal routes
                is_internal = any(
                    seg in path.lower()
                    for seg in ["/internal/", "/health", "/metrics",
                                "/debug", "/_", "/admin/"]
                )
                severity = "info" if is_internal else "warning"
                issues.append(AlignmentIssue(
                    kind="undocumented",
                    severity=severity,
                    item=actual_route,
                    message=(
                        f"`{actual_route}` exists in code "
                        f"but is not declared in PKML"
                    ),
                    suggestion=(
                        "Add to PKML exposes.api if intentionally public, "
                        "or add /internal/ prefix if it should stay private"
                    ),
                ))

        return issues, confirmed

    def check_events(self) -> Tuple[List[AlignmentIssue], List[str]]:
        """Compare PKML declared events against external-dependencies.json."""
        issues = []
        confirmed = []

        if not self.pkml:
            return issues, confirmed

        pkml_events: List[str] = self.pkml.get("exposes", {}).get("events", [])
        if not pkml_events and not self._actual_events:
            return issues, confirmed

        pkml_set = {e.lower() for e in pkml_events}
        actual_set = {e.lower() for e in self._actual_events}

        for event in pkml_events:
            if event.lower() in actual_set:
                confirmed.append(event)
            else:
                issues.append(AlignmentIssue(
                    kind="missing_impl",
                    severity="warning",
                    item=event,
                    message=f"Event `{event}` declared in PKML but not found in code",
                    suggestion="Implement the event emission or remove from PKML",
                ))

        for event in self._actual_events:
            if event.lower() not in pkml_set:
                issues.append(AlignmentIssue(
                    kind="undocumented",
                    severity="info",
                    item=event,
                    message=f"Event `{event}` emitted in code but not declared in PKML",
                    suggestion="Add to PKML exposes.events",
                ))

        return issues, confirmed

    def check_dependencies(self) -> Tuple[List[AlignmentIssue], List[str]]:
        """Compare PKML declared dependencies against external-dependencies.json."""
        issues = []
        confirmed = []

        if not self.pkml:
            return issues, confirmed

        pkml_deps: List[str] = self.pkml.get("depends_on", {}).get("services", [])
        if not pkml_deps:
            return issues, confirmed

        content = safe_read_text(
            self.context_dir / "external-dependencies.json"
        )
        if not content:
            return issues, confirmed

        try:
            ext_data = json.loads(content)
        except Exception:
            return issues, confirmed

        actual_services = {
            s.lower() for s in
            ext_data.get("depends_on", {}).get("services", [])
        }

        for dep in pkml_deps:
            if dep.lower() in actual_services:
                confirmed.append(dep)
            else:
                issues.append(AlignmentIssue(
                    kind="missing_impl",
                    severity="info",
                    item=dep,
                    message=(
                        f"Dependency on `{dep}` declared in PKML "
                        f"but not detected in code analysis"
                    ),
                    suggestion=(
                        "Verify the dependency exists or remove from PKML. "
                        "May require `ccc --force` to re-detect."
                    ),
                ))

        return issues, confirmed

    # ── Main run ──────────────────────────────────────────────────────────────

    def run(self) -> AlignmentReport:
        """Run all alignment checks and return a consolidated report."""
        report = AlignmentReport(
            service=self._service_name,
            generated=get_timestamp(),
            has_pkml=self.pkml is not None,
            pkml_completeness=_pkml_completeness(self.pkml) if self.pkml else 0.0,
        )

        if not self.pkml:
            report.issues.append(AlignmentIssue(
                kind="no_pkml",
                severity="info",
                item="pkml.json",
                message="No pkml.json found — alignment checking requires product documentation",
                suggestion="Run `ccc pkml` to generate a PKML scaffold, then fill it in",
            ))
            return report

        if report.pkml_completeness < 0.3:
            report.issues.append(AlignmentIssue(
                kind="incomplete_pkml",
                severity="info",
                item="pkml.json",
                message=(
                    f"PKML is {int(report.pkml_completeness * 100)}% complete — "
                    f"alignment checks will be limited"
                ),
                suggestion="Fill in PKML fields: api, description, owners, depends_on",
            ))

        route_issues, route_confirmed = self.check_routes()
        event_issues, event_confirmed = self.check_events()
        dep_issues, dep_confirmed = self.check_dependencies()

        report.issues.extend(route_issues + event_issues + dep_issues)
        report.confirmed.extend(route_confirmed + event_confirmed + dep_confirmed)

        return report


# ── Report formatting ─────────────────────────────────────────────────────────

def format_report(report: AlignmentReport, fmt: str = "human") -> str:
    """Format an AlignmentReport for output."""

    if fmt == "json":
        return json.dumps({
            "service": report.service,
            "generated": report.generated,
            "has_pkml": report.has_pkml,
            "pkml_completeness": report.pkml_completeness,
            "clean": report.is_clean(),
            "summary": {
                "errors": len(report.errors),
                "warnings": len(report.warnings),
                "confirmed": len(report.confirmed),
            },
            "issues": [
                {
                    "kind": i.kind, "severity": i.severity,
                    "item": i.item, "message": i.message,
                    "suggestion": i.suggestion,
                }
                for i in report.issues
            ],
            "confirmed": report.confirmed,
        }, indent=2)

    # Human-readable
    lines = [
        f"",
        f"{'=' * 60}",
        f"  CCC Alignment — {report.service}",
        f"  Generated: {report.generated}",
        f"{'=' * 60}",
        f"",
    ]

    if not report.has_pkml:
        lines += [
            f"  ℹ  No pkml.json found.",
            f"     Run `ccc pkml` to create one, then fill it in.",
            f"",
        ]
        return "\n".join(lines)

    completeness_pct = int(report.pkml_completeness * 100)
    lines.append(f"  PKML completeness: {completeness_pct}%")
    lines.append(f"")

    if report.confirmed:
        lines.append(f"  ✓  Confirmed ({len(report.confirmed)} match):")
        for item in report.confirmed:
            lines.append(f"     ✓  {item}")
        lines.append(f"")

    if report.errors:
        lines.append(f"  ✗  Errors ({len(report.errors)}):")
        for issue in report.errors:
            lines.append(f"     ✗  {issue.item}")
            lines.append(f"        {issue.message}")
            if issue.suggestion:
                lines.append(f"        → {issue.suggestion}")
        lines.append(f"")

    if report.warnings:
        lines.append(f"  ⚠  Warnings ({len(report.warnings)}):")
        for issue in report.warnings:
            lines.append(f"     ⚠  {issue.item}")
            lines.append(f"        {issue.message}")
            if issue.suggestion:
                lines.append(f"        → {issue.suggestion}")
        lines.append(f"")

    info_issues = [i for i in report.issues if i.severity == "info"
                   and i.kind not in ("no_pkml", "incomplete_pkml")]
    if info_issues:
        lines.append(f"  ℹ  Info ({len(info_issues)}):")
        for issue in info_issues:
            lines.append(f"     ℹ  {issue.item}: {issue.message}")
        lines.append(f"")

    if report.is_clean() and report.has_pkml:
        lines.append(f"  ✓  All checks passed — code and PKML are aligned.")
        lines.append(f"")
    else:
        e, w = len(report.errors), len(report.warnings)
        lines.append(f"  Summary: {e} error(s), {w} warning(s), "
                     f"{len(report.confirmed)} confirmed")
        lines.append(f"")

    return "\n".join(lines)


# ── Public entry point ────────────────────────────────────────────────────────

def run_alignment(
    context_dir: Path,
    pkml_path: Optional[Path] = None,
    fmt: str = "human",
) -> Tuple[AlignmentReport, str]:
    """
    Run alignment check and return (report, formatted_output).
    """
    engine = AlignmentEngine(context_dir, pkml_path)
    report = engine.run()
    output = format_report(report, fmt)
    return report, output