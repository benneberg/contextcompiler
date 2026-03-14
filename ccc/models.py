from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class FileManifestEntry:
    """Metadata for a generated file."""
    hash: str
    size: int
    generated_at: str
    source_files: List[str] = field(default_factory=list)
    source_hashes: List[str] = field(default_factory=list)
    strategy: str = "always"


@dataclass
class ProjectInfo:
    """Auto-detected project metadata."""
    root: Path
    name: str = ""
    languages: List[str] = field(default_factory=list)
    framework: str = ""
    package_manager: str = ""
    has_docker: bool = False
    has_ci: bool = False
    has_tests: bool = False
    entry_points: List[str] = field(default_factory=list)
    description: str = ""
    python_version: str = ""
    node_version: str = ""


@dataclass
class ServiceConfig:
    """Configuration for a service in a workspace."""
    name: str
    path: Path
    service_type: str
    tags: List[str]
    depends_on: List[str]
    description: str

    def exists(self) -> bool:
        return self.path.exists()


@dataclass
class Conflict:
    """Represents an inconsistency between services."""
    conflict_type: str
    severity: str
    symbol: str
    services: List[str]
    details: str
    locations: List[str] = field(default_factory=list)
    suggestion: str = ""


@dataclass
class TypeDefinition:
    """Represents an extracted type definition."""
    name: str
    kind: str
    service: str
    file: str
    fields: List[str] = field(default_factory=list)
    values: List[str] = field(default_factory=list)
    raw_source: str = ""
