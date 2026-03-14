import json
from pathlib import Path
from typing import Dict, List

from ..models import ServiceConfig
from ..utils.files import safe_read_text, safe_write_text
from ..utils.formatting import get_timestamp
from .manifest import WorkspaceManifest


class WorkspaceQuery:
    """Query workspace for services and dependencies."""

    def __init__(self, manifest: WorkspaceManifest):
        self.manifest = manifest

    def query_tags(self, tags: List[str], generate_context: bool = False) -> None:
        """Query services by tags and print results."""
        services = self.manifest.query_by_tags(tags)

        if not services:
            print(f"\n  No services found with tags: {', '.join(tags)}")
            print("\n  Available tags:")
            all_tags = set()
            for service in self.manifest.services.values():
                all_tags.update(service.tags)
            for tag in sorted(all_tags):
                print(f"    - {tag}")
            return

        print(f"\n{'=' * 60}")
        print(f"  Workspace: {self.manifest.name}")
        print(f"  Query: tags={tags}")
        print(f"{'=' * 60}")
        print(f"\n  Found {len(services)} service(s):\n")

        for service in services:
            deps = ", ".join(service.depends_on) if service.depends_on else "none"
            status = "✓" if service.exists() else "✗"
            print(f"  {status} {service.name:20s} [{service.service_type:12s}]")
            print(f"      Path: {service.path}")
            print(f"      Tags: {', '.join(service.tags)}")
            print(f"      Depends on: {deps}")
            if service.description:
                print(f"      Description: {service.description}")
            print("")

        ordered = self.manifest.get_dependency_order(services)
        print("  Suggested change sequence (from dependency graph):\n")
        for i, service in enumerate(ordered, 1):
            hint = self._get_change_hint(service)
            print(f"    {i}. {service.name:20s} <- {hint}")

        print("")

        if generate_context:
            self.generate_workspace_context(services)

    def query_service(self, service_name: str, what: str = "info") -> None:
        """Query information about a specific service."""
        service = self.manifest.query_by_service(service_name)

        if not service:
            print(f"\n  Service '{service_name}' not found.")
            print("\n  Available services:")
            for name in sorted(self.manifest.services.keys()):
                print(f"    - {name}")
            return

        print(f"\n{'=' * 60}")
        print(f"  Service: {service.name}")
        print(f"{'=' * 60}\n")

        if what in ("info", "all"):
            print(f"  Type: {service.service_type}")
            print(f"  Path: {service.path}")
            print(f"  Tags: {', '.join(service.tags)}")
            print(f"  Description: {service.description or 'N/A'}")
            print("")

        if what in ("depends-on", "all"):
            print("  Dependencies (services this depends on):")
            deps = self.manifest.get_dependencies(service_name)
            if deps:
                for dep in deps:
                    print(f"    -> {dep.name} [{dep.service_type}]")
            else:
                print("    (none)")
            print("")

        if what in ("dependents", "all"):
            print("  Dependents (services that depend on this):")
            dependents = self.manifest.get_dependents(service_name)
            if dependents:
                for dep in dependents:
                    print(f"    <- {dep.name} [{dep.service_type}]")
            else:
                print("    (none)")
            print("")

        if what in ("external", "all"):
            self._show_external_dependencies(service)

    def list_services(self) -> None:
        """List all services in the workspace."""
        print(f"\n{'=' * 60}")
        print(f"  Workspace: {self.manifest.name} (v{self.manifest.version})")
        print(f"  Root: {self.manifest.root}")
        print(f"{'=' * 60}\n")

        print(f"  Services ({len(self.manifest.services)}):\n")

        for name, service in sorted(self.manifest.services.items()):
            status = "✓" if service.exists() else "✗"
            tags_str = ", ".join(service.tags[:3])
            if len(service.tags) > 3:
                tags_str += f" +{len(service.tags) - 3} more"
            print(f"  {status} {name:20s} [{service.service_type:12s}] tags: {tags_str}")

        print("")

        all_tags = set()
        for service in self.manifest.services.values():
            all_tags.update(service.tags)

        print(f"  Available tags: {', '.join(sorted(all_tags))}")
        print("")

    def validate_workspace(self) -> None:
        """Validate workspace configuration."""
        print(f"\n{'=' * 60}")
        print(f"  Workspace Validation: {self.manifest.name}")
        print(f"{'=' * 60}\n")

        issues = self.manifest.validate()

        if issues:
            print(f"  Found {len(issues)} issue(s):\n")
            for issue in issues:
                print(f"  ✗ {issue}")
        else:
            print(f"  ✓ All {len(self.manifest.services)} services validated successfully")

        print("\n  Context file status:\n")
        for name, service in sorted(self.manifest.services.items()):
            context_dir = service.path / ".llm-context"
            ext_deps = context_dir / "external-dependencies.json"

            if not service.exists():
                print(f"  ✗ {name:20s} - service path missing")
            elif not context_dir.exists():
                print(f"  ⚠ {name:20s} - no .llm-context/ (run generator)")
            elif not ext_deps.exists():
                print(f"  ⚠ {name:20s} - no external-dependencies.json")
            else:
                print(f"  ✓ {name:20s} - ready")

        print("")

    def generate_workspace_context(self, services: List[ServiceConfig]) -> None:
        """Generate cross-repo workspace context."""
        print("  Generating workspace context...")

        output_dir = self.manifest.root / "workspace-context"
        output_dir.mkdir(exist_ok=True)

        all_deps: Dict[str, Dict] = {}
        for service in services:
            ext_deps_file = service.path / ".llm-context" / "external-dependencies.json"
            if ext_deps_file.exists():
                content = safe_read_text(ext_deps_file)
                if content:
                    try:
                        all_deps[service.name] = json.loads(content)
                    except json.JSONDecodeError:
                        pass

        self._generate_workspace_md(services, all_deps, output_dir)
        self._generate_cross_repo_api(services, all_deps, output_dir)
        self._generate_change_sequence(services, output_dir)
        self._generate_dependency_graph(services, all_deps, output_dir)

        print(f"\n  Generated workspace context in: {output_dir}")
        print("    - WORKSPACE.md")
        print("    - cross-repo-api.txt")
        print("    - change-sequence.md")
        print("    - dependency-graph.md")
        print("")

    def _get_change_hint(self, service: ServiceConfig) -> str:
        """Get a hint about what to change in this service."""
        hints = {
            "data": "update schema/config first",
            "database": "update schema/config first",
            "backend-api": "implement business logic",
            "api": "implement endpoints",
            "frontend": "update UI components",
            "library": "update shared types/utilities",
            "gateway": "update routing configuration",
        }
        return hints.get(service.service_type, "review and update")

    def _show_external_dependencies(self, service: ServiceConfig) -> None:
        """Show external dependencies from generated context."""
        ext_deps_file = service.path / ".llm-context" / "external-dependencies.json"

        if not ext_deps_file.exists():
            print("  External dependencies: (not generated)")
            print(f"    Run generator in: {service.path}")
            return

        try:
            content = safe_read_text(ext_deps_file)
            if not content:
                return

            deps = json.loads(content)

            print("  External Dependencies (from code analysis):\n")

            if deps.get("exposes", {}).get("api"):
                print("    Exposes APIs:")
                for api in deps["exposes"]["api"][:10]:
                    print(f"      {api}")
                if len(deps["exposes"]["api"]) > 10:
                    print(f"      ... and {len(deps['exposes']['api']) - 10} more")

            if deps.get("depends_on", {}).get("services"):
                print("\n    Depends on services:")
                for svc in deps["depends_on"]["services"]:
                    print(f"      -> {svc}")

            if deps.get("depends_on", {}).get("databases"):
                print("\n    Databases:")
                for db in deps["depends_on"]["databases"]:
                    print(f"      - {db}")

            if deps.get("depends_on", {}).get("external_apis"):
                print("\n    Third-party APIs:")
                for api in deps["depends_on"]["external_apis"]:
                    print(f"      - {api}")

            print("")

        except Exception as e:
            print(f"  Error reading external dependencies: {e}")

    def _generate_workspace_md(self, services: List[ServiceConfig], all_deps: Dict, output_dir: Path) -> None:
        """Generate WORKSPACE.md overview."""
        lines = [
            f"# {self.manifest.name} — Workspace Context",
            "",
            f"Generated: {get_timestamp()}",
            "",
            "## Services in This Workspace",
            "",
            "| Service | Type | Tags | Dependencies |",
            "|---------|------|------|--------------|",
        ]

        for service in services:
            tags = ", ".join(service.tags[:3])
            deps = ", ".join(service.depends_on) if service.depends_on else "-"
            lines.append(f"| {service.name} | {service.service_type} | {tags} | {deps} |")

        lines.extend([
            "",
            "## How They Connect",
            "",
        ])

        connections = []
        for service in services:
            if service.name in all_deps:
                deps = all_deps[service.name]
                for consumed in deps.get("depends_on", {}).get("apis_consumed", []):
                    for other in services:
                        if other.name in consumed or other.name.replace("-", "") in consumed:
                            connections.append(f"{service.name} -> {other.name}")
                            break

        if connections:
            lines.append("```")
            for conn in sorted(set(connections)):
                lines.append(conn)
            lines.append("```")
        else:
            lines.append("(No direct API connections detected)")

        lines.extend([
            "",
            "## Service Details",
            "",
        ])

        for service in services:
            lines.append(f"### {service.name}")
            lines.append("")
            lines.append(f"- **Type**: {service.service_type}")
            lines.append(f"- **Path**: `{service.path}`")
            lines.append(f"- **Tags**: {', '.join(service.tags)}")
            if service.description:
                lines.append(f"- **Description**: {service.description}")

            if service.name in all_deps:
                deps = all_deps[service.name]

                if deps.get("exposes", {}).get("api"):
                    lines.append("")
                    lines.append("**Exposes:**")
                    for api in deps["exposes"]["api"][:5]:
                        lines.append(f"- `{api}`")
                    if len(deps["exposes"]["api"]) > 5:
                        lines.append(f"- ... and {len(deps['exposes']['api']) - 5} more")

                if deps.get("depends_on", {}).get("databases"):
                    lines.append("")
                    lines.append("**Databases:**")
                    for db in deps["depends_on"]["databases"]:
                        lines.append(f"- {db}")

            lines.append("")

        content = "\n".join(lines)
        safe_write_text(output_dir / "WORKSPACE.md", content)

    def _generate_cross_repo_api(self, services: List[ServiceConfig], all_deps: Dict, output_dir: Path) -> None:
        """Generate cross-repo API call map."""
        lines = [
            "# Cross-Repository API Calls",
            f"# Generated: {get_timestamp()}",
            "",
        ]

        for service in services:
            if service.name not in all_deps:
                continue

            deps = all_deps[service.name]
            consumed = deps.get("depends_on", {}).get("apis_consumed", [])

            if consumed:
                lines.append(f"## {service.name}")
                lines.append("")
                for api in consumed:
                    lines.append(f"  -> {api}")
                lines.append("")

        content = "\n".join(lines)
        safe_write_text(output_dir / "cross-repo-api.txt", content)

    def _generate_change_sequence(self, services: List[ServiceConfig], output_dir: Path) -> None:
        """Generate change sequence based on dependencies."""
        ordered = self.manifest.get_dependency_order(services)

        lines = [
            "# Change Sequence",
            "",
            f"Generated: {get_timestamp()}",
            "",
            "Recommended order for implementing changes across services:",
            "",
        ]

        for i, service in enumerate(ordered, 1):
            lines.append(f"## {i}. {service.name}")
            lines.append("")
            lines.append(f"- **Type**: {service.service_type}")
            lines.append(f"- **Path**: `{service.path}`")

            if service.depends_on:
                lines.append(f"- **Depends on**: {', '.join(service.depends_on)}")
                lines.append("")
                lines.append("*Ensure the above services are updated first.*")
            else:
                lines.append("")
                lines.append("*No dependencies - can be updated first.*")

            lines.append("")

        content = "\n".join(lines)
        safe_write_text(output_dir / "change-sequence.md", content)

    def _generate_dependency_graph(self, services: List[ServiceConfig], all_deps: Dict, output_dir: Path) -> None:
        """Generate Mermaid dependency graph."""
        lines = [
            "# Dependency Graph",
            "",
            "```mermaid",
            "graph TD",
        ]

        for service in services:
            node_id = service.name.replace("-", "_")
            lines.append(f"  {node_id}[{service.name}]")

        lines.append("")

        edges_added = set()
        for service in services:
            node_id = service.name.replace("-", "_")

            for dep in service.depends_on:
                dep_id = dep.replace("-", "_")
                edge = f"{node_id} --> {dep_id}"
                if edge not in edges_added:
                    lines.append(f"  {edge}")
                    edges_added.add(edge)

            if service.name in all_deps:
                for svc in all_deps[service.name].get("depends_on", {}).get("services", []):
                    for other in services:
                        if other.name in svc or svc in other.name:
                            other_id = other.name.replace("-", "_")
                            edge = f"{node_id} -.-> {other_id}"
                            if edge not in edges_added and node_id != other_id:
                                lines.append(f"  {edge}")
                                edges_added.add(edge)

        lines.extend([
            "```",
            "",
            "**Legend:**",
            "- Solid arrows (`-->`) = declared dependencies in workspace manifest",
            "- Dashed arrows (`-.->`) = detected from code analysis",
        ])

        content = "\n".join(lines)
        safe_write_text(output_dir / "dependency-graph.md", content)
