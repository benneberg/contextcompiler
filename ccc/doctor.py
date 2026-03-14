from pathlib import Path
import sys

from .config import load_config
from .manifest import GenerationManifest
from .security.manager import SecurityManager
from .utils.formatting import human_readable_size
from .utils.files import safe_read_text


class DiagnosticTool:
    """Run diagnostics on the project and environment."""

    def __init__(self, root: Path):
        self.root = root

    def run(self) -> None:
        """Run all diagnostics."""
        print("")
        print("=" * 60)
        print("  LLM Context Generator - Diagnostics")
        print("=" * 60)
        print("")

        self._check_environment()
        self._check_project()
        self._check_generated_context()
        self._check_security()
        self._recommend_improvements()

    def _check_environment(self) -> None:
        """Check system environment."""
        print("-> Environment Check")
        print(f"  Python: {sys.version.split()[0]}")
        print(f"  Platform: {sys.platform}")

        optional_deps = [
            ("yaml", "pyyaml", "YAML config support"),
            ("anthropic", "anthropic", "Anthropic AI summaries"),
            ("openai", "openai", "OpenAI summaries"),
            ("watchdog", "watchdog", "Watch mode"),
        ]

        for module, package, feature in optional_deps:
            try:
                __import__(module)
                print(f"  {feature}: installed")
            except ImportError:
                print(f"  {feature}: not installed (pip install {package})")
        print("")

    def _check_project(self) -> None:
        """Check project structure."""
        print("-> Project Check")
        print(f"  Root: {self.root}")
        print(f"  Exists: {'Yes' if self.root.exists() else 'No'}")
        print(f"  Is directory: {'Yes' if self.root.is_dir() else 'No'}")

        package_files = [
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "requirements.txt",
        ]

        found = []
        for filename in package_files:
            if (self.root / filename).exists():
                found.append(filename)

        if found:
            print(f"  Package/config files: {', '.join(found)}")
        else:
            print("  Package/config files: none detected")

        print(f"  Git repo: {'Yes' if (self.root / '.git').exists() else 'No'}")
        print("")

    def _check_generated_context(self) -> None:
        """Check generated context files."""
        print("-> Generated Context Check")

        context_dir = self.root / ".llm-context"
        if not context_dir.exists():
            print("  Status: No context generated yet")
            print("  Run: python3 llm-context-setup.py")
            print("")
            return

        manifest = GenerationManifest.load(self.root)
        if manifest:
            print(f"  Last generated: {manifest.generated_at}")
            print(f"  Files tracked: {len(manifest.files)}")

            total_size = 0
            for f in context_dir.rglob("*"):
                if f.is_file():
                    total_size += f.stat().st_size
            print(f"  Total size: {human_readable_size(total_size)}")
        else:
            print("  Status: Manifest missing, corrupted, or outdated")

        print("")

    def _check_security(self) -> None:
        """Check security configuration."""
        print("-> Security Check")

        config = load_config(self.root)
        security = SecurityManager(self.root, config)

        print(f"  Mode: {security.mode}")
        print(f"  Secret Redaction: {'Enabled' if security.redact_secrets else 'Disabled'}")
        print(f"  Audit Logging: {'Enabled' if security.audit_enabled else 'Disabled'}")
        print("")

    def _recommend_improvements(self) -> None:
        """Suggest improvements."""
        print("-> Recommendations")

        recommendations = []

        if not (self.root / "CLAUDE.md").exists():
            recommendations.append("Create CLAUDE.md to capture project conventions")

        if not (self.root / "ARCHITECTURE.md").exists():
            recommendations.append("Create ARCHITECTURE.md to document system design")

        if not (self.root / "llm-context.yml").exists() and not (self.root / "llm-context.json").exists():
            recommendations.append("Create llm-context.yml for project-specific settings")

        if not (self.root / ".git").exists():
            recommendations.append("Initialize git repository for version control")

        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                print(f"  {i}. {rec}")
        else:
            print("  All checks passed!")

        print("")
