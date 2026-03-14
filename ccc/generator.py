"""Main context generator orchestrator."""
from pathlib import Path
from typing import Optional, Dict, List

from .config import load_config
from .manifest import SmartUpdater, GenerationManifest
from .security.modes import SecurityManager
from .extractors.python import PythonExtractor
from .extractors.typescript import TypeScriptExtractor
from .security.manager import SecurityManager
from .generators.tree import TreeGenerator
from .generators.schemas import SchemaGenerator


class LLMContextGenerator:
    """
    Main orchestrator for context generation.

    This is currently a modular skeleton.
    The full single-repo generation logic is still being migrated
    from llm-context-setup.py.
    """

    def __init__(
        self,
        root: Path,
        config: Optional[dict] = None,
        quick_mode: bool = False,
        force: bool = False,
    ):
        self.root = root
        self.config = config or load_config(self.root)
        self.output_dir = self.root / self.config["output_dir"]
        self.quick_mode = quick_mode
        self.updater = SmartUpdater(self.root, self.config, force=force)
        self.security = SecurityManager(self.root, self.config)

    def generate(self) -> None:
        """
        Generate all context files.

        Full logic is still in the standalone script for now.
        """
        print("")
        print("=" * 60)
        print("  CCC Modular Generator Skeleton")
        print("=" * 60)
        print("")
        print("The modular generator is not fully migrated yet.")
        print("Current status:")
        print("  - Workspace mode is modularized")
        print("  - Diagnostics are modularized")
        print("  - Watch mode is modularized")
        print("  - Full single-repo generation still runs in standalone mode")
        print("")
        print("Next migration step:")
        print("  Move core extractors and generators into ccc/")
        print("")
