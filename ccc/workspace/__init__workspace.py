"""Workspace support for CCC."""

from .manifest import WorkspaceManifest
from .query import WorkspaceQuery
from .conflicts import ConflictDetector
from .init import init_workspace
from .index import build_service_index
from .serve import serve_workspace
from .discover import run_discovery, CrossRepoDiscovery

__all__ = [
    "WorkspaceManifest",
    "WorkspaceQuery",
    "ConflictDetector",
    "init_workspace",
    "build_service_index",
    "serve_workspace",
    "run_discovery",
    "CrossRepoDiscovery",
]