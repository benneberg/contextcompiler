"""Workspace query commands."""
from pathlib import Path
from typing import List

from .manifest import WorkspaceManifest, ServiceConfig

class WorkspaceQuery:
    """Query workspace for services and dependencies."""
    
    def __init__(self, manifest: WorkspaceManifest):
        self.manifest = manifest
    
    def query_tags(self, tags: List[str]) -> None:
        """Query services by tags and print results."""
        services = self.manifest.query_by_tags(tags)
        
        if not services:
            print(f"No services found with tags: {', '.join(tags)}")
            return
        
        print(f"\nFound {len(services)} service(s) with tags {tags}:\n")
        
        for service in services:
            deps = ", ".join(service.depends_on) if service.depends_on else "none"
            print(f"  {service.name:20s} [{service.type:12s}] — depends on: {deps}")
        
        # Show suggested change sequence
        ordered = self.manifest.get_dependency_order(services)
        print("\nSuggested change sequence (derived from dependencies):")
        for i, service in enumerate(ordered, 1):
            print(f"  {i}. {service.name:20s} ← {self._get_change_hint(service)}")
    
    def _get_change_hint(self, service: ServiceConfig) -> str:
        """Get a hint about what to change in this service."""
        hints = {
            "data": "update schema/config first",
            "backend-api": "implement business logic",
            "frontend": "update UI components",
            "library": "update shared types/utilities",
        }
        return hints.get(service.type, "review and update")
