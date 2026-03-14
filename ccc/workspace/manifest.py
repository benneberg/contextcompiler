from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import json

from ..models import ServiceConfig
from ..utils.files import safe_read_text


@dataclass
class WorkspaceManifest:
    """Parsed workspace configuration."""

    name: str
    version: str
    root: Path
    services: Dict[str, ServiceConfig]

    @classmethod
    def load(cls, workspace_file: Path) -> "WorkspaceManifest":
        """Load and parse workspace manifest."""
        try:
            import yaml

            content = safe_read_text(workspace_file)
            if not content:
                raise ValueError(f"Could not read {workspace_file}")

            data = yaml.safe_load(content)
        except ImportError:
            content = safe_read_text(workspace_file)
            if not content:
                raise ValueError(f"Could not read {workspace_file}")

            if workspace_file.suffix in [".yml", ".yaml"]:
                raise ImportError("PyYAML required for workspace manifests: pip install pyyaml")

            data = json.loads(content)

        services: Dict[str, ServiceConfig] = {}

        for name, config in data.get("services", {}).items():
            path_str = config.get("path", f"./{name}")
            service_path = (workspace_file.parent / path_str).resolve()

            services[name] = ServiceConfig(
                name=name,
                path=service_path,
                service_type=config.get("type", "unknown"),
                tags=config.get("tags", []),
                depends_on=config.get("depends_on", []),
                description=config.get("description", ""),
            )

        return cls(
            name=data.get("name", "workspace"),
            version=str(data.get("version", "1")),
            root=workspace_file.parent.resolve(),
            services=services,
        )

    def query_by_tags(self, tags: Optional[List[str]]) -> List[ServiceConfig]:
        """Find services matching any of the given tags."""
        if not tags:
            return list(self.services.values())

        results: List[ServiceConfig] = []
        lowered_tags = [tag.lower() for tag in tags]

        for service in self.services.values():
            service_tags = [t.lower() for t in service.tags]
            if any(tag in service_tags for tag in lowered_tags):
                results.append(service)

        return results

    def query_by_service(self, service_name: str) -> Optional[ServiceConfig]:
        """Get a specific service by name."""
        return self.services.get(service_name)

    def get_dependents(self, service_name: str) -> List[ServiceConfig]:
        """Get services that depend on the given service."""
        dependents: List[ServiceConfig] = []
        for service in self.services.values():
            if service_name in service.depends_on:
                dependents.append(service)
        return dependents

    def get_dependencies(self, service_name: str) -> List[ServiceConfig]:
        """Get services that the given service depends on."""
        service = self.services.get(service_name)
        if not service:
            return []

        dependencies: List[ServiceConfig] = []
        for dep_name in service.depends_on:
            if dep_name in self.services:
                dependencies.append(self.services[dep_name])

        return dependencies

    def get_dependency_order(self, services: Optional[List[ServiceConfig]] = None) -> List[ServiceConfig]:
        """
        Order services by dependencies using topological sort.
        Services with no dependencies come first.
        """
        if services is None:
            services = list(self.services.values())

        service_names = {s.name for s in services}

        graph = {s.name: [] for s in services}
        in_degree = {s.name: 0 for s in services}

        for service in services:
            for dep in service.depends_on:
                if dep in service_names:
                    graph[dep].append(service.name)
                    in_degree[service.name] += 1

        queue = [name for name, degree in in_degree.items() if degree == 0]
        result: List[ServiceConfig] = []

        while queue:
            node = queue.pop(0)
            result.append(self.services[node])

            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(services):
            print("  Warning: Circular dependency detected")
            return services

        return result

    def validate(self) -> List[str]:
        """Validate workspace configuration and return issues."""
        issues: List[str] = []

        for name, service in self.services.items():
            if not service.path.exists():
                issues.append(f"Service '{name}': path does not exist: {service.path}")

            for dep in service.depends_on:
                if dep not in self.services:
                    issues.append(f"Service '{name}': unknown dependency '{dep}'")

        return issues
