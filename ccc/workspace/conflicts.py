import json
import re
import ast
from pathlib import Path
from typing import Dict, List, Optional

from ..models import Conflict, TypeDefinition, ServiceConfig
from ..utils.files import safe_read_text, should_skip_path, safe_write_text
from ..utils.formatting import get_timestamp
from .manifest import WorkspaceManifest


class ConflictDetector:
    """Detect inconsistencies across multiple services."""

    def __init__(self, manifest: WorkspaceManifest):
        self.manifest = manifest
        self.type_definitions: Dict[str, List[TypeDefinition]] = {}
        self.api_contracts: Dict[str, Dict] = {}
        self.conflicts: List[Conflict] = []

    def analyze(self, services: Optional[List[ServiceConfig]] = None) -> List[Conflict]:
        """Analyze services for conflicts."""
        if services is None:
            services = list(self.manifest.services.values())

        self.conflicts = []
        self.type_definitions = {}
        self.api_contracts = {}

        print(f"\n  Analyzing {len(services)} services for conflicts...")

        for service in services:
            print(f"    Scanning {service.name}...")
            self._extract_types_from_service(service)
            self._load_external_deps(service)

        print("\n  Checking for conflicts...")

        self._detect_enum_conflicts()
        self._detect_interface_conflicts()
        self._detect_constant_conflicts()
        self._detect_api_contract_mismatches(services)
        self._detect_event_mismatches(services)
        self._detect_naming_inconsistencies()

        severity_order = {"error": 0, "warning": 1, "info": 2}
        self.conflicts.sort(key=lambda c: severity_order.get(c.severity, 99))

        return self.conflicts

    def _extract_types_from_service(self, service: ServiceConfig) -> None:
        """Extract type definitions from a service's source code."""
        if not service.exists():
            return

        self._extract_typescript_types(service)
        self._extract_python_types(service)

    def _extract_typescript_types(self, service: ServiceConfig) -> None:
        """Extract TypeScript type definitions."""
        enum_pattern = re.compile(
            r'(?:export\s+)?enum\s+(\w+)\s*\{([^}]+)\}',
            re.MULTILINE | re.DOTALL
        )

        interface_pattern = re.compile(
            r'(?:export\s+)?interface\s+(\w+)(?:\s+extends\s+[\w,\s]+)?\s*\{([^}]+)\}',
            re.MULTILINE | re.DOTALL
        )

        type_pattern = re.compile(
            r'(?:export\s+)?type\s+(\w+)\s*=\s*(\{[^}]+\}|[^;]+);',
            re.MULTILINE
        )

        const_pattern = re.compile(
            r'(?:export\s+)?const\s+([A-Z][A-Z0-9_]+)\s*(?::\s*\w+)?\s*=\s*([^;]+);',
            re.MULTILINE
        )

        for ts_file in service.path.rglob("*.ts"):
            if should_skip_path(ts_file):
                continue

            content = safe_read_text(ts_file)
            if not content:
                continue

            rel_path = str(ts_file.relative_to(service.path))

            for match in enum_pattern.finditer(content):
                name = match.group(1)
                body = match.group(2)
                values = []

                for line in body.split("\n"):
                    line = line.strip().rstrip(",")
                    if line and not line.startswith("//"):
                        value_match = re.match(r'(\w+)(?:\s*=\s*["\']?([^"\']+)["\']?)?', line)
                        if value_match:
                            values.append(value_match.group(1))

                type_def = TypeDefinition(
                    name=name,
                    kind="enum",
                    service=service.name,
                    file=rel_path,
                    values=values,
                    raw_source=match.group(0)[:200],
                )
                self._add_type_definition(name, type_def)

            for match in interface_pattern.finditer(content):
                name = match.group(1)
                body = match.group(2)
                fields = []

                for line in body.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("//"):
                        field_match = re.match(r'(\w+)\??:', line)
                        if field_match:
                            fields.append(field_match.group(1))

                type_def = TypeDefinition(
                    name=name,
                    kind="interface",
                    service=service.name,
                    file=rel_path,
                    fields=sorted(fields),
                    raw_source=match.group(0)[:300],
                )
                self._add_type_definition(name, type_def)

            for match in type_pattern.finditer(content):
                name = match.group(1)
                body = match.group(2)
                if "{" in body:
                    fields = []
                    for field_match in re.finditer(r'(\w+)\??:', body):
                        fields.append(field_match.group(1))

                    type_def = TypeDefinition(
                        name=name,
                        kind="type",
                        service=service.name,
                        file=rel_path,
                        fields=sorted(fields),
                        raw_source=match.group(0)[:200],
                    )
                    self._add_type_definition(name, type_def)

            for match in const_pattern.finditer(content):
                name = match.group(1)
                value = match.group(2).strip().strip('"').strip("'")
                type_def = TypeDefinition(
                    name=name,
                    kind="constant",
                    service=service.name,
                    file=rel_path,
                    values=[value],
                    raw_source=f"const {name} = {value}",
                )
                self._add_type_definition(name, type_def)

    def _extract_python_types(self, service: ServiceConfig) -> None:
        """Extract Python type definitions."""
        for py_file in service.path.rglob("*.py"):
            if should_skip_path(py_file):
                continue

            content = safe_read_text(py_file)
            if not content:
                continue

            rel_path = str(py_file.relative_to(service.path))

            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    base_names = []
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            base_names.append(base.id)
                        elif isinstance(base, ast.Attribute):
                            base_names.append(base.attr)

                    if "Enum" in base_names or "IntEnum" in base_names or "StrEnum" in base_names:
                        values = []
                        for item in node.body:
                            if isinstance(item, ast.Assign):
                                for target in item.targets:
                                    if isinstance(target, ast.Name):
                                        values.append(target.id)

                        type_def = TypeDefinition(
                            name=node.name,
                            kind="enum",
                            service=service.name,
                            file=rel_path,
                            values=values,
                        )
                        self._add_type_definition(node.name, type_def)

                    elif "BaseModel" in base_names or "TypedDict" in base_names:
                        fields = []
                        for item in node.body:
                            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                                fields.append(item.target.id)

                        type_def = TypeDefinition(
                            name=node.name,
                            kind="interface",
                            service=service.name,
                            file=rel_path,
                            fields=sorted(fields),
                        )
                        self._add_type_definition(node.name, type_def)

                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id.isupper():
                            try:
                                value = ast.literal_eval(node.value)
                                if isinstance(value, (str, int, float, bool)):
                                    type_def = TypeDefinition(
                                        name=target.id,
                                        kind="constant",
                                        service=service.name,
                                        file=rel_path,
                                        values=[str(value)],
                                    )
                                    self._add_type_definition(target.id, type_def)
                            except (ValueError, TypeError):
                                pass

    def _add_type_definition(self, name: str, type_def: TypeDefinition) -> None:
        """Add a type definition to the registry."""
        if name not in self.type_definitions:
            self.type_definitions[name] = []
        self.type_definitions[name].append(type_def)

    def _load_external_deps(self, service: ServiceConfig) -> None:
        """Load external dependencies from generated context."""
        ext_deps_file = service.path / ".llm-context" / "external-dependencies.json"
        if ext_deps_file.exists():
            content = safe_read_text(ext_deps_file)
            if content:
                try:
                    self.api_contracts[service.name] = json.loads(content)
                except json.JSONDecodeError:
                    pass

    def _detect_enum_conflicts(self) -> None:
        """Detect enum definitions with mismatched values."""
        for name, definitions in self.type_definitions.items():
            enums = [d for d in definitions if d.kind == "enum"]
            if len(enums) < 2:
                continue

            value_sets = [frozenset(e.values) for e in enums]
            unique_value_sets = set(value_sets)

            if len(unique_value_sets) > 1:
                services = [e.service for e in enums]
                locations = [f"{e.service}:{e.file}" for e in enums]

                details_parts = []
                for enum in enums:
                    values_str = ", ".join(enum.values[:5])
                    if len(enum.values) > 5:
                        values_str += f" +{len(enum.values) - 5} more"
                    details_parts.append(f"{enum.service}: [{values_str}]")

                details = "\n      ".join(details_parts)

                all_values = set()
                for enum in enums:
                    all_values.update(enum.values)

                suggestions = []
                for enum in enums:
                    missing = all_values - set(enum.values)
                    if missing:
                        suggestions.append(f"Add {missing} to {enum.service}")

                conflict = Conflict(
                    conflict_type="enum_mismatch",
                    severity="error",
                    symbol=name,
                    services=services,
                    details=f"Enum '{name}' has different values:\n      {details}",
                    locations=locations,
                    suggestion="; ".join(suggestions) if suggestions else "Synchronize enum values across services",
                )
                self.conflicts.append(conflict)

    def _detect_interface_conflicts(self) -> None:
        """Detect interface/type definitions with mismatched fields."""
        for name, definitions in self.type_definitions.items():
            interfaces = [d for d in definitions if d.kind in ["interface", "type"]]
            if len(interfaces) < 2:
                continue

            if name in ["Props", "State", "Config", "Options", "Context", "Request", "Response"]:
                continue

            field_sets = [frozenset(i.fields) for i in interfaces]
            unique_field_sets = set(field_sets)

            if len(unique_field_sets) > 1:
                services = [i.service for i in interfaces]
                locations = [f"{i.service}:{i.file}" for i in interfaces]

                details_parts = []
                for interface in interfaces:
                    fields_str = ", ".join(interface.fields[:5])
                    if len(interface.fields) > 5:
                        fields_str += f" +{len(interface.fields) - 5} more"
                    details_parts.append(f"{interface.service}: [{fields_str}]")

                details = "\n      ".join(details_parts)

                all_fields = set()
                for interface in interfaces:
                    all_fields.update(interface.fields)

                common_fields = set.intersection(*[set(i.fields) for i in interfaces]) if interfaces else set()
                different_fields = all_fields - common_fields

                conflict = Conflict(
                    conflict_type="interface_mismatch",
                    severity="warning",
                    symbol=name,
                    services=services,
                    details=f"Type '{name}' has different fields:\n      {details}",
                    locations=locations,
                    suggestion=f"Inconsistent fields: {different_fields}. Consider creating a shared types package.",
                )
                self.conflicts.append(conflict)

    def _detect_constant_conflicts(self) -> None:
        """Detect constants with mismatched values."""
        for name, definitions in self.type_definitions.items():
            constants = [d for d in definitions if d.kind == "constant"]
            if len(constants) < 2:
                continue

            values = [c.values[0] if c.values else "" for c in constants]
            unique_values = set(values)

            if len(unique_values) > 1:
                services = [c.service for c in constants]
                locations = [f"{c.service}:{c.file}" for c in constants]
                details_parts = [f"{c.service}: {c.values[0] if c.values else 'undefined'}" for c in constants]
                details = "\n      ".join(details_parts)

                conflict = Conflict(
                    conflict_type="constant_mismatch",
                    severity="warning",
                    symbol=name,
                    services=services,
                    details=f"Constant '{name}' has different values:\n      {details}",
                    locations=locations,
                    suggestion="Centralize this constant in a shared configuration or types package",
                )
                self.conflicts.append(conflict)

    def _detect_api_contract_mismatches(self, services: List[ServiceConfig]) -> None:
        """Detect API contract mismatches between services."""
        exposed_apis: Dict[str, List] = {}
        consumed_apis: Dict[str, List] = {}

        for service in services:
            if service.name not in self.api_contracts:
                continue

            contract = self.api_contracts[service.name]

            for api in contract.get("exposes", {}).get("api", []):
                parts = api.split(" ", 1)
                if len(parts) == 2:
                    method, route = parts
                else:
                    method, route = "GET", parts[0]

                normalized = self._normalize_route(route)
                if normalized not in exposed_apis:
                    exposed_apis[normalized] = []
                exposed_apis[normalized].append((service.name, method))

            consumed_apis[service.name] = []
            for api in contract.get("depends_on", {}).get("apis_consumed", []):
                consumed_apis[service.name].append(api)

        for consumer, apis in consumed_apis.items():
            for api in apis:
                parts = api.split(" ", 1)
                if len(parts) != 2:
                    continue

                method, url = parts
                route_match = re.search(r'https?://[^/]+(/[^\s?#]*)', url)
                if not route_match:
                    continue

                route = route_match.group(1)
                normalized = self._normalize_route(route)

                if normalized not in exposed_apis:
                    similar = self._find_similar_routes(normalized, list(exposed_apis.keys()))
                    if similar:
                        conflict = Conflict(
                            conflict_type="api_route_mismatch",
                            severity="warning",
                            symbol=route,
                            services=[consumer],
                            details=f"Service '{consumer}' calls '{api}' but route not found.\n      Similar routes: {similar}",
                            suggestion=f"Check if the route should be '{similar[0]}' instead",
                        )
                        self.conflicts.append(conflict)

    def _detect_event_mismatches(self, services: List[ServiceConfig]) -> None:
        """Detect event naming mismatches."""
        published_events: Dict[str, str] = {}

        for service in services:
            if service.name not in self.api_contracts:
                continue

            contract = self.api_contracts[service.name]
            for event in contract.get("exposes", {}).get("events", []):
                published_events[event] = service.name

        event_patterns: Dict[str, List] = {}
        for event in published_events.keys():
            if "." in event:
                pattern = "dot.notation"
            elif "_" in event:
                pattern = "snake_case"
            elif event and event[0].islower() and any(c.isupper() for c in event):
                pattern = "camelCase"
            else:
                pattern = "other"

            if pattern not in event_patterns:
                event_patterns[pattern] = []
            event_patterns[pattern].append((event, published_events[event]))

        if len(event_patterns) > 1:
            details_parts = []
            for pattern, events in event_patterns.items():
                event_names = [e[0] for e in events[:3]]
                details_parts.append(f"{pattern}: {event_names}")

            details = "\n      ".join(details_parts)

            conflict = Conflict(
                conflict_type="event_naming_inconsistency",
                severity="info",
                symbol="event_naming",
                services=list(set(published_events.values())),
                details=f"Inconsistent event naming conventions:\n      {details}",
                suggestion="Consider standardizing on one event naming convention (e.g., dot.notation like 'user.created')",
            )
            self.conflicts.append(conflict)

    def _detect_naming_inconsistencies(self) -> None:
        """Detect similar names that might be the same thing."""
        name_groups: Dict[str, List[TypeDefinition]] = {}

        for name, definitions in self.type_definitions.items():
            lower_name = name.lower()
            if lower_name not in name_groups:
                name_groups[lower_name] = []
            name_groups[lower_name].extend(definitions)

        for lower_name, definitions in name_groups.items():
            unique_names = set(d.name for d in definitions)
            if len(unique_names) > 1:
                services = list(set(d.service for d in definitions))
                conflict = Conflict(
                    conflict_type="naming_inconsistency",
                    severity="info",
                    symbol=lower_name,
                    services=services,
                    details=f"Inconsistent casing for '{lower_name}': {unique_names}",
                    suggestion="Standardize naming across services",
                )
                self.conflicts.append(conflict)

    def _normalize_route(self, route: str) -> str:
        """Normalize a route for comparison."""
        route = route.rstrip("/")
        route = re.sub(r":(\w+)", r"{\1}", route)
        route = re.sub(r"\[(\w+)\]", r"{\1}", route)
        return route.lower()

    def _find_similar_routes(self, route: str, existing_routes: List[str]) -> List[str]:
        """Find routes similar to the given route."""
        similar = []
        route_parts = route.split("/")

        for existing in existing_routes:
            existing_parts = existing.split("/")
            if len(route_parts) != len(existing_parts):
                continue

            matches = 0
            for a, b in zip(route_parts, existing_parts):
                if a == b or "{" in a or "{" in b:
                    matches += 1

            if matches >= len(route_parts) - 1:
                similar.append(existing)

        return similar

    def generate_report(self, output_dir: Optional[Path] = None) -> str:
        """Generate a conflicts report."""
        lines = [
            "# Cross-Repository Conflict Report",
            "",
            f"Generated: {get_timestamp()}",
            f"Services analyzed: {len(self.manifest.services)}",
            f"Conflicts found: {len(self.conflicts)}",
            "",
        ]

        if not self.conflicts:
            lines.extend([
                "## ✅ No Conflicts Detected",
                "",
                "All analyzed services appear to be consistent.",
            ])
        else:
            errors = [c for c in self.conflicts if c.severity == "error"]
            warnings = [c for c in self.conflicts if c.severity == "warning"]
            infos = [c for c in self.conflicts if c.severity == "info"]

            lines.extend([
                "## Summary",
                "",
                f"- 🔴 Errors: {len(errors)}",
                f"- 🟡 Warnings: {len(warnings)}",
                f"- 🔵 Info: {len(infos)}",
                "",
            ])

            if errors:
                lines.extend([
                    "## 🔴 Errors",
                    "",
                    "These conflicts should be fixed before deploying:",
                    "",
                ])
                for conflict in errors:
                    lines.extend(self._format_conflict(conflict))

            if warnings:
                lines.extend([
                    "## 🟡 Warnings",
                    "",
                    "These inconsistencies may cause issues:",
                    "",
                ])
                for conflict in warnings:
                    lines.extend(self._format_conflict(conflict))

            if infos:
                lines.extend([
                    "## 🔵 Info",
                    "",
                    "Potential improvements:",
                    "",
                ])
                for conflict in infos:
                    lines.extend(self._format_conflict(conflict))

        content = "\n".join(lines)

        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            safe_write_text(output_dir / "conflicts-report.md", content)

        return content

    def _format_conflict(self, conflict: Conflict) -> List[str]:
        """Format a single conflict for the report."""
        lines = [
            f"### {conflict.conflict_type}: `{conflict.symbol}`",
            "",
            f"**Services:** {', '.join(conflict.services)}",
            "",
            "**Details:**",
            "```",
            conflict.details,
            "```",
            "",
        ]

        if conflict.locations:
            lines.append(f"**Locations:** {', '.join(conflict.locations)}")
            lines.append("")

        if conflict.suggestion:
            lines.append(f"**Suggestion:** {conflict.suggestion}")
            lines.append("")

        lines.append("---")
        lines.append("")
        return lines

    def print_summary(self) -> None:
        """Print a summary of detected conflicts."""
        print(f"\n{'=' * 60}")
        print("  Conflict Detection Results")
        print(f"{'=' * 60}")

        if not self.conflicts:
            print("\n  ✅ No conflicts detected!")
            print(f"\n  All {len(self.manifest.services)} services appear to be consistent.")
        else:
            errors = [c for c in self.conflicts if c.severity == "error"]
            warnings = [c for c in self.conflicts if c.severity == "warning"]
            infos = [c for c in self.conflicts if c.severity == "info"]

            print(f"\n  Found {len(self.conflicts)} issue(s):")
            print(f"    🔴 Errors: {len(errors)}")
            print(f"    🟡 Warnings: {len(warnings)}")
            print(f"    🔵 Info: {len(infos)}")

            if errors:
                print("\n  Errors (fix these first):")
                for conflict in errors[:5]:
                    print(f"    • {conflict.conflict_type}: {conflict.symbol}")
                    print(f"      Services: {', '.join(conflict.services)}")
                if len(errors) > 5:
                    print(f"    ... and {len(errors) - 5} more")

            if warnings:
                print("\n  Warnings:")
                for conflict in warnings[:5]:
                    print(f"    • {conflict.conflict_type}: {conflict.symbol}")
                if len(warnings) > 5:
                    print(f"    ... and {len(warnings) - 5} more")

        print(f"\n{'=' * 60}\n")
