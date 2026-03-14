"""Workspace manifest parsing and validation."""
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import yaml

from ..utils.files import safe_read_text

@dataclass
class ServiceConfig:
    """Configuration for a service in the workspace."""
    name: str
    path: Path
    type: str  # frontend, backend-api, data, library
    tags: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)

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
        content = safe_read_text(workspace_file)
        if not content:
            raise ValueError(f"Could not read {workspace_file}")
        
        data = yaml.safe_load(content)
        
        services = {}
        for name, config in data.get("services", {}).items():
            path = workspace_file.parent / config["path"]
            services[name] = ServiceConfig(
                name=name,
                path=path.resolve(),
                type=config.get("type", "unknown"),
                tags=config.get("tags", []),
                depends_on=config.get("depends_on", []),
            )
        
        return cls(
            name=data["name"],
            version=str(data.get("version", "1")),
            root=workspace_file.parent,
            services=services,
        )
    
    def query_by_tags(self, tags: List[str]) -> List[ServiceConfig]:
        """Find services matching any of the given tags."""
        results = []
        for service in self.services.values():
            if any(tag in service.tags for tag in tags):
                results.append(service)
        return results
    
    def get_dependency_order(self, services: List[ServiceConfig]) -> List[ServiceConfig]:
        """Order services by dependencies (topological sort)."""
        # ... (implement topological sort)
