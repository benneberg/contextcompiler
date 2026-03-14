"""Cross-repo context aggregation."""
from pathlib import Path
from typing import Dict, List

from .manifest import WorkspaceManifest, ServiceConfig
from ..generator import LLMContextGenerator
from ..extractors.base import ExtractionResult

class WorkspaceAggregator:
    """Aggregate context across multiple repositories."""
    
    def __init__(self, manifest: WorkspaceManifest):
        self.manifest = manifest
        self.service_results: Dict[str, ExtractionResult] = {}
    
    def generate(self, services: List[ServiceConfig], output_dir: Path) -> None:
        """Generate cross-repo context for selected services."""
        print(f"\nGenerating workspace context for {len(services)} services...")
        
        # Step 1: Extract context from each service
        for service in services:
            print(f"  Extracting from {service.name}...")
            # Load that service's .llm-context/
            context_dir = service.path / ".llm-context"
            if not context_dir.exists():
                print(f"    Warning: No context found, generating...")
                # Generate context for this service
                gen = LLMContextGenerator(service.path)
                gen.generate()
            
            # Read external-dependencies.json
            # ... (read extraction results)
        
        # Step 2: Generate aggregated outputs
        output_dir.mkdir(parents=True, exist_ok=True)
        
        self._generate_workspace_md(services, output_dir)
        self._generate_cross_repo_api(services, output_dir)
        self._generate_dependency_graph(services, output_dir)
        self._generate_change_sequence(services, output_dir)
    
    def _generate_workspace_md(self, services: List[ServiceConfig], output: Path) -> None:
        """Generate WORKSPACE.md overview."""
        lines = [
            f"# {self.manifest.name} — Workspace Context",
            "",
            "## Services in This Workspace",
            "",
            "| Service | Type | Responsibility |",
            "|---------|------|----------------|",
        ]
        
        for service in services:
            # Get description from service's CLAUDE.md if available
            description = self._get_service_description(service)
            lines.append(f"| {service.name} | {service.type} | {description} |")
        
        # ... (continue building WORKSPACE.md)
        
        content = "\n".join(lines)
        (output / "WORKSPACE.md").write_text(content, encoding="utf-8")
    
    def _generate_cross_repo_api(self, services: List[ServiceConfig], output: Path) -> None:
        """Generate cross-repo API call map."""
        # ... (analyze external-dependencies.json from each service)
    
    def _generate_change_sequence(self, services: List[ServiceConfig], output: Path) -> None:
        """Generate change sequence based on dependencies."""
        ordered = self.manifest.get_dependency_order(services)
        
        lines = [
            "# Change Sequence",
            "",
            "Recommended order for implementing changes across services:",
            "",
        ]
        
        for i, service in enumerate(ordered, 1):
            lines.append(f"{i}. **{service.name}** ({service.type})")
            lines.append(f"   - Path: `{service.path}`")
            if service.depends_on:
                lines.append(f"   - Depends on: {', '.join(service.depends_on)}")
            lines.append("")
        
        content = "\n".join(lines)
        (output / "change-sequence.md").write_text(content, encoding="utf-8")
